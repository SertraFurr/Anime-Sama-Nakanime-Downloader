from src.var                                     import print_status, SourceDomains
from src.utils.fetch.fetch_video_source          import fetch_video_source
from src.utils.download.download_episode         import download_episode


def download_episode_with_fallback(episode_num, episode_index, episodes, player_order, anime_name, save_dir,
                                    primary_video_source=None, use_ts_threading=False, automatic_mp4=False,
                                    pre_selected_tool=None, no_mal=False, interactive=True, defer_conversion=False):
    for i, player in enumerate(player_order):
        urls_for_player = episodes.get(player)
        if not urls_for_player or episode_index >= len(urls_for_player):
            continue

        url = urls_for_player[episode_index]
        if not url or not any(source in url.lower() for source in SourceDomains.PLAYERS):
            continue

        if i == 0 and primary_video_source:
            video_source = primary_video_source
        else:
            if i > 0:
                print_status(f"Trying fallback player '{player}' for episode {episode_num}...", "info")
            video_source = fetch_video_source(url)

        if not video_source:
            print_status(f"[{player}] Could not extract video source for episode {episode_num}", "warning")
            continue

        success, output_path = download_episode(episode_num, url, video_source, anime_name, save_dir,
                                                  use_ts_threading, automatic_mp4, pre_selected_tool, no_mal, interactive,
                                                  defer_conversion=defer_conversion)
        if success:
            return True, output_path

        print_status(f"[{player}] Download failed for episode {episode_num}", "warning")

    print_status(f"All available players failed for episode {episode_num}", "error")
    return False, None
