import requests
from concurrent.futures import ThreadPoolExecutor

from src.var import DEFAULT_USER_AGENT
from src.utils.extract.extract_sendvid_video_source import extract_sendvid_video_source
from src.utils.download.download_video import MIN_VIDEO_BYTES

# Checking costs two requests per episode, so only the first few selected
# episodes are looked at - a host that serves placeholders does it everywhere.
SAMPLE_SIZE = 12


def _fetch_html(url):
    # same headers as fetch_page_content, minus its "Connecting to server..." line
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Gecko/20100101 Firefox/108.0",
        "Referer": "https://sendvid.com/",
    }
    return requests.get(url, headers=headers, timeout=10).text


def _remote_size(video_url):
    headers = {"User-Agent": DEFAULT_USER_AGENT, "Referer": "https://sendvid.com/", "Range": "bytes=0-0"}
    resp = requests.get(video_url, headers=headers, timeout=15, stream=True)
    try:
        content_range = resp.headers.get("Content-Range", "")
        if "/" in content_range and content_range.split("/")[-1].isdigit():
            return int(content_range.split("/")[-1])
        if resp.status_code == 200:
            return int(resp.headers.get("Content-Length", 0))
    finally:
        resp.close()
    return 0


def _is_placeholder(embed_url):
    try:
        source = extract_sendvid_video_source(_fetch_html(embed_url))
        if not source:
            return False
        size = _remote_size(source)
        return 0 < size < MIN_VIDEO_BYTES
    except Exception:
        return False


def find_placeholder_episodes(host, urls, working):
    """Episode numbers (among `working`) whose Sendvid file is the tiny
    "video unavailable" clip. Only Sendvid is known to do this, other hosts
    return an empty set."""
    if host != "sendvid":
        return set()
    sample = list(working)[:SAMPLE_SIZE]
    with ThreadPoolExecutor(max_workers=6) as pool:
        verdicts = list(pool.map(lambda n: _is_placeholder(urls[n - 1]), sample))
    return {n for n, fake in zip(sample, verdicts) if fake}
