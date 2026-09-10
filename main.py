from src.utils.config.config import get_cookies, set_cookies, check_cookies
from src.utils.print.print_status import print_status
from src.var import Colors, get_domain, print_header, print_separator, print_tutorial, generate_requests_headers, SourceDomains
from src.utils.check.is_cloudflare_here import check_if_cloudflare_enabled

def tutorial_input():
    print_status("No valid Cloudflare cookies found. Let's set them up!", "info")
    print_status(f"1. Open {get_domain()} in your browser.", "info")
    print_status("2. Press F12 to open Developer Tools.", "info")
    print_status(f"3. Go to the 'Application' tab → Cookies → select {get_domain()}.", "info")
    print_status("4. Copy the value of the 'cf_clearance' cookie.", "info")
    cf_clearance = input("Paste the cf_clearance value here: ").strip()

    print_status("5. In DevTools Console (F12 → Console), run:", "info")
    print_status("   navigator.userAgent", "info")
    print_status("6. Copy the User-Agent string printed in console WITHOUT the ' .", "info")
    user_agent = input("Paste the User-Agent here: ").strip()

    return cf_clearance, user_agent

print("Checking if cloudflare is enabled..")
cloudflare = check_if_cloudflare_enabled(domain=get_domain(), headers={"User-Agent": "Mozilla/5.0"})

if cloudflare:
    print("Cloudflare is enabled, either wait (Unknown time) or follow this:")
    cookies_info = get_cookies()
    if cookies_info is False:
        cf_clearance, user_agent = tutorial_input()
        set_cookies(cf_clearance, user_agent)
    cf_clearance, headers = get_cookies()
    request_headers = {"User-Agent": headers.get("User-Agent")}

    while not check_cookies(domain=get_domain(), headers=request_headers):
        print_status("Please update your Cloudflare cookies or use the same User-Agent as before.", "error")
        cf_clearance, user_agent = tutorial_input()
        set_cookies(cf_clearance, user_agent)

    user_agent = headers.get("User-Agent")
    headers = generate_requests_headers(cf_clearance, user_agent)
else:
    headers = generate_requests_headers("None", "Mozilla/5.0")

import os
import re
import sys
import argparse
from concurrent.futures                         import ThreadPoolExecutor, as_completed
from src.utils.fetch.fetch_episodes             import fetch_episodes, fetch_nakanime_episode_count
from src.utils.fetch.fetch_video_source         import fetch_video_source
from src.utils.print.print_episodes             import print_episodes
from src.utils.get.get_player_choice            import get_player_choice, is_fast_player
from src.utils.get.get_episode_choice           import get_episode_choice
from src.utils.check.check_package              import check_package
from src.utils.check.check_ffmpeg_installed     import check_ffmpeg_installed
from src.utils.validate_anime_sama_url          import validate_anime_sama_url
from src.utils.extract.extract_anime_name       import extract_anime_name
from src.utils.get.get_save_directory           import get_save_directory, format_save_path
from src.utils.download.download_episode        import download_episode, create_match_file, convert_episode_ts_to_mp4
from src.utils.fetch.fetch_alt_titles           import fetch_alt_titles
from src.utils.download.download_episode_with_fallback import download_episode_with_fallback
from src.utils.search.search_anime              import search_anime
from src.utils.search.expand_catalogue          import expand_catalogue_url
from src.utils.download.download_scan           import download_scan
from src.utils.settings.settings_menu           import settings_menu

# PLEASE DO NOT REMOVE: Original code from https://github.com/sertrafurr/Anime-Sama-Downloader

def parse_selection_indices(user_input, count):
    """Parse a 1-based selection string (comma list, ranges like 12-49, or 'all') into 0-based indices."""
    user_input = user_input.strip().lower()
    if not user_input:
        return []

    if user_input == 'all':
        return list(range(count))

    indices = []
    seen = set()
    for part in user_input.split(','):
        part = part.strip()
        if not part:
            continue
        try:
            if '-' in part:
                start, end = map(int, part.split('-', 1))
                nums = range(start, end + 1)
            else:
                nums = [int(part)]
        except ValueError:
            print_status(f"Invalid selection: '{part}'", "error")
            continue

        for num in nums:
            if num in seen:
                continue
            seen.add(num)
            if 1 <= num <= count:
                indices.append(num - 1)
            else:
                print_status(f"Number {num} is out of range (1-{count})", "error")

    return indices


