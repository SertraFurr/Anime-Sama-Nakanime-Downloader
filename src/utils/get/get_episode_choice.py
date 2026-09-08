from src.var import Colors, print_status, print_separator, SourceDomains

def get_episode_choice(episodes, player_choice):
    print(f"\n{Colors.BOLD}{Colors.HEADER}📺 SELECT EPISODE - {player_choice}{Colors.ENDC}")
    print_separator()

    num_episodes = len(episodes[player_choice])
    working_episodes = []

    source_types = {}
    for domain in SourceDomains.PLAYERS:
         source_types[domain] = SourceDomains.DISPLAY_NAMES.get(domain, domain.capitalize())

    for i, url in enumerate(episodes[player_choice], 1):
        if url is None:
            print(f"{Colors.FAIL}  {i:2d}. Episode {i} - Unavailable ❌{Colors.ENDC}")
            continue

        url_lower = url.lower()
        found_type = None

        if SourceDomains.is_voe_url(url, category=player_choice):
            found_type = "Voe"
        else:
            for key, value in source_types.items():
                if key in url_lower:
                    found_type = value
                    break

        if found_type:
            working_episodes.append(i)
            print(f"{Colors.OKGREEN}  {i:2d}. Episode {i} - {found_type} ✅{Colors.ENDC}")
        else:
            print(f"{Colors.FAIL}  {i:2d}. Episode {i} - Deprecated ❌{Colors.ENDC}")

    if not working_episodes:
        print_status("No working episodes found for this player!", "error")
        return None

    print(f"\n{Colors.OKCYAN}Available episodes: {len(working_episodes)} out of {num_episodes}{Colors.ENDC}")

    while True:
        try:
            episode_input = input(
                f"\n{Colors.BOLD}Enter episode number(s) (1-{num_episodes}, "
                "comma-separated example 1,2,3, ranges like 12-49, or 'all' for all available): "
                f"{Colors.ENDC}"
            ).strip().lower()

            if episode_input == 'all':
                valid_episodes = []
                for i in range(num_episodes):
                    episode_url = episodes[player_choice][i]
                    if episode_url and not ('vk.com' in episode_url or 'myvi.tv' in episode_url):
                        valid_episodes.append(i)

                if not valid_episodes:
                    print_status("No valid episodes available for download", "error")
                    continue
                return valid_episodes

            valid_episodes = []
            seen = set()

            for part in episode_input.split(','):
                part = part.strip()
                if not part:
                    continue

                if '-' in part:
                    start, end = map(int, part.split('-', 1))
                    for num in range(start, end + 1):
                        if num in seen:
                            continue
                        seen.add(num)

                        if 1 <= num <= num_episodes:
                            episode_url = episodes[player_choice][num - 1]
                            if episode_url is None:
                                print_status(f"Episode {num} is unavailable for this player", "error")
                            elif 'vk.com' in episode_url or 'myvi.tv' in episode_url:
                                print_status(f"Episode {num} source is deprecated and cannot be downloaded", "error")
                            else:
                                valid_episodes.append(num - 1)
                        else:
                            print_status(f"Episode number {num} is out of range (1-{num_episodes})", "error")
                else:
                    num = int(part)
                    if num in seen:
                        continue
                    seen.add(num)

                    if 1 <= num <= num_episodes:
                        episode_url = episodes[player_choice][num - 1]
                        if episode_url is None:
                            print_status(f"Episode {num} is unavailable for this player", "error")
                        elif 'vk.com' in episode_url or 'myvi.tv' in episode_url:
                            print_status(f"Episode {num} source is deprecated and cannot be downloaded", "error")
                        else:
                            valid_episodes.append(num - 1)
                    else:
                        print_status(f"Episode number {num} is out of range (1-{num_episodes})", "error")

            if valid_episodes:
                return valid_episodes
            else:
                print_status("No valid episodes selected", "error")

        except KeyboardInterrupt:
            print_status("\nOperation cancelled by user", "error")
            return None
        except ValueError:
            print_status("Invalid input. Please enter numbers, ranges (e.g. 12-49), or 'all'.", "error")
