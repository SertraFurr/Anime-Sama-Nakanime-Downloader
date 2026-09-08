import re
import json
import requests
import urllib.parse
from src.var import print_status

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

def fetch_nakanime_episodes(base_url, headers=None):
    unquoted = urllib.parse.unquote(base_url)
    match_anime = re.search(r'/anime/(\d+)', unquoted)
    if not match_anime:
        print_status("Could not determine Nakanime anime ID", "error")
        return None
    anime_id = int(match_anime.group(1))
    
    match_season = re.search(r'/season/(\d+)', unquoted)
    target_season = int(match_season.group(1)) if match_season else 1
    
    req_headers = {"User-Agent": "Mozilla/5.0"}
    if headers and "User-Agent" in headers:
        req_headers["User-Agent"] = headers["User-Agent"]
        
    print_status(f"Fetching Nakanime player sources for Season {target_season}...", "loading")
    try:
        url_page = f"https://nakanime.tv/anime/{anime_id}/season/{target_season}/episode/1"
        res_page = requests.get(url_page, headers=req_headers, timeout=10)
        
        ep_numbers = []
        scripts = re.findall(r'<script[^>]*>(.*?)</script>', res_page.text, re.DOTALL)
        for s in scripts:
            if 'animeId' in s and 'seasons' in s:
                try:
                    data = json.loads(s.strip())
                    for season in data.get('seasons', []):
                        if season.get('number', 1) == target_season:
                            eps = season.get('episodes', [])
                            ep_numbers = [e.get('number') for e in eps if e.get('number') is not None]
                            break
                    break
                except Exception:
                    pass

        if not ep_numbers:
            path_eps = f"/api/anime/{anime_id}/episodes"
            res = requests.get(f"https://nakanime.tv{path_eps}", headers=req_headers, timeout=15)
            res.raise_for_status()
            decrypted = decode_nakanime_response(res.content, path_eps)
            data = json.loads(decrypted.decode('utf-8'))
            all_episodes = data.get('data', [])
            for ep in all_episodes:
                s_num = ep.get('seasonNumber')
                if s_num is None:
                    s_num = 1
                if int(s_num) == target_season:
                    ep_numbers.append(ep.get('number', 1))
            ep_numbers = sorted(list(set(ep_numbers)))

        if not ep_numbers:
            print_status(f"No episodes found for Season {target_season}", "error")
            return None
            
        # On indexe par numero d'episode reel (pas par ordre d'arrivee) pour
        # que la position dans la liste finale reste alignee sur ep_num - 1
        # meme si un episode echoue au fetch (sinon tous les episodes suivants
        # se retrouveraient decales d'une position, silencieusement).
        player_episodes_by_num = {}
        path_src = "/api/sources/anime"
        url_src = f"https://nakanime.tv{path_src}"

        for ep_num in ep_numbers:
            ep_page_url = f"https://nakanime.tv/anime/{anime_id}/season/{target_season}/episode/{ep_num}"
            try:
                r_page = requests.get(ep_page_url, headers=req_headers, timeout=10)
                m_ep_id = re.search(r'data-episode-id=["\'](\d+)["\']', r_page.text)
                if not m_ep_id:
                    continue
                ep_id = int(m_ep_id.group(1))

                payload = {"anime_id": anime_id, "episode_id": ep_id, "turnstile_token": ""}
                r_src = requests.post(url_src, headers={**req_headers, "Content-Type": "application/json"}, json=payload, timeout=10)
                if r_src.status_code == 200:
                    dec_src = decode_nakanime_response(r_src.content, path_src)
                    sources = json.loads(dec_src.decode('utf-8'))

                    seen_counts = {}
                    for item in sources:
                        host = item.get('host', 'unknown').capitalize()
                        lang = item.get('language', 'UNKNOWN')
                        base_key = f"{host} ({lang})"
                        seen_counts[base_key] = seen_counts.get(base_key, 0) + 1
                        cnt = seen_counts[base_key]
                        player_key = f"{host} {cnt} ({lang})" if cnt > 1 else base_key

                        player_episodes_by_num.setdefault(player_key, {})[ep_num] = item.get('url')
            except Exception:
                continue

        if player_episodes_by_num:
            max_ep_num = max(ep_numbers)
            player_episodes = {}
            for player_key, urls_by_num in player_episodes_by_num.items():
                # liste de taille max_ep_num, index i correspond a l'episode i+1
                # (None pour un episode qui a echoue au fetch ou n'a pas ce player)
                episode_list = [urls_by_num.get(n) for n in range(1, max_ep_num + 1)]
                player_episodes[player_key] = episode_list
            print_status(f"Found {len(player_episodes)} player sources across VF & VOSTFR!", "success")
            return player_episodes
        else:
            print_status("No working video players found for this season", "error")
            return None
            
    except Exception as e:
        print_status(f"Failed to fetch Nakanime episodes: {str(e)}", "error")
        return None

def fetch_episodes(base_url, headers=None):
    if 'nakanime.tv' in base_url.lower():
        return fetch_nakanime_episodes(base_url, headers)

    js_url = base_url.rstrip('/') + '/episodes.js'
    print_status("Fetching episode list...", "loading")
    try:
        response = requests.get(js_url, headers=headers, timeout=15)
        response.raise_for_status()
        js_content = response.text
    except Exception as e:
        print_status(f"Failed to fetch episodes.js: {str(e)}", "error")
        return None

    pattern = re.compile(r'var\s+(eps\d+)\s*=\s*\[([^\]]*)\];', re.MULTILINE)
    matches = pattern.findall(js_content)
    episodes = {}
    
    for name, content in matches:
        player_num = re.search(r'\d+', name).group()
        player_name = f"Player {player_num}"
        urls = re.findall(r"'(https?://[^']+)'", content)
        episodes[player_name] = urls
    
    if episodes:
        print_status(f"Found {len(episodes)} players with episodes!", "success")
    else:
        print_status("No episodes found in episodes.js", "error")
    
    return episodes
