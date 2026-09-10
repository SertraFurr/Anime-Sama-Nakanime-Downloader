import random
from tqdm import tqdm

DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

class SourceDomains:
    _SOURCES = {
        "sendvid": ("SendVid", ["sendvid.com"]),
        "dingtezuni": ("Dingtezuni", ["dingtezuni.com"]),
        "sibnet": ("Sibnet", ["video.sibnet.ru"]),
        "oneupload": ("OneUpload", ["oneupload.net", "oneupload.to"]),
        "vidmoly": ("Vidmoly", ["vidmoly.net", "vidmoly.to", "vidmoly.biz", "vidmoly.org", "vidmoly.me"]),
        "movearn": ("Movearnpre", ["movearnpre.com", "ovaltinecdn.com"]),
        "mivalyo": ("Mivalyo", ["mivalyo.com"]),
        "smooth": ("Smoothpre", ["smoothpre.com", "Smoothpre.com"]),
        "embed4me": ("Embed4me", ["embed4me.com", "embed4me"]),
        "uqload": ("Uqload", ["uqload.is", "uqload"]),
        "ansembed": ("AnsEmbed", ["ansembed.net"]),
        "voe": ("Voe", ["voe"]),
        "filemoon": ("Filemoon", ["bysesukior.com", "filemoon"]),
        "luluvdo": ("LuluStream", ["luluvdo.com", "lulustream.com", "lulu"]),
        "vidzy": ("Vidzy", ["vidzy.live", "vidzy.org", "vidzy"]),
        "nakanime": ("Nakanime", ["nakanime.tv", "nakanime.fr", "nakanime"]),
        # VidHide player software (jwplayer + HLS/m3u8) - seen mirrored under
        # rotating domain names that don't contain "vidhide" at all (e.g.
        # minochinos.com); identified by the "/vidhide/..." asset paths in
        # the embed page itself rather than the domain.
        "vidhide": ("VidHide", ["minochinos.com", "vidhide"]),
    }

    ONEUPLOAD = _SOURCES["oneupload"][1]
    VIDMOLY = _SOURCES["vidmoly"][1]
    MOVARNPRE = _SOURCES["movearn"][1]

    PLAYERS = [d for _, domains in _SOURCES.values() for d in domains]
    
    DISPLAY_NAMES = {d: name for name, domains in _SOURCES.values() for d in domains}
    
    DOMAIN_MAP = {
        k: (val[1] if len(val[1]) > 1 else val[1][0])
        for k, val in _SOURCES.items()
    }

    @classmethod
    def is_voe_url(cls, url, category=None):
        if not url:
            return False
        if category and "voe" in str(category).lower():
            return True
        url_lower = str(url).lower()
        if "voe" in url_lower:
            return True
        import re
        if re.search(r'https?://[^/]+/e/[a-zA-Z0-9]+', url_lower):
            non_voe = ["sibnet", "vidmoly", "lulustream", "luluvdo", "vidzy", "filemoon", "uqload", "ansembed", "embed4me", "sendvid", "oneupload"]
            if not any(p in url_lower for p in non_voe):
                return True
        return False

    @classmethod
    def is_valid_url(cls, url, category=None):
        if not url:
            return False
        if cls.is_voe_url(url, category=category):
            return True
        url_lower = str(url).lower()
        return any(source in url_lower for source in cls.PLAYERS)

def get_domain():
    return "anime-sama.to"

def generate_requests_headers(cf_clearance, user_agent=None):
    cookies = f"cf_clearance={cf_clearance}"

    headers = {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "fr-FR,fr;q=0.8",
        "Referer": "https://anime-sama.si/",
        "Origin": "https://anime-sama.si",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Cookie": cookies,
    }
    return headers

class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    DIM = '\033[2m'
    MAGENTA = '\033[35m'

def print_header():
    w = 62
    inner = "ANIME  VIDEO  DOWNLOADER"
    pad   = lambda s: s.center(w)
    header = (
        f"\n{Colors.HEADER}{Colors.BOLD}"
        f"╔{'═' * w}╗\n"
        f"║{pad(inner)}║\n"
        f"╚{'═' * w}╝"
        f"{Colors.ENDC}\n"
        f"{Colors.DIM}  {'─' * (w + 2)}{Colors.ENDC}\n"
        f"  {Colors.OKCYAN}📺  {Colors.DIM}Download anime episodes from your favourite streaming sites.{Colors.ENDC}\n"
        f"  {Colors.DIM}Type a URL, search by name, or browse seasons.{Colors.ENDC}\n"
    )
    print(header)

