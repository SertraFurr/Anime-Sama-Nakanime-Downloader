import os
import re
from src.var import Colors, print_status, print_separator
from src.utils.config.config import get_setting

def sanitize_path(path):
    return re.sub(r'[<>:"|?*]', '', path)


_SEASON_FOLDER_RE = re.compile(r'^(season|saison)\s*0*(\d+)$', re.IGNORECASE)


def find_existing_season_dir(anime_dir, saison_info):
    """If --dest points straight at a folder Sonarr/Plex already manages, that
    folder can already contain a season subfolder for this season under a
    different naming convention (Sonarr writes "Season 1", the site's own
    slug is "saison1"/"Saison 1"). Creating a second, differently-named one
    scatters episodes across two folders that neither Sonarr nor this script
    ever reconciles - reuse whichever one already exists instead. Returns the
    existing folder's name, or None if there isn't one / the number can't be
    read from saison_info."""
    m = re.search(r'\d+', saison_info or "")
    if not m or not os.path.isdir(anime_dir):
        return None
    season_num = m.group()
    try:
        candidates = []
        for d in os.listdir(anime_dir):
            if not os.path.isdir(os.path.join(anime_dir, d)):
                continue
            fm = _SEASON_FOLDER_RE.match(d)
            if fm and fm.group(2) == season_num:
                candidates.append(d)
    except OSError:
        return None
    if not candidates:
        return None
    # Prefer Sonarr's own spelling when both exist, since that's the one Sonarr
    # (and therefore Plex, if the library is Sonarr-managed) actually scans.
    for d in candidates:
        if d.lower().replace(" ", "") == f"season{season_num}":
            return d
    return candidates[0]


def format_save_path(anime_name, saison_info, base_path=None):
    template = get_setting("save_template", "./videos/{anime}/{season}")

    fmt_args = {
        "anime": anime_name if anime_name else "Unknown_Anime",
        "season": saison_info if saison_info else "Unknown_Season"
    }

    if base_path:
        anime_dir = os.path.join(base_path, fmt_args["anime"])
        existing = find_existing_season_dir(anime_dir, fmt_args["season"])
        return os.path.join(anime_dir, existing or fmt_args["season"])

    try:
        formatted_path = template.format(**fmt_args)
        return os.path.normpath(formatted_path)
    except Exception:
        return os.path.join("./videos", fmt_args["anime"], fmt_args["season"])

def get_save_directory(anime_name=None, saison_info=None):
    formatted_path = format_save_path(anime_name, saison_info)

    print(f"\n{Colors.BOLD}{Colors.HEADER}📁 SAVE LOCATION{Colors.ENDC}")
    print_separator()

    print(f"{Colors.OKCYAN}Current save path (from config): {Colors.ENDC}{formatted_path}")

    change = input(f"{Colors.BOLD}Press Enter to confirm or type new absolute path: {Colors.ENDC}").strip()

    if change:
        save_dir = change
    else:
        save_dir = formatted_path

    # The folder itself is only created when the first file is written, so
    # cancelling before the download leaves nothing behind - here we just
    # check that it could be created (nearest existing parent is writable).
    ancestor = os.path.abspath(save_dir)
    while not os.path.exists(ancestor):
        parent = os.path.dirname(ancestor)
        if parent == ancestor:
            break
        ancestor = parent

    if os.path.isdir(ancestor) and os.access(ancestor, os.W_OK):
        print_status(f"Save directory confirmed: {os.path.abspath(save_dir)}", "success")
        return save_dir

    print_status(f"Cannot write to {save_dir}", "error")
    default_fallback = "./videos/"
    print_status(f"Using fallback: {default_fallback}", "info")
    return default_fallback
