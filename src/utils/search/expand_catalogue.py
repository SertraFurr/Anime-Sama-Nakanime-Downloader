import re
import json
import requests
import urllib.parse
from urllib.parse import urljoin
from src.var import get_domain
from src.utils.config.config import get_domain_cookies

NAKANIME_DOMAIN = "nakanime.tv"

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

def expand_nakanime_url(url, headers=None):
    unquoted = urllib.parse.unquote(url)
    match = re.search(r'/anime/(\d+)', unquoted)
    if not match:
        return []
    anime_id = match.group(1)
    
    req_headers = {"User-Agent": "Mozilla/5.0"}
    if headers and "User-Agent" in headers:
        req_headers["User-Agent"] = headers["User-Agent"]
    # a caller-supplied headers dict (e.g. fallback.py's) may carry a Cookie
    # for a different domain - an explicit Cookie header beats cookies= in
    # requests, so the stale cookie would silently win over the one we set below.
    req_headers.pop("Cookie", None)
    req_headers.pop("cookie", None)

    nk_cookies = None
    stored = get_domain_cookies(NAKANIME_DOMAIN)
    if stored:
        cf_clearance, stored_headers = stored
        req_headers["User-Agent"] = stored_headers["User-Agent"]
        nk_cookies = {"cf_clearance": cf_clearance}

    seasons = set()

    try:
        url_page = f"https://nakanime.tv/anime/{anime_id}/season/1/episode/1"
        res_page = requests.get(url_page, headers=req_headers, cookies=nk_cookies, timeout=10)
        scripts = re.findall(r'<script[^>]*>(.*?)</script>', res_page.text, re.DOTALL)
        for s in scripts:
            if 'animeId' in s and 'seasons' in s:
                try:
                    data = json.loads(s.strip())
                    for season in data.get('seasons', []):
                        s_num = season.get('number', 1)
                        if s_num is not None:
                            seasons.add(int(s_num))
                    break
                except Exception:
                    pass
    except Exception:
        pass

    if not seasons:
        try:
            path = f"/api/anime/{anime_id}/episodes"
            api_url = f"https://nakanime.tv{path}"
            res = requests.get(api_url, headers=req_headers, cookies=nk_cookies, timeout=10)
            res.raise_for_status()
            decrypted = decode_nakanime_response(res.content, path)
            data = json.loads(decrypted.decode('utf-8'))
            episodes = data.get('data', [])
            for ep in episodes:
                s_num = ep.get('seasonNumber')
                if s_num is None:
                    s_num = 1
                seasons.add(int(s_num))
        except Exception:
            pass

    if not seasons:
        seasons.add(1)
        
    results = []
    for s_num in sorted(seasons):
        results.append({
            "name": f"Saison {s_num}",
            "url": f"https://nakanime.tv/anime/{anime_id}/season/{s_num}/episode/1"
        })
    return results

def is_valid_season(url, headers):
    try:
        ep_url = url.rstrip('/') + '/episodes.js'
        r = requests.get(ep_url, headers=headers, timeout=5)
        
        if r.status_code != 200:
            return False
            
        content = r.text
        if not content.strip():
            return False

        pattern = re.compile(r'var\s+eps\d+\s*=\s*\[(.*?)\];', re.DOTALL)
        array_matches = pattern.findall(content)
        
        if not array_matches:
            return False

        has_valid_url = False
        for array_content in array_matches:
            urls = re.findall(r"['\"](https?://[^'\"]+)['\"]", array_content)
            
            if any(is_real_url(u) for u in urls):
                has_valid_url = True
                break
                
        return has_valid_url
    except:
        return False

def is_real_url(u):
    u = u.strip()
    if len(u) < 20: return False
    
    if re.search(r'[?&][a-zA-Z0-9_]+=(?:$|&)', u):
        return False

    if re.search(r'/embed[-_.]?(?:\w{3,4})?$', u):
        return False
    
    return True

def get_matches_from_page(url, headers):
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        content = response.text

        content = re.sub(r'<!--[\s\S]*?-->', '', content)
        content = re.sub(r'/\*[\s\S]*?\*/', '', content)

        anime_matches = re.findall(r'panneauAnime\s*\(\s*(["\'])(.*?)\1\s*,\s*(["\'])(.*?)\3\s*\)', content)
        scan_matches = re.findall(r'panneauScan\s*\(\s*(["\'])(.*?)\1\s*,\s*(["\'])(.*?)\3\s*\)', content)
        
        results = []
        for _, name, _, rel_url in anime_matches:
            results.append((name, rel_url))
        for _, name, _, rel_url in scan_matches:
            results.append((name, rel_url))
            
        return results
    except Exception:
        return []

def expand_catalogue_url(url, headers=None):
    if 'nakanime.tv' in url.lower():
        return expand_nakanime_url(url, headers)

    raw_matches = get_matches_from_page(url, headers)
    
    if not raw_matches:
        domain = get_domain()
        match = re.search(r'https?://(?:www\.)?' + re.escape(domain) + r'/catalogue/([^/]+)/', url)
        if match:
            slug = match.group(1)
            root_url = f"https://{domain}/catalogue/{slug}/"
            if root_url.rstrip('/') != url.rstrip('/'):
                raw_matches = get_matches_from_page(root_url, headers)

    results = []
    seen_urls = set()
    
    for name, rel_url in raw_matches:
        if name == "nom" or rel_url == "url":
            continue
            
        full_url = urljoin(url if url.endswith('/') else url + '/', rel_url)
        if not full_url.endswith('/'):
            full_url += '/'
        
        if full_url in seen_urls:
            continue
        
        if '/scan' not in full_url.lower():
            if not is_valid_season(full_url, headers):
                continue
            
        seen_urls.add(full_url)
        results.append({"name": name, "url": full_url})
        
        if 'vostfr' in rel_url.lower():
            vf_rel = rel_url.lower().replace('vostfr', 'vf')
            vf_full = full_url.lower().replace('vostfr', 'vf')
            
            if vf_full not in seen_urls:
                if '/scan' not in vf_full:
                     if is_valid_season(vf_full, headers):
                        vf_name = f"{name} (VF)"
                        results.append({"name": vf_name, "url": vf_full})
                        seen_urls.add(vf_full)

    return results
