import re
import urllib.parse
from src.var import Colors, get_domain

def validate_anime_sama_url(url):
    anime_sama_pattern = re.compile(
        r'^https?://(?:www\.)?anime-sama\.[^/]+/catalogue/[^/]+/.+/.+/?$', 
        re.IGNORECASE
    )
    nakanime_pattern = re.compile(
        r'^https?://(?:www\.)?nakanime\.tv/(?:anime/\d+|catalog\?.*overlay=).*$',
        re.IGNORECASE
    )
    franime_pattern = re.compile(
        r'^https?://(?:www\.)?franime\.fr/anime/[^/?]+\?.*anime_id=\d+.*$',
        re.IGNORECASE
    )
    if anime_sama_pattern.match(url) or nakanime_pattern.match(url) or franime_pattern.match(url):
        return True, ""
    else:
        return False, (
            f"{url} Invalid URL. Format should be:\n"
            f"  https://{get_domain()}/catalogue/<anime-name>/<season-type>/<language>/\n"
            f"  https://nakanime.tv/anime/<id>/season/<s_num>/episode/<ep_num>\n"
        )
