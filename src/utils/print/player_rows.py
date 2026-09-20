import re
from src.var import Colors, SourceDomains
from src.utils.print.format_ranges import format_ranges


def summarize_players(episodes, wanted_episodes=None):
    """Returns (considered, no_source, available, rows) where rows is a list of
    (player, urls, working_episode_numbers) in the same order as `episodes`."""
    longest = max((len(urls) for urls in episodes.values()), default=0)
    considered = set(wanted_episodes) if wanted_episodes else set(range(1, longest + 1))

    # Aucune source chez aucun lecteur : episode pas encore sorti (ou fetch
    # rate). On le resume une seule fois au lieu de le repeter par lecteur.
    no_source = {
        n for n in considered
        if all(n > len(urls) or urls[n - 1] is None for urls in episodes.values())
    }
    available = len(considered) - len(no_source)

    rows = []
    for player, urls in episodes.items():
        working = [
            i for i, url in enumerate(urls, start=1)
            if i in considered and i not in no_source and url is not None
            and SourceDomains.is_valid_url(url, category=player)
        ]
        rows.append((player, urls, working))
    return considered, no_source, available, rows


def display_names(rows):
    """Anime-Sama names players generically ("Player 1"); show the real host
    (Sibnet, Vidmoly...) instead when it can be detected from the URLs."""
    from src.utils.get.get_player_choice import _detect_host
    names, seen = [], {}
    for player, urls, _working in rows:
        name = player
        if re.fullmatch(r"Player \d+", player):
            host = _detect_host(player, urls)
            if host and host != "player":
                base = SourceDomains.DISPLAY_NAMES.get(host, host.capitalize())
                seen[base] = seen.get(base, 0) + 1
                name = base if seen[base] == 1 else f"{base} {seen[base]}"
        names.append(name)
    return names


def format_player_row(player, urls, working, available, name_width, display=None):
    from src.utils.get.get_player_choice import is_fast_player
    fast = "⚡" if is_fast_player(player, urls) else " "
    player = display or player
    ranges = format_ranges(working)
    if len(ranges) > 40:
        ranges = ranges[:40].rsplit(",", 1)[0] + ", …"
    if not working:
        color, mark, detail = Colors.FAIL, "x", "Unavailable"
    elif len(working) == available:
        color, mark, detail = Colors.OKGREEN, "v", f"All ({ranges})"
    else:
        color, mark, detail = Colors.WARNING, "~", f"Partial ({ranges})"
    return f"{color}[{mark}] {player:<{name_width}} {fast} : {detail}{Colors.ENDC}"
