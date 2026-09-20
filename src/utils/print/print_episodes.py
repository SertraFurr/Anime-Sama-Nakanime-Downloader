from src.var import Colors, print_separator
from src.utils.print.format_ranges import format_ranges
from src.utils.print.player_rows import summarize_players


def print_episodes(episodes, wanted_episodes=None):
    """Header only: the per-player detail is shown, numbered, by get_player_choice."""
    considered, no_source, available, _rows = summarize_players(episodes, wanted_episodes)

    header = f"\n{Colors.BOLD}{Colors.HEADER}📺 AVAILABLE EPISODES ({available}/{len(considered)}){Colors.ENDC}"
    if no_source:
        header += f" · {len(no_source)} not released ({format_ranges(no_source)})"
    print(header)
    print_separator("─")
