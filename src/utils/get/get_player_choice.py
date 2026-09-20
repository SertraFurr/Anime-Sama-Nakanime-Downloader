from src.var import Colors, print_status, print_separator, SourceDomains
from src.utils.print.format_ranges import format_ranges
from src.utils.print.player_rows import summarize_players, format_player_row, display_names

# Hebergeurs qui servent la video en HLS/m3u8 (plusieurs segments) - le
# telechargeur peut les recuperer en plusieurs morceaux/threads en parallele,
# ce qui les rend generalement bien plus rapides qu'un lien fichier unique.
# Verifie dans le code d'extraction de chaque hebergeur, pas devine.
SEGMENTED_HOSTS = {
    "vidmoly", "voe", "vidzy", "filemoon", "uqload", "ansembed",
    "movearnpre", "embed4me", "lulustream", "luluvdo", "vidhide",
}
# Sibnet et Sendvid renvoient un lien fichier unique (pas de decoupage
# possible) - un seul flux, donc potentiellement plus lent sur un gros fichier.
DIRECT_FILE_HOSTS = {"sibnet", "sendvid"}


def _detect_host(player_key, urls=None):
    """Resolve the real hoster key (vidmoly, sibnet, ...) for this player.

    anime-sama names players generically ("Player 1", "Player 2" - the real
    host is never in the JS variable name, only in the URLs themselves),
    while Nakanime already gives us the real host name directly in
    player_key. Try the key first, fall back to sniffing the URLs.
    """
    base = player_key.split(" ")[0].lower()
    if base in SEGMENTED_HOSTS or base in DIRECT_FILE_HOSTS:
        return base

    for url in (urls or []):
        if not url:
            continue
        url_lower = url.lower()
        for host_key, domains in SourceDomains.DOMAIN_MAP.items():
            domain_list = domains if isinstance(domains, list) else [domains]
            if any(d in url_lower for d in domain_list):
                return host_key
    return base


def is_fast_player(player_key, urls=None):
    """True if this player serves HLS/m3u8 (segmented, multi-thread capable)
    rather than a single direct file - used to prefer fast alternatives when
    a player fails and the downloader falls back to another one."""
    return _detect_host(player_key, urls) in SEGMENTED_HOSTS


def _speed_hint(player_key, urls=None):
    host = _detect_host(player_key, urls)
    if host in SEGMENTED_HOSTS:
        return f"{Colors.OKGREEN}⚡ Fast{Colors.ENDC}"
    if host in DIRECT_FILE_HOSTS:
        return f"{Colors.WARNING}Single file{Colors.ENDC}"
    return None


def get_player_choice(episodes, wanted_episodes=None):
    available_players = list(episodes.keys())
    # Si seule une partie de la saison a ete demandee/fetchee, summarize_players
    # ne compte que sur cette portion (sinon "51/367" ferait croire que le
    # lecteur est presque tout casse alors qu'il couvre tout ce qui a ete demande).
    considered, no_source, available, rows = summarize_players(episodes, wanted_episodes)

    title = f"\n{Colors.BOLD}{Colors.HEADER}🎮 SELECT PLAYER{Colors.ENDC}"
    if no_source:
        title += f" · {available}/{len(considered)} episodes available ({format_ranges(no_source)} not released)"
    else:
        title += f" · {available} episodes"
    print(title)
    print_separator()

    shown = display_names(rows)
    name_width = max((len(n) for n in shown), default=0)
    for i, ((player, urls, working), name) in enumerate(zip(rows, shown), 1):
        print(f"  {i}. {format_player_row(player, urls, working, available, name_width, display=name)}")
    by_display_name = {n.lower(): p for n, p in zip(shown, available_players)}


    while True:
        try:
            choice = input(f"\n{Colors.BOLD}Enter player number (1-{len(available_players)}, 0 to cancel) or type player name: {Colors.ENDC}").strip()

            if choice == "0":
                print_status("Cancelled by user", "warning")
                return None

            if choice.isdigit():
                choice_idx = int(choice) - 1
                if 0 <= choice_idx < len(available_players):
                    return available_players[choice_idx]
                else:
                    print_status(f"Please enter a number between 0 and {len(available_players)}", "error")
            else:
                player_input = choice.lower()
                if player_input in by_display_name:
                    return by_display_name[player_input]
                if player_input.isdigit():
                    player_choice = f"Player {player_input}"
                elif player_input.startswith("player") and player_input[6:].isdigit():
                    player_choice = f"Player {player_input[6:]}"
                elif player_input.replace(" ", "").startswith("player") and player_input.replace(" ", "")[6:].isdigit():
                    player_choice = f"Player {player_input.replace(' ', '')[6:]}"
                else:
                    player_choice = choice.title()
                
                if player_choice in episodes:
                    return player_choice
                else:
                    print_status("Invalid player choice. Try again.", "error")
        except KeyboardInterrupt:
            print_status("\nOperation cancelled by user", "error")
            return None
        except Exception:
            print_status("Invalid input. Please try again.", "error")