def print_tutorial():
    tutorial = f"""
{Colors.BOLD}{Colors.HEADER}🎓 COMPLETE TUTORIAL - HOW TO USE{Colors.ENDC}
{Colors.BOLD}{'='*65}{Colors.ENDC}

{Colors.OKGREEN}{Colors.BOLD}Step 1: Find Your Anime{Colors.ENDC}
├─ 🌐 Anime-Sama: {Colors.OKCYAN}https://anime-sama.fr/catalogue/{Colors.ENDC}
├─ 🌐 Nakanime:   {Colors.OKCYAN}https://nakanime.fr/{Colors.ENDC}
├─ 🔍 Search for your desired anime (e.g., "Roshidere")
├─ 📺 Click on the anime title to view seasons
└─ 📂 Navigate to your preferred season and language

{Colors.OKGREEN}{Colors.BOLD}Step 2: Get the Complete URL{Colors.ENDC}
├─ 🎯 Choose your preferred option:
│   ├─ Season (saison1, saison2, etc.)  [Anime-Sama]
│   └─ Language (vostfr, vf, etc.)
├─ 📋 Copy the FULL URL from browser address bar
└─ ✅ Example URL formats:
    {Colors.OKCYAN}https://anime-sama.fr/catalogue/roshidere/saison1/vostfr/{Colors.ENDC}
    {Colors.OKCYAN}https://nakanime.fr/anime/roshidere/{Colors.ENDC}

{Colors.OKGREEN}{Colors.BOLD}Step 3: Run This Program{Colors.ENDC}
├─ 🚀 Start the downloader
├─ 📝 Paste the complete URL when prompted
├─ ⚡ Program will automatically fetch available episodes
└─ 🎮 Follow the interactive prompts

{Colors.WARNING}{Colors.BOLD}📌 IMPORTANT NOTES:{Colors.ENDC}
├─ ✅ Supported sites: Anime-Sama & Nakanime
├─ ✅ Supported video sources: See GitHub README for details
├─ ❌ Other sites/sources are not supported
├─ 🔗 URL must be the complete path including season/language
└─ 📁 Videos save to ./videos/ by default (customizable)

{Colors.OKGREEN}{Colors.BOLD}🎯 Example URLs that work:{Colors.ENDC}
├─ https://anime-sama.fr/catalogue/roshidere/saison1/vostfr/
├─ https://anime-sama.fr/catalogue/demon-slayer/saison1/vf/
├─ https://anime-sama.fr/catalogue/attack-on-titan/saison3/vostfr/
├─ https://anime-sama.fr/catalogue/one-piece/saison1/vostfr/
├─ https://nakanime.fr/anime/roshidere/
├─ https://nakanime.fr/anime/demon-slayer/

{Colors.BOLD}{'='*65}{Colors.ENDC}
"""
    print(tutorial)

def print_separator(char="─", length=65, title=""):
    # tqdm.write() (not print()) so this coordinates with any active tqdm
    # progress bars - it clears them, writes the line, then redraws them,
    # instead of writing straight to the terminal and visually colliding
    # with a bar mid-redraw (which plain print() does, even though the
    # underlying write itself is atomic).
    if title:
        title_str = f"  {title}  "
        side = max(0, (length - len(title_str)) // 2)
        line = char * side + title_str + char * (length - side - len(title_str))
        tqdm.write(f"{Colors.OKBLUE}{Colors.BOLD}{line}{Colors.ENDC}")
    else:
        tqdm.write(f"{Colors.OKBLUE}{char * length}{Colors.ENDC}")

def print_section(title, emoji=""):
    label = f" {emoji}  {title} " if emoji else f" {title} "
    border = "─" * (len(label) + 2)
    tqdm.write(
        f"\n{Colors.BOLD}{Colors.HEADER}┌{border}┐\n"
        f"│ {label} │\n"
        f"└{border}┘{Colors.ENDC}"
    )

def print_status(message, status_type="info"):
    icons = {
        "info":    "ℹ️ ",
        "success": "✅ ",
        "warning": "⚠️ ",
        "error":   "❌ ",
        "loading": "⏳ "
    }
    colors = {
        "info":    Colors.OKBLUE,
        "success": Colors.OKGREEN,
        "warning": Colors.WARNING,
        "error":   Colors.FAIL,
        "loading": Colors.OKCYAN
    }
    icon  = icons.get(status_type, "ℹ️ ")
    color = colors.get(status_type, Colors.OKBLUE)
    tqdm.write(f"{color}{icon}{message}{Colors.ENDC}")
