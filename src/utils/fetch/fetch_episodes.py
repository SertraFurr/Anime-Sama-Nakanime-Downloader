import re
import json
import time
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

def _get_nakanime_session_and_headers(headers=None):
    req_headers = {"User-Agent": "Mozilla/5.0"}
    if headers and "User-Agent" in headers:
        req_headers["User-Agent"] = headers["User-Agent"]
    session = requests.Session()
    session.headers.update(req_headers)
    return session, req_headers


def _get_nakanime_episode_numbers(session, anime_id, target_season):
    """Recupere juste la liste des numeros d'episode existants (1-2 requetes,
    pas cher) - separe du fetch des sources par episode (le vrai cout)."""
    url_page = f"https://nakanime.tv/anime/{anime_id}/season/{target_season}/episode/1"
    res_page = session.get(url_page, timeout=10)

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
        res = session.get(f"https://nakanime.tv{path_eps}", timeout=15)
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

    return ep_numbers


def fetch_nakanime_episode_count(base_url, headers=None):
    """Recupere uniquement le nombre d'episodes disponibles, sans faire le
    fetch couteux (source par episode). Sert a demander a l'utilisateur
    quels episodes il veut AVANT de payer le cout du fetch complet."""
    unquoted = urllib.parse.unquote(base_url)
    match_anime = re.search(r'/anime/(\d+)', unquoted)
    if not match_anime:
        return None
    anime_id = int(match_anime.group(1))
    match_season = re.search(r'/season/(\d+)', unquoted)
    target_season = int(match_season.group(1)) if match_season else 1

    try:
        session, _ = _get_nakanime_session_and_headers(headers)
        ep_numbers = _get_nakanime_episode_numbers(session, anime_id, target_season)
        return max(ep_numbers) if ep_numbers else None
    except Exception:
        return None


def fetch_nakanime_episodes(base_url, headers=None, wanted_episodes=None):
    unquoted = urllib.parse.unquote(base_url)
    match_anime = re.search(r'/anime/(\d+)', unquoted)
    if not match_anime:
        print_status("Could not determine Nakanime anime ID", "error")
        return None
    anime_id = int(match_anime.group(1))

    match_season = re.search(r'/season/(\d+)', unquoted)
    target_season = int(match_season.group(1)) if match_season else 1

    print_status(f"Fetching Nakanime player sources for Season {target_season}...", "loading")
    try:
        # Session partagee pour toutes les requetes vers nakanime.tv - reutilise
        # la connexion TCP/TLS (keep-alive) au lieu d'en rouvrir une par requete,
        # ce qui accelere nettement une longue serie de requetes sequentielles
        # sans changer le rythme/volume percu par le serveur.
        session, req_headers = _get_nakanime_session_and_headers(headers)

        all_ep_numbers = _get_nakanime_episode_numbers(session, anime_id, target_season)
        if not all_ep_numbers:
            print_status(f"No episodes found for Season {target_season}", "error")
            return None

        # Si l'appelant sait deja quels episodes il veut (choisis avant ce
        # fetch), on ne paie le cout (et le rate-limit) que pour ceux-la -
        # le reste garde une position None dans la liste finale, alignee sur
        # le nombre total reel d'episodes du site.
        if wanted_episodes:
            ep_numbers = [n for n in all_ep_numbers if n in wanted_episodes]
            if not ep_numbers:
                ep_numbers = all_ep_numbers
        else:
            ep_numbers = all_ep_numbers

        # On indexe par numero d'episode reel (pas par ordre d'arrivee) pour
        # que la position dans la liste finale reste alignee sur ep_num - 1
        # meme si un episode echoue au fetch (sinon tous les episodes suivants
        # se retrouveraient decales d'une position, silencieusement).
        player_episodes_by_num = {}
        path_src = "/api/sources/anime"
        url_src = f"https://nakanime.tv{path_src}"

        # Envoyer ~700 requetes sequentielles sans pause declenche du
        # rate-limiting cote serveur, surtout vers la fin d'une longue
        # saison - d'ou un petit delai entre chaque episode et une
        # retentative avant d'abandonner un episode donne. Le parallelisme
        # (plusieurs requetes en meme temps) a ete teste et rend les choses
        # pires: le serveur rate-limite davantage sans gain de vitesse reel.
        #
        # Le vrai goulot d'etranglement mesure: nakanime.tv laisse passer
        # ~60-100 requetes rapides puis renvoie du 429 (Too Many Requests)
        # avec un header Retry-After (ex: 29s) sur TOUT le reste des episodes.
        # Sans le detecter, chaque episode suivant "echoue" en 0.1s puis
        # attend un backoff bien trop court avant de re-echouer - des
        # centaines d'echecs rapides qui, cumules, prennent des minutes pour
        # rien. On respecte maintenant le Retry-After une seule fois des
        # qu'on le voit, au lieu de le retenter en boucle trop tot.
        print_status(f"Fetching sources for {len(ep_numbers)} episodes...", "loading")
        for ep_num in ep_numbers:
            ep_page_url = f"https://nakanime.tv/anime/{anime_id}/season/{target_season}/episode/{ep_num}"

            sources = None
            for attempt in range(2):
                try:
                    r_page = session.get(ep_page_url, timeout=10)
                    if r_page.status_code == 429:
                        wait_s = int(r_page.headers.get("Retry-After", 30)) + 1
                        print_status(f"Rate-limited by Nakanime, waiting {wait_s}s before resuming...", "warning")
                        time.sleep(wait_s)
                        continue

                    m_ep_id = re.search(r'data-episode-id=["\'](\d+)["\']', r_page.text)
                    if not m_ep_id:
                        raise ValueError("episode id not found")
                    ep_id = int(m_ep_id.group(1))

                    payload = {"anime_id": anime_id, "episode_id": ep_id, "turnstile_token": ""}
                    r_src = session.post(url_src, headers={"Content-Type": "application/json"}, json=payload, timeout=10)
                    if r_src.status_code == 429:
                        wait_s = int(r_src.headers.get("Retry-After", 30)) + 1
                        print_status(f"Rate-limited by Nakanime, waiting {wait_s}s before resuming...", "warning")
                        time.sleep(wait_s)
                        continue
                    if r_src.status_code != 200:
                        raise ValueError(f"sources request failed with status {r_src.status_code}")

                    dec_src = decode_nakanime_response(r_src.content, path_src)
                    sources = json.loads(dec_src.decode('utf-8'))
                    break
                except Exception:
                    if attempt == 0:
                        time.sleep(0.8)
                    continue

            if sources:
                seen_counts = {}
                for item in sources:
                    host = item.get('host', 'unknown').capitalize()
                    lang = item.get('language', 'UNKNOWN')
                    base_key = f"{host} ({lang})"
                    seen_counts[base_key] = seen_counts.get(base_key, 0) + 1
                    cnt = seen_counts[base_key]
                    player_key = f"{host} {cnt} ({lang})" if cnt > 1 else base_key

                    player_episodes_by_num.setdefault(player_key, {})[ep_num] = item.get('url')

        if player_episodes_by_num:
            # Toujours dimensionne sur le total reel de la saison (pas juste
            # le sous-ensemble demande) pour que les index restent coherents
            # avec ce que le reste du programme (selection episode/joueur)
            # attend deja.
            max_ep_num = max(all_ep_numbers)
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

def fetch_episodes(base_url, headers=None, wanted_episodes=None):
    if 'nakanime.tv' in base_url.lower():
        return fetch_nakanime_episodes(base_url, headers, wanted_episodes=wanted_episodes)

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
