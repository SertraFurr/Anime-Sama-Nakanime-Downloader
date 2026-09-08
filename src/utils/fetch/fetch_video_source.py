import re
import time
import requests

from src.var                                            import print_status, SourceDomains
from src.utils.parse.parse_m3u8_content                 import parse_m3u8_content
from src.utils.extract.extract_movearnpre_video_source  import extract_movearnpre_video_source
from src.utils.extract.extract_sendvid_video_source     import extract_sendvid_video_source
from src.utils.extract.extract_embed4me_video_source   import extract_embed4me_video_source
from src.utils.extract.extract_oneupload_video_source   import extract_oneupload_video_source
from src.utils.extract.extract_vidmoly_video_source     import extract_vidmoly_video_source
from src.utils.fetch.fetch_page_content                 import fetch_page_content
from src.utils.extract.extract_sibnet_video_source      import extract_sibnet_video_source
from src.utils.fetch.fetch_sibnet_redirect_location     import fetch_sibnet_redirect_location
from src.utils.extract.extract_uqload_video_source      import extract_m3u8
from src.utils.extract.extract_ansembed_video_source   import extract_ansembed_video_source
from src.utils.extract.extract_voe_video_source        import extract_voe_video_source
from src.utils.extract.extract_filemoon_video_source   import extract_filemoon_video_source
from src.utils.extract.extract_luluvdo_video_source   import extract_luluvdo_video_source
from src.utils.extract.extract_vidzy_video_source     import extract_vidzy_video_source

try:
    from urllib3.exceptions import InsecureRequestWarning
    requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
except Exception:
    pass


def _get_m3u8(url, headers, timeout=10):
    """GET a playlist URL, falling back to an unverified TLS connection if the
    CDN box serving it has a broken/incomplete certificate chain (observed on
    several dynamically-assigned Vidmoly/Uqload/Ansembed CDN boxes). The
    playlist itself is public video stream data, not sensitive, so relaxing
    verification here (and only here, only as a fallback) is an acceptable
    tradeoff to avoid a hard failure on an otherwise-working stream."""
    try:
        return requests.get(url, headers=headers, timeout=timeout)
    except requests.exceptions.SSLError:
        print_status("CDN certificate invalid, retrying without TLS verification...", "warning")
        return requests.get(url, headers=headers, timeout=timeout, verify=False)


