
import re
from urllib.parse import urljoin, urlparse

import requests

from src.var import DEFAULT_USER_AGENT, print_status


_PACKED_SCRIPT_PATTERN = re.compile(
    r"eval\(function\(p,a,c,k,e,d\)\{[\s\S]*?\}\('(.*?)',(\d+),(\d+),'(.*?)'\.split\('\|'\)",
)
_M3U8_URL_PATTERN = re.compile(
    r"""["']((?:https?:)?//[^"'\s<>]*?\.m3u8(?:\?[^"'\s<>]*)?|(?:\.\.?/|/)?[^"'\s<>]*?\.m3u8(?:\?[^"'\s<>]*)?)["']""",
    re.IGNORECASE,
)
_BASE_ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _encode_base(number, base):
    if number == 0:
        return "0"
    encoded = []
    while number:
        number, remainder = divmod(number, base)
        encoded.append(_BASE_ALPHABET[remainder])
    return "".join(reversed(encoded))


def _unpack_player_scripts(html):
    for match in _PACKED_SCRIPT_PATTERN.finditer(html):
        decoded, base, count, words = match.group(1), int(match.group(2)), int(match.group(3)), match.group(4).split("|")
        if not 2 <= base <= len(_BASE_ALPHABET):
            continue

        for index in range(min(count, len(words)) - 1, -1, -1):
            word = words[index]
            if word:
                token = _encode_base(index, base)
                decoded = re.sub(r"\b" + re.escape(token) + r"\b", lambda _: word, decoded)
        yield decoded


def extract_vidhide_video_source(url, headers=None):
    parsed_url = urlparse(url)
    request_headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Referer": f"{parsed_url.scheme}://{parsed_url.netloc}/",
    }
    if headers:
        request_headers.update(headers)

    try:
        response = requests.get(url, headers=request_headers, allow_redirects=True, timeout=10)
        response.raise_for_status()
    except requests.RequestException as exc:
        print_status(f"Failed to fetch VidHide embed: {exc}", "error")
        return None

    for content in (response.text, *_unpack_player_scripts(response.text)):
        for match in _M3U8_URL_PATTERN.finditer(content):
            source = match.group(1).replace("\\/", "/")
            stream_url = urljoin(response.url, source)
            if urlparse(stream_url).scheme in ("http", "https"):
                return stream_url

    print_status("Could not extract video source from VidHide", "warning")
    return None
