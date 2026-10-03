import re
import json
import requests

from src.var import print_status
from src.utils.config.config import get_domain_cookies

NAKANIME_DOMAIN = "nakanime.tv"


def _fetch_nakanime_alt_titles(base_url, headers=None):
    match = re.search(r'(https?://[^/]+/anime/\d+/[^/]+)', base_url)
    root_url = match.group(1) if match else base_url

    request_headers = dict(headers) if headers else {"User-Agent": "Mozilla/5.0"}
    cookies = None
    stored = get_domain_cookies(NAKANIME_DOMAIN)
    if stored:
        cf_clearance, stored_headers = stored
        request_headers["User-Agent"] = stored_headers["User-Agent"]
        # caller's headers may carry a Cookie for a different domain (e.g.
        # anime-sama.to's cf_clearance) - requests leaves an explicit Cookie
        # header untouched even when cookies= is passed, so the stale cookie
        # would silently win and nakanime.tv would 403 again.
        request_headers.pop("Cookie", None)
        request_headers.pop("cookie", None)
        cookies = {"cf_clearance": cf_clearance}

    try:
        response = requests.get(root_url, headers=request_headers, cookies=cookies, timeout=10)
        response.raise_for_status()
        html = response.text
    except requests.RequestException as e:
        print_status(f"Could not fetch alternate titles: {str(e)}", "warning")
        return []

    for ld_match in re.finditer(r'<script type=["\']application/ld\+json["\']>(.*?)</script>', html, re.DOTALL):
        try:
            data = json.loads(ld_match.group(1))
        except json.JSONDecodeError:
            continue

        if data.get('@type') != 'TVSeries':
            continue

        names = []
        for key in ("name", "alternateName"):
            value = data.get(key)
            if value and value.strip() and value.strip() not in names:
                names.append(value.strip())
        return names

    return []


def _fetch_franime_alt_titles(base_url, headers=None):
    from src.utils.search.expand_catalogue import extract_franime_id, find_franime_anime
    try:
        anime = find_franime_anime(extract_franime_id(base_url), headers)
    except (KeyError, ValueError):
        return []
    if not anime:
        return []
    names = []
    for value in [anime.get("title"), anime.get("titleO")] + list((anime.get("titles") or {}).values()):
        if isinstance(value, str) and value.strip() and value.strip() not in names:
            names.append(value.strip())
    # the catalogue lists the title in dozens of languages; only latin ones help
    # the TVDB/IMDb lookup, and a handful is plenty
    return [n for n in names if n.isascii()][:8]


def fetch_alt_titles(base_url, headers=None):
    if 'franime.fr' in base_url.lower():
        return _fetch_franime_alt_titles(base_url, headers=headers)

    if 'nakanime.tv' in base_url.lower() or 'nakanime.fr' in base_url.lower():
        return _fetch_nakanime_alt_titles(base_url, headers=headers)

    match = re.search(r'(https?://[^/]+/catalogue/[^/]+/)', base_url)
    if not match:
        return []
    root_url = match.group(1)

    try:
        response = requests.get(root_url, headers=headers, timeout=10)
        response.raise_for_status()
        html = response.text
    except requests.RequestException as e:
        print_status(f"Could not fetch alternate titles: {str(e)}", "warning")
        return []

    alt_match = re.search(r'id=["\']titreAlter["\'][^>]*>([^<]*)<', html)
    if not alt_match:
        return []

    return [title.strip() for title in alt_match.group(1).split(',') if title.strip()]