def fetch_video_source(url):
    def process_single_url(single_url):
        print_status(f"Processing video URL: {single_url[:50]}...", "loading")

        # VIDZY EXTRACTION
        if 'vidzy.live' in single_url or 'vidzy.org' in single_url or 'vidzy' in single_url:
            stream_url = extract_vidzy_video_source(single_url)
            if stream_url:
                return stream_url
            return None

        # LULUVDO / LULUSTREAM EXTRACTION

        if 'luluvdo.com' in single_url or 'lulustream.com' in single_url or 'lulu' in single_url:
            try:
                import requests as _r
                rtest = _r.get(single_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=6)
                if rtest.status_code == 200 and ('m3u8' in rtest.text or 'eval(function' in rtest.text):
                    return f"LULU_DEFERRED:{single_url}"
            except Exception:
                pass
            return None

        # FILEMOON EXTRACTION
        if 'bysesukior.com' in single_url or 'filemoon' in single_url:
            stream_url = extract_filemoon_video_source(single_url)
            if stream_url:
                return stream_url
            return None

        # VOE EXTRACTION
        if SourceDomains.is_voe_url(single_url):
            stream_url = extract_voe_video_source(single_url)
            if stream_url:
                return stream_url
            return None

        # VIDMOLY DOMAIN & ROUTE CONVERSION
        # vidmoly.biz is preferred (canonical embed host), but its cert has
        # been known to break server-side - keep every other domain variant
        # as a fallback candidate instead of hard-committing to .biz, so a
        # single dead domain doesn't take down every Vidmoly download.
        vidmoly_candidates = []
        if 'vidmoly' in single_url:
            m_route = re.search(r'/(?:v|w)/([a-zA-Z0-9]+)', single_url)
            if m_route:
                code = m_route.group(1)
                vidmoly_candidates = [f"https://{d}/embed-{code}.html" for d in
                                       ("vidmoly.biz", "vidmoly.org", "vidmoly.net", "vidmoly.to", "vidmoly.me")]
            else:
                for domain in ("vidmoly.to", "vidmoly.net", "vidmoly.org", "vidmoly.me"):
                    if domain in single_url:
                        others = [d for d in ("vidmoly.biz", "vidmoly.org", "vidmoly.net", "vidmoly.to", "vidmoly.me") if d != domain]
                        vidmoly_candidates = [single_url] + [single_url.replace(domain, d) for d in others]
                        break
            if vidmoly_candidates:
                single_url = vidmoly_candidates[0]
            print_status("Normalized Vidmoly domain/route", "info")
        
        # SENDVID EXTRACTION
        if 'sendvid.com' in single_url:
            html_content = fetch_page_content(single_url)
            return extract_sendvid_video_source(html_content)

        # EMBED4ME EXTRACTION
        if 'embed4me' in single_url or 'embed4me.com' in single_url or 'lpayer.embed4me.com' in single_url:
            m3u8_url = extract_embed4me_video_source(single_url)
            if not m3u8_url:
                return None
            return m3u8_url
        
        # SIBNET EXTRACTION
        elif 'video.sibnet.ru' in single_url:
            html_content = fetch_page_content(single_url)
            video_source = extract_sibnet_video_source(html_content)
            if video_source:
                print_status("Getting direct download link...", "loading")
                return fetch_sibnet_redirect_location(video_source)
            return None
        # UQLOAD EXTRACTION
        elif 'uqload' in single_url:
            master_m3u8 = extract_m3u8(single_url)
            if not master_m3u8:
                return None
            try:
                headers = {"accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8", "accept-language": "fr-FR,fr;q=0.8", "cache-control": "no-cache", "sec-gpc": "1", "upgrade-insecure-requests": "1", "user-agent": "Chrome/150.0.0.0 Safari/67.67"}

                response = _get_m3u8(master_m3u8, headers, timeout=10)

                response.raise_for_status()

                streams = parse_m3u8_content(response.text)
                if not streams:
                    print_status("No video streams found in UQLoad playlist","error")
                    return master_m3u8

                best_stream = max(streams, key=lambda x: int(x.get("BANDWIDTH", 0)) )
                return best_stream["url"]

            except requests.RequestException as e:
                print_status(
                    f"Failed to fetch UQLoad playlist: {e}",
                    "error"
                )
                return master_m3u8
            
        # ONEUPLOAD EXTRACTION
        elif 'oneupload.net' in single_url or 'oneupload.to' in single_url:
            single_url = single_url.replace('oneupload.to', 'oneupload.net')
            html_content = fetch_page_content(single_url)
            m3u8_url = extract_oneupload_video_source(html_content)
            if not m3u8_url:
                return None
            try:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Gecko/20100101 Firefox/108.0',
                    'Referer': 'https://oneupload.net/'
                }
                response = _get_m3u8(m3u8_url, headers, timeout=10)
                response.raise_for_status()
                streams = parse_m3u8_content(response.text)
                if not streams:
                    print_status("No video streams found in M3U8 playlist", "error")
                    return None
                return max(streams, key=lambda x: int(x.get('BANDWIDTH', 0)))['url']
            except requests.RequestException as e:
                print_status(f"Failed to fetch M3U8 playlist: {str(e)}", "error")
                return None
            
        # VIDMOLY EXTRACTION
        elif 'vidmoly' in single_url:
            html_content = None
            candidates = vidmoly_candidates or [single_url]

            for candidate_url in candidates:
                attempt = 0
                while attempt < 5:
                    attempt += 1
                    html_content = fetch_page_content(candidate_url)
                    if html_content and '<title>Please wait</title>' in html_content and not "url.indexOf('?'" in html_content:
                        print_status(f"Vidmoly rate limit ('Please wait') detected. Retrying in 3s (Attempt {attempt})...", "warning")
                        time.sleep(3)
                        continue
                    break

                if html_content:
                    single_url = candidate_url
                    break
                elif len(candidates) > 1:
                    print_status(f"Vidmoly domain {candidate_url} unreachable, trying next domain...", "warning")

            m3u8_url = extract_vidmoly_video_source(html_content, single_url)
            if not m3u8_url:
                return None
            try:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Gecko/20100101 Firefox/108.0',
                    'Referer': 'https://vidmoly.net/'
                }
                response = _get_m3u8(m3u8_url, headers, timeout=10)
                response.raise_for_status()
                streams = parse_m3u8_content(response.text)
                if not streams:
                    print_status("No video streams found in M3U8 playlist", "error")
                    return None
                return max(streams, key=lambda x: int(x.get('BANDWIDTH', 0)))['url']
            except requests.RequestException as e:
                print_status(f"Failed to fetch M3U8 playlist: {str(e)}", "error")
                return None
        
        # ANSEMBED EXTRACTION
        elif 'ansembed.net' in single_url:
            html_content = fetch_page_content(single_url)
            m3u8_url = extract_ansembed_video_source(html_content)
            if not m3u8_url:
                return None
            try:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Gecko/20100101 Firefox/108.0',
                    'Referer': 'https://ansembed.net/'
                }
                response = _get_m3u8(m3u8_url, headers, timeout=10)
                response.raise_for_status()
                streams = parse_m3u8_content(response.text)
                if not streams:
                    print_status("No video streams found in M3U8 playlist", "error")
                    return None
                return max(streams, key=lambda x: int(x.get('BANDWIDTH', 0)))['url']
            except requests.RequestException as e:
                print_status(f"Failed to fetch M3U8 playlist: {str(e)}", "error")
                return None
        
        # all those !
        elif 'dingtezuni.com' in single_url or 'mivalyo.com' in single_url or 'smoothpre.com' in single_url or 'Smoothpre.com' in single_url or 'movearnpre.com' in single_url:
            m3u8_url = extract_movearnpre_video_source(single_url)
            if not m3u8_url:
                return None
            return m3u8_url

    if isinstance(url, str):
        return process_single_url(url)
    elif isinstance(url, list):
        results = []
        for i, single_url in enumerate(url):
            result = process_single_url(single_url)
            results.append(result)
        return results
    else:
        print_status("Invalid input: URL must be a string or a list of strings.", "error")
        return None
