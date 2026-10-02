import re
import json
import requests
import urllib.parse

from src.utils.config.config import get_domain_cookies

NAKANIME_DOMAIN = "nakanime.tv"

def extract_anime_name(base_url):
    match = re.search(r'catalogue/([^/]+)/', base_url)
    if match:
        return match.group(1)
    
    unquoted = urllib.parse.unquote(base_url)
    nakanime_match = re.search(r'/anime/\d+/([^/&#?]+)', unquoted)
    if nakanime_match and nakanime_match.group(1) not in ['season', 'episode']:
        return nakanime_match.group(1)
        
    nakanime_id_match = re.search(r'/anime/(\d+)', unquoted)
    if nakanime_id_match:
        anime_id = nakanime_id_match.group(1)
        try:
            url = f"https://nakanime.tv/anime/{anime_id}/season/1/episode/1"
            req_headers = {"User-Agent": "Mozilla/5.0"}
            cookies = None
            stored = get_domain_cookies(NAKANIME_DOMAIN)
            if stored:
                cf_clearance, stored_headers = stored
                req_headers["User-Agent"] = stored_headers["User-Agent"]
                cookies = {"cf_clearance": cf_clearance}
            res = requests.get(url, headers=req_headers, cookies=cookies, timeout=5)
            scripts = re.findall(r'<script[^>]*>(.*?)</script>', res.text, re.DOTALL)
            for s in scripts:
                if 'title' in s and 'animeId' in s:
                    data = json.loads(s.strip())
                    title = data.get('title')
                    if title:
                        return title
        except Exception:
            pass
        return f"nakanime-{anime_id}"
        
    return "episode"
