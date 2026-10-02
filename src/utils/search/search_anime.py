import requests
import re
import json
import urllib.parse
import difflib
from bs4 import BeautifulSoup
from src.var import get_domain, print_status
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin

cO = "nkapiv1"

def derive_nakanime_key(url_path):
    N = cO + url_path
    V = []
    for v in range(32):
        G = 0
        for q in range(len(N)):
            G = (G * 31 + ord(N[q]) + v) & 255
        V.append(G)
    return V

def decode_nakanime_response(response_bytes, url_path):
    key_bytes = derive_nakanime_key(url_path)
    out = bytearray(len(response_bytes))
    for i in range(len(response_bytes)):
        out[i] = response_bytes[i] ^ key_bytes[i % len(key_bytes)]
    return bytes(out)

def _search_nakanime_one(query, headers=None):
    encoded_query = urllib.parse.quote(query)
    path = f"/api/catalog/search?q={encoded_query}&sort=relevance&page=1&per_page=32"
    url = f"https://nakanime.tv{path}"
    
    req_headers = {"User-Agent": "Mozilla/5.0"}
    if headers and "User-Agent" in headers:
        req_headers["User-Agent"] = headers["User-Agent"]
        
    try:
        response = requests.get(url, headers=req_headers, timeout=10)
        response.raise_for_status()
        decrypted = decode_nakanime_response(response.content, path)
        data = json.loads(decrypted.decode('utf-8'))
        
        results = []
        for item in data.get('data', []):
            title = item.get('title', 'Unknown')
            anime_id = item.get('id')
            slug = item.get('slug')
            if anime_id and slug:
                full_url = f"https://nakanime.tv/anime/{anime_id}/{slug}"
                results.append({
                    "title": title,
                    "url": full_url,
                    "support": "Anime Supported",
                    "site": "nakanime"
                })
        return results
    except Exception as e:
        print_status(f"Nakanime search failed: {str(e)}", "warning")
        return []

def check_link_support(res, headers):
    try:
        from src.utils.search.expand_catalogue import is_valid_season
        
        r = requests.get(res['url'], headers=headers, timeout=5)
        if r.status_code == 200:
            content = r.text
            
            anime_matches = re.findall(r'panneauAnime\s*\(\s*(["\'])(.*?)\1\s*,\s*(["\'])(.*?)\3\s*\)', content)
            
            has_valid_anime = False
            
            base_url = res['url']
            if not base_url.endswith('/'):
                base_url += '/'

            for _, name, _, rel_url in anime_matches:
                if name == "nom" or rel_url == "url": continue
                
                full_url = urljoin(base_url, rel_url)
                if not full_url.endswith('/'): full_url += '/'
                
                if is_valid_season(full_url, headers):
                    has_valid_anime = True
                    break
            
            if has_valid_anime:
                scan_matches = re.findall(r'panneauScan\s*\(\s*(["\'])(.*?)\1\s*,\s*(["\'])(.*?)\3\s*\)', content)
                valid_scan = [m for m in scan_matches if m[1] != "nom" and m[3] != "url"]
                
                if valid_scan:
                    res['support'] = "Anime & Scans Supported"
                else:
                    res['support'] = "Anime Supported"
            else:
                scan_matches = re.findall(r'panneauScan\s*\(\s*(["\'])(.*?)\1\s*,\s*(["\'])(.*?)\3\s*\)', content)
                valid_scan = [m for m in scan_matches if m[1] != "nom" and m[3] != "url"]
                
                if valid_scan:
                    res['support'] = "Scans Supported"
                else:
                    res['support'] = "Unsupported"
        else:
            res['support'] = "Unknown"
    except Exception:
        res['support'] = "Unknown"
    return res

def _search_anime_sama_one(query, headers=None):
    url = f"https://{get_domain()}/template-php/defaut/fetch.php"

    data = {"query": query}
    
    try:
        response = requests.post(url, headers=headers, data=data)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        results = []
        for a in soup.find_all('a'):
            href = a.get('href')
            h3 = a.find('h3')
            title = h3.text.strip() if h3 else "Unknown"
            if href:
                full_url = urljoin(f"https://{get_domain()}/", href)
                results.append({"title": title, "url": full_url, "support": None, "site": "anime-sama"})
        
        return results
    except Exception:
        return []

def _dedupe(results):
    seen, out = set(), []
    for r in results:
        if r['url'] not in seen:
            seen.add(r['url'])
            out.append(r)
    return out

def search_nakanime(queries, headers=None):
    queries = [queries] if isinstance(queries, str) else queries
    return _dedupe([r for q in queries for r in _search_nakanime_one(q, headers)])

def search_anime_sama(queries, headers=None):
    queries = [queries] if isinstance(queries, str) else queries
    results = _dedupe([r for q in queries for r in _search_anime_sama_one(q, headers)])
    if results:
        with ThreadPoolExecutor(max_workers=10) as executor:
            list(executor.map(lambda r: check_link_support(r, headers), results))
    return results

def _keywords(query):
    """The full query plus each keyword alone, so 'king raid' also finds "King's Raid"."""
    words = [w for w in _norm(query).split() if len(w) >= 3]
    return [query] + [w for w in dict.fromkeys(words) if w != _norm(query)]

def _norm(text):
    return re.sub(r'[^a-z0-9 ]', '', text.lower().replace("'", "").replace("-", " "))

def relevance(query, title):
    q, t = _norm(query), _norm(title)
    if not q or not t:
        return 0.0
    t_tokens = t.split()
    q_tokens = [w for w in q.split() if len(w) >= 3] or q.split()
    positions = []
    for qt in q_tokens:
        pos = next((i for i, tt in enumerate(t_tokens) if tt.startswith(qt)), None)
        if pos is not None:
            positions.append(pos)
    covered = len(positions) / len(q_tokens)
    in_order = len(positions) == len(q_tokens) and positions == sorted(positions)
    ratio = difflib.SequenceMatcher(None, q.replace(" ", ""), t.replace(" ", "")).ratio()
    return max(covered * (0.9 if in_order else 0.7), ratio)

MIN_SCORE = 0.5
MIN_PER_SITE = 3

def rank_results(query, results):
    """Best match first inside each site; sites keep a fixed order (Anime-Sama, then Nakanime)."""
    by_site = {}
    for r in results:
        r['score'] = relevance(query, r['title'])
        by_site.setdefault(r.get('site') or '', []).append(r)
    groups = []
    for g in by_site.values():
        g = sorted(g, key=lambda r: -r['score'])
        groups.append([r for i, r in enumerate(g) if i < MIN_PER_SITE or r['score'] >= MIN_SCORE])
    order = {'anime-sama': 0, 'nakanime': 1}
    groups.sort(key=lambda g: order.get(g[0].get('site'), 99))
    return [r for g in groups for r in g]

def search_anime(query, headers=None, site="all"):
    queries = _keywords(query)
    if site and site.lower() == "nakanime":
        return rank_results(query, search_nakanime(queries, headers=headers))
    if site and site.lower() == "anime-sama":
        return rank_results(query, search_anime_sama(queries, headers=headers))

    with ThreadPoolExecutor(max_workers=2) as executor:
        future_sama = executor.submit(search_anime_sama, queries, headers)
        future_naka = executor.submit(search_nakanime, queries, headers)
        results_sama = future_sama.result()
        results_naka = future_naka.result()

    return rank_results(query, results_sama + results_naka)