def process_season(base_url, args, headers, interactive, pause_at_end=True):
    is_valid, error_msg = validate_anime_sama_url(base_url)
    if not is_valid:
        print_status(error_msg, "error")
        return 1

    if "/scan" in base_url.lower():
        download_scan(base_url, headers)
        return 0

    anime_name = extract_anime_name(base_url)
    print_status(f"Detected anime: {anime_name}", "info")

    # Nakanime fetch le cout reel un episode a la fois (rate-limite par le
    # site au-dela de ~40-50 requetes/minute) - demander a l'utilisateur
    # quels episodes il veut AVANT ce fetch (plutot qu'apres, comme pour
    # anime-sama ou le cout est negligeable) evite de payer inutilement pour
    # toute une saison quand il n'en veut qu'une poignee.
    wanted_episodes = None
    if 'nakanime.tv' in base_url.lower():
        nb_episodes = fetch_nakanime_episode_count(base_url, headers=headers)
        if nb_episodes:
            selection_str = None
            if args.latest:
                selection_str = str(nb_episodes)
            elif args.episodes:
                selection_str = args.episodes
            elif interactive:
                selection_str = input(
                    f"{Colors.BOLD}This season has {nb_episodes} episodes. "
                    f"Which ones do you want (1-{nb_episodes}, comma-separated, ranges like 12-49, or 'all')? "
                    f"{Colors.ENDC}"
                ).strip()
                args.episodes = selection_str

            if selection_str and selection_str.lower() != 'all':
                indices = parse_selection_indices(selection_str, nb_episodes)
                if indices:
                    wanted_episodes = {i + 1 for i in indices}

    episodes = fetch_episodes(base_url, headers=headers, wanted_episodes=wanted_episodes)
    if not episodes:
        print_status("Failed to fetch episodes.", "error")
        return 1

    print_episodes(episodes, wanted_episodes=wanted_episodes)

    player_choice = None
    if args.player:
        avail = list(episodes.keys())
        if args.player in avail:
            player_choice = args.player
        else:
            for p in avail:
                if args.player.lower() in p.lower():
                    player_choice = p
                    break

            if not player_choice:
                target = args.player.lower()
                domain_map = SourceDomains.DOMAIN_MAP

                search_domains = []
                if target in domain_map:
                     val = domain_map[target]
                     if isinstance(val, list): search_domains.extend(val)
                     else: search_domains.append(val)
                else:
                    search_domains.append(target)

                for p in avail:
                    urls_to_check = [u for u in episodes[p][:5] if u]
                    found_match = False
                    for u in urls_to_check:
                        u_lower = u.lower()
                        if any(d in u_lower for d in search_domains):
                            player_choice = p
                            found_match = True
                            break
                    if found_match:
                        break

        if not player_choice:
            print_status(f"Player '{args.player}' not found.", "error")
            return 1
    else:
        player_choice = get_player_choice(episodes, wanted_episodes=wanted_episodes)

    if not player_choice:
        return 1

    episode_indices = None

    if args.latest:
        if episodes and player_choice in episodes:
            count = len(episodes[player_choice])
            if count > 0:
                episode_indices = [count - 1]
                print_status(f"Latest episode selected: Episode {count}", "info")
            else:
                print_status("No episodes found to select latest.", "error")
                return 1
        else:
            return 1

    if not episode_indices:
        if args.episodes:
            if args.episodes.lower() == 'all':
                episode_indices = []
                for i in range(len(episodes[player_choice])):
                    url = episodes[player_choice][i]
                    if url and 'vk.com' not in url and 'myvi.tv' not in url:
                        episode_indices.append(i)
            else:
                # parse_selection_indices supporte deja les plages (12-49) et
                # les listes separees par virgules - l'ancien parsing local
                # ici ne gerait que les virgules et plantait ("Invalid
                # episode list format") des qu'un tiret apparaissait, y
                # compris pour la selection faite juste avant le fetch.
                episode_indices = parse_selection_indices(args.episodes, len(episodes[player_choice]))
                if not episode_indices:
                    print_status("Invalid episode list format", "error")
                    return 1
        else:
             if not args.latest:
                episode_indices = get_episode_choice(episodes, player_choice)

    if episode_indices is None or not episode_indices:
        return 1

    get_anime_name = extract_anime_name(base_url)
    if 'nakanime.tv' in base_url.lower() or 'nakanime.fr' in base_url.lower():
        m_season = re.search(r'/season/(\d+)', base_url)
        get_saison_info = f"saison{m_season.group(1)}" if m_season else "saison1"
    else:
        get_saison_info = base_url.split('/')[-3]


    if args.dest:
         save_dir = format_save_path(get_anime_name, get_saison_info, base_path=args.dest)
    elif interactive:
        save_dir = get_save_directory(get_anime_name, get_saison_info)
    else:
        save_dir = format_save_path(get_anime_name, get_saison_info)

    if not args.dest and not interactive:
         os.makedirs(save_dir, exist_ok=True)

    if isinstance(episode_indices, int):
        episode_indices = [episode_indices]

    # Un index peut valoir None si le fetch de cet episode a echoue plus tot
    # (ex: source Nakanime indisponible) - on l'ignore au lieu de planter ou
    # de decaler les episodes suivants.
    filtered_indices = []
    for index in episode_indices:
        if episodes[player_choice][index] is None:
            print_status(f"Episode {index + 1} unavailable for this player, skipping.", "error")
        else:
            filtered_indices.append(index)
    episode_indices = filtered_indices

    if not episode_indices:
        print_status("No available episodes to download for this player.", "error")
        return 1

    urls = [episodes[player_choice][index] for index in episode_indices]
    episode_numbers = [index + 1 for index in episode_indices]
    def _player_lang(player_key):
        m = re.search(r'\(([^)]+)\)\s*$', player_key)
        return m.group(1).strip().upper() if m else None

    # Quand le lecteur choisi echoue pour un episode, on prefere retomber sur
    # un autre lecteur "rapide" (HLS/m3u8, multi-thread) avant les lecteurs
    # a fichier unique (Sibnet, Sendvid) - sinon un fallback silencieux vers
    # Sibnet fait perdre tout le gain de vitesse du choix initial.
    def _speed_sort_key(p):
        return 0 if is_fast_player(p, episodes.get(p)) else 1

    chosen_lang = _player_lang(player_choice)
    other_players = [p for p in episodes.keys() if p != player_choice]
    if chosen_lang:
        same_lang = sorted([p for p in other_players if _player_lang(p) == chosen_lang], key=_speed_sort_key)
        other_lang = sorted([p for p in other_players if _player_lang(p) != chosen_lang], key=_speed_sort_key)
        player_order = [player_choice] + same_lang + other_lang
    else:
        player_order = [player_choice] + sorted(other_players, key=_speed_sort_key)

    if not args.no_mal and get_anime_name:
        os.makedirs(save_dir, exist_ok=True)
        alt_names = fetch_alt_titles(base_url, headers=headers)
        # get_saison_info is "saisonN" (or nakanime's "saisonN") - pull N out
        # so the MAL search can be season-aware instead of always searching
        # the bare show name (which silently matches season 1's MAL entry
        # even when downloading a later season/part, e.g. Fire Force S3).
        m_season_num = re.search(r'\d+', get_saison_info or "")
        season_number = int(m_season_num.group()) if m_season_num else None
        create_match_file(save_dir, get_anime_name, interactive=interactive, alt_names=alt_names, season_number=season_number)

    print(f"\n{Colors.BOLD}{Colors.HEADER}🎬 PROCESSING EPISODES{Colors.ENDC}")
    print_separator()
    print_status(f"Player: {player_choice}", "info")
    print_status(f"Episodes selected: {', '.join(map(str, episode_numbers))}", "info")

    video_sources = fetch_video_source(urls)
    if not video_sources:
        print_status("Could not extract video sources", "error")
        return 1

    if isinstance(video_sources, str):
        video_sources = [video_sources]

    use_threading = args.threads
    use_ts_threading = args.fast
    automatic_mp4 = args.mp4
    pre_selected_tool = args.tool

    if interactive:
        if len(episode_indices) > 1 and not args.threads:
            thread_choice = input(f"{Colors.BOLD}Download all episodes simultaneously? (t/1/y = yes / s = no): {Colors.ENDC}").strip().lower()
            use_threading = thread_choice in ['t', 'threaded', '1', 'y', 'yes']

        # Only checking the chosen player's own video_sources misses the case
        # where it fails per-episode and download_episode_with_fallback()
        # switches to a different (segmented/m3u8) player - the ts-threading
        # and mp4-conversion questions would then silently never get asked,
        # even though the fallback player ends up needing them.
        any_fallback_is_fast = any(is_fast_player(p, episodes.get(p)) for p in player_order)
        if any_fallback_is_fast or any('m3u8' in src for src in video_sources if src):
            if use_threading:
                print_status("Using threading with M3U8.", "warning")

            if not args.fast:
                 ts_thread_choice = input(f"{Colors.BOLD}Download .ts files simultaneously (fast)? (y/n): {Colors.ENDC}").strip().lower()
                 use_ts_threading = ts_thread_choice in ['t', 'threaded', '1', 'y', 'yes']

            if not args.mp4:
                auto_mp4_choice = input(f"{Colors.BOLD}Convert to .mp4 automatically? (y/n): {Colors.ENDC}").strip().lower()
                automatic_mp4 = auto_mp4_choice in ['t', 'threaded', '1', 'y', 'yes']

                if automatic_mp4:
                    if not pre_selected_tool:
                         while True:
                            t = input(f"{Colors.BOLD}Tool (1=av, 2=ffmpeg): {Colors.ENDC}").strip()
                            if t in ['1', 'av', '']:
                                pre_selected_tool = 'av'
                                break
                            elif t in ['2', 'ffmpeg']:
                                pre_selected_tool = 'ffmpeg'
                                break

    failed_downloads = 0
    try:
        if use_threading and len(episode_indices) > 1:
            print_status("Starting threaded downloads...", "info")
            from src.utils.download.download_video import set_batch_size
            set_batch_size(len(episode_indices))
            # Once inside a threaded batch, no per-episode question should
            # ever hit the terminal again - the batch-level choices already
            # made (use_ts_threading, automatic_mp4) cover it, and letting
            # download_video() fall back to an interactive input() per file
            # means multiple threads race to read stdin at once (this was
            # producing the repeated, garbled "Threaded Download Option"
            # prompts interleaved with progress bars). Forcing
            # interactive=False here makes it silently default instead.
            # Downloads and conversions are split into two separate phases
            # instead of each episode converting right after its own
            # download finishes. Converting mid-batch meant its (occasional
            # but still live-terminal) output was printed while OTHER
            # episodes' download bars were still actively redrawing -
            # mixing those broke the bars' terminal positioning and
            # produced garbled output. Running every download to
            # completion first (bars visible throughout, no other prints
            # happening) then every conversion afterward (bars gone, only
            # plain text) keeps both phases clean.
            to_convert = []  # (ep_num, ts_path)
            # Tried registering tqdm's shared lock in every worker thread
            # here (tqdm's documented fix for multi-threaded bar corruption)
            # but it deadlocked once episodes' nested per-segment executor
            # threads (in download_video.py) also touched that same lock -
            # reverted. Live-tested and confirmed to hang indefinitely.
            with ThreadPoolExecutor() as executor:
                future_to_episode = {
                    executor.submit(download_episode_with_fallback, ep_num, ep_idx, episodes, player_order, get_anime_name, save_dir, video_src, use_ts_threading, automatic_mp4, pre_selected_tool, args.no_mal, False, automatic_mp4): ep_num
                    for ep_num, ep_idx, video_src in zip(episode_numbers, episode_indices, video_sources)
                }
                for future in as_completed(future_to_episode):
                    ep_num = future_to_episode[future]
                    try:
                        success, output_path = future.result()
                        if not success:
                            failed_downloads += 1
                        elif automatic_mp4 and output_path and output_path.endswith('.ts'):
                            to_convert.append((ep_num, output_path))
                    except Exception as e:
                        print_status(f"Error ep {ep_num}: {e}", "error")
                        failed_downloads += 1

            total_episodes = len(episode_indices)
            downloaded_count = total_episodes - failed_downloads
            print_status(f"✅ {downloaded_count}/{total_episodes} episode(s) downloaded", "success")

            if to_convert:
                print_separator()
                print_status(f"🎬 Conversion .ts → .mp4 ({len(to_convert)} episode(s))", "info")
                print_separator()
                # Live-tested: converting these files one at a time takes
                # ~8-9s each, but running several PyAV conversions
                # concurrently made the whole batch take 10+ minutes with
                # almost no CPU progress. Each conversion reads its whole
                # multi-hundred-MB .ts file via av.open() with a large
                # probesize/analyzeduration - several of those happening at
                # once thrashes a spinning disk into near-random-access
                # territory instead of the fast sequential read a single
                # conversion gets, which dwarfs any benefit from
                # parallelism. Converting sequentially instead.
                for ep_num, ts_path in to_convert:
                    try:
                        success, _ = convert_episode_ts_to_mp4(ep_num, ts_path, pre_selected_tool)
                        if not success: failed_downloads += 1
                    except Exception as e:
                        print_status(f"Error converting ep {ep_num}: {e}", "error")
                        failed_downloads += 1
        else:
            for episode_num, ep_idx, video_source in zip(episode_numbers, episode_indices, video_sources):
                success, _ = download_episode_with_fallback(episode_num, ep_idx, episodes, player_order, get_anime_name, save_dir, video_source, use_ts_threading, automatic_mp4, pre_selected_tool, args.no_mal, interactive)
                if not success: failed_downloads += 1

        print_separator()
        if failed_downloads == 0:
            print_status("All downloads completed! 🎉", "success")
            if interactive and pause_at_end: input(f"{Colors.BOLD}Press Enter to exit...{Colors.ENDC}")
            return 0
        else:
            print_status(f"Completed with {failed_downloads} failed", "warning")
            if interactive and pause_at_end: input(f"{Colors.BOLD}Press Enter to exit...{Colors.ENDC}")
            return 1

    except KeyboardInterrupt:
        print_status("Interrupted", "error")
        return 1
    except Exception as e:
        print_status(f"Error: {e}", "error")
        return 1


def main():
    parser = argparse.ArgumentParser(formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--url", default=None)
    parser.add_argument("--search", default=None)
    parser.add_argument("--episodes", default=None)
    parser.add_argument("--player", default=None)
    parser.add_argument("--dest", default=None)
    parser.add_argument("--threads", action='store_true')
    parser.add_argument("--fast", action='store_true')
    parser.add_argument("--mp4", action='store_true')
    parser.add_argument("--tool", default=None)
    parser.add_argument("--no-mal", action='store_true', help="Disable MyAnimeList research")
    parser.add_argument("--latest", action='store_true', help="Download only the latest episode")

    
    args = parser.parse_args()
    interactive = len(sys.argv) == 1

    if not check_package(ask_install=True, first_run=True):
        print_status("Some required packages were missing. Would you like to install them now? (y/n): ", "warning")
        ask_user = input().strip().lower()
        if ask_user in ['y', 'yes', '1']:
            if not check_package(ask_install=True, first_run=False):
                print_status("Failed to install required packages. Please install them manually and re-run the script.", "error")
                sys.exit(1)
        else:
            print_status("Cannot proceed without required packages. Exiting.", "warning")
            input("Press Enter to exit...")
            sys.exit(1)

    if not check_ffmpeg_installed():
        print_status("FFmpeg is not installed or not found in the PATH. You could consider installing it from https://ffmpeg.org/download.html", "error")

    try:
        print_header()
        
        base_url = args.url
        season_urls = None

        if args.search and not base_url:
            results = search_anime(args.search, headers=headers)
            if not results:
                print_status("No results found for search query.", "error")
                return 1
            print(f"\n{Colors.BOLD}{Colors.HEADER}🔍 SEARCH RESULTS{Colors.ENDC}")
            print_separator()
            for i, res in enumerate(results, 1):
                support_text = ""
                if res.get('support') == "Anime Supported":
                    support_text = f" {Colors.OKGREEN}(Anime Supported){Colors.ENDC}"
                elif res.get('support') == "Scans Supported":
                    support_text = f" {Colors.OKGREEN}(Scans Supported){Colors.ENDC}"
                site_tag = f" [{res.get('site')}]" if res.get('site') else ""
                print(f"{Colors.OKCYAN}{i}. {res['title']}{site_tag}{support_text} ({res['url']}){Colors.ENDC}")
            
            while True:
                try:
                    choice = input(f"{Colors.BOLD}Select anime (1-{len(results)}): {Colors.ENDC}").strip()
                    if choice.isdigit():
                        idx = int(choice) - 1
                        if 0 <= idx < len(results):
                            base_url = results[idx]['url']
                            break
                    print_status("Invalid choice", "error")
                except KeyboardInterrupt:
                    return 1



        if not base_url:
            show_tutorial = input(f"{Colors.BOLD}Show tutorial? (y/n, default: n): {Colors.ENDC}").strip().lower()
            if show_tutorial in ['y', 'yes', '1']:
                print_tutorial()
                input(f"\n{Colors.BOLD}Press Enter to continue...{Colors.ENDC}")
            
            while True:
                print(f"\n{Colors.BOLD}{Colors.HEADER}🔗 ANIME-SAMA SELECTION{Colors.ENDC}")
                print_separator()
                print(f"{Colors.OKCYAN}1. Paste URL{Colors.ENDC}")
                print(f"{Colors.OKCYAN}2. Search Anime{Colors.ENDC}")
                print(f"{Colors.OKCYAN}3. Settings{Colors.ENDC}")
                mode = input(f"{Colors.BOLD}Choice (1/2/3): {Colors.ENDC}").strip()
                
                if mode == '1':
                    while True:
                        base_url = input(f"{Colors.BOLD}Enter the complete anime-sama URL: {Colors.ENDC}").strip()
                        if not base_url: continue
                        break
                    break
                elif mode == '2':
                    query = input(f"{Colors.BOLD}Enter search query: {Colors.ENDC}").strip()
                    results = search_anime(query, headers=headers)
                    if not results:
                        print_status("No results found.", "error")
                        continue
                    
                    print(f"\n{Colors.BOLD}{Colors.HEADER}🔍 SEARCH RESULTS{Colors.ENDC}")
                    print_separator()
                    for i, res in enumerate(results, 1):
                         support_text = ""
                         if res.get('support') == "Anime Supported":
                             support_text = f" {Colors.OKGREEN}(Anime Supported){Colors.ENDC}"
                         elif res.get('support') == "Scans Supported":
                             support_text = f" {Colors.OKGREEN}(Scans Supported){Colors.ENDC}"
                         elif res.get('support') == "Anime & Scans Supported":
                             support_text = f" {Colors.OKGREEN}(Anime & Scans Supported){Colors.ENDC}"
                         elif res.get('support') == "Unknown":
                             support_text = f" {Colors.FAIL}(Status Unknown){Colors.ENDC}"
                         site_tag = f" [{res.get('site')}]" if res.get('site') else ""
                         print(f"{Colors.OKCYAN}{i}. {res['title']}{site_tag}{support_text}{Colors.ENDC}")
                    
                    valid_choice = False
                    while True:
                        choice = input(f"{Colors.BOLD}Select anime (1-{len(results)}) or 'c' to cancel: {Colors.ENDC}").strip()
                        if choice.lower() == 'c': break
                        if choice.isdigit():
                            idx = int(choice) - 1
                            if 0 <= idx < len(results):
                                base_url = results[idx]['url']
                                options = expand_catalogue_url(base_url, headers=headers)
                                if options:
                                    anime_opts = []
                                    scan_opts = []
                                    for opt in options:
                                        if '/scan' in opt['url'].lower():
                                            scan_opts.append(opt)
                                        else:
                                            anime_opts.append(opt)
                                    
                                    options = anime_opts + scan_opts
                                    
                                    print(f"\n{Colors.BOLD}{Colors.HEADER}📅 AVAILABLE SEASONS/VERSIONS{Colors.ENDC}")
                                    print_separator()
                                    
                                    idx_counter = 1
                                    if anime_opts:
                                         print(f"{Colors.BOLD}--- Anime ---{Colors.ENDC}")
                                         for opt in anime_opts:
                                             print(f"{Colors.OKCYAN}{idx_counter}. {opt['name']} ({opt['url']}){Colors.ENDC}")
                                             idx_counter += 1
                                    
                                    if scan_opts:
                                         print(f"{Colors.BOLD}--- Scans ---{Colors.ENDC}")
                                         for opt in scan_opts:
                                             print(f"{Colors.OKBLUE}{idx_counter}. {opt['name']} ({opt['url']}){Colors.ENDC}")
                                             idx_counter += 1
                                    
                                    while True:
                                        s_choice = input(
                                            f"{Colors.BOLD}Select season(s) (1-{len(options)}, "
                                            "comma-separated example 1,2,3, ranges like 1-3, or 'all'): "
                                            f"{Colors.ENDC}"
                                        )
                                        s_indices = parse_selection_indices(s_choice, len(options))
                                        if s_indices:
                                            season_urls = [options[i]['url'] for i in s_indices]
                                            base_url = season_urls[0]
                                            valid_choice = True
                                            break
                                        print_status("Invalid choice", "error")
                                    if valid_choice:
                                        break
                                else:
                                    print_status("This page doesn't seem to contain any anime downloadable content.", "warning")
                                    continue
                    if valid_choice: 
                        break
                elif mode == '3':
                    settings_menu()
                else:
                    print_status("Invalid option", "error")
        
        is_valid, _ = validate_anime_sama_url(base_url)
        if not is_valid:
            print_status("Checking for seasons/versions...", "info")
            season_options = expand_catalogue_url(base_url, headers=headers)
            if season_options:
                anime_opts = []
                scan_opts = []
                for opt in season_options:
                     if '/scan' in opt['url'].lower():
                         scan_opts.append(opt)
                     else:
                         anime_opts.append(opt)
                
                season_options = anime_opts + scan_opts

                print(f"\n{Colors.BOLD}{Colors.HEADER}📅 AVAILABLE SEASONS/VERSIONS{Colors.ENDC}")
                print_separator()

                idx_counter = 1
                if anime_opts:
                        print(f"{Colors.BOLD}--- Anime ---{Colors.ENDC}")
                        for opt in anime_opts:
                            print(f"{Colors.OKCYAN}{idx_counter}. {opt['name']} ({opt['url']}){Colors.ENDC}")
                            idx_counter += 1
                
                if scan_opts:
                        print(f"{Colors.BOLD}--- Scans ---{Colors.ENDC}")
                        for opt in scan_opts:
                            print(f"{Colors.OKBLUE}{idx_counter}. {opt['name']} ({opt['url']}){Colors.ENDC}")
                            idx_counter += 1
                
                while True:
                    choice = input(
                        f"{Colors.BOLD}Select season(s) (1-{len(season_options)}, "
                        "comma-separated example 1,2,3, ranges like 1-3, or 'all'): "
                        f"{Colors.ENDC}"
                    )
                    indices = parse_selection_indices(choice, len(season_options))
                    if indices:
                        season_urls = [season_options[i]['url'] for i in indices]
                        base_url = season_urls[0]
                        break
                    print_status("Invalid choice", "error")
            else:
                 print_status("Could not find any seasons/versions. Please define one manually (url/saison...)", "warning")

        if season_urls is None:
            season_urls = [base_url]

        multi = len(season_urls) > 1
        overall_rc = 0
        for i, season_url in enumerate(season_urls):
            if multi:
                print(f"\n{Colors.BOLD}{Colors.HEADER}=== Saison {i + 1}/{len(season_urls)} ==={Colors.ENDC}")
            rc = process_season(season_url, args, headers, interactive, pause_at_end=not multi)
            if rc != 0:
                overall_rc = 1

        if multi and interactive:
            input(f"{Colors.BOLD}Press Enter to exit...{Colors.ENDC}")

        return overall_rc
    except Exception as e:
        print_status(f"Fatal: {e}", "error")
        return 1

if __name__ == "__main__":
    sys.exit(main())
