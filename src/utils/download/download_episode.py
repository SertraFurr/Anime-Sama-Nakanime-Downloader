import os
import re
import requests
import threading
from src.var                            import print_separator, print_status, Colors
from src.utils.download.download_video  import download_video
from src.utils.ts.convert_ts_to_mp4     import convert_ts_to_mp4
import time

PREFIX_URL = "https://myanimelist.net/search/prefix.json"

_mal_search_cache = {}
_cache_lock = threading.Lock()
# Tracks which anime we've already printed the "using cached MAL data"
# message for, so a multi-threaded batch download doesn't print it once
# per episode (it was flooding the interleaved progress bars).
_mal_cache_hit_announced = set()


def normalize(text):
    if text is None: return ""
    return re.sub(r"[^\w\s]", "", str(text).lower().strip())

def _get_best_title(anime):
    titles = anime.get("titles", [])
    
    for title in titles:
        if title.get("type") == "English":
            return title.get("title") or ""
    
    for title in titles:
        if title.get("type") == "Default":
            return title.get("title") or ""
    
    if titles:
        return titles[0].get("title") or ""
    
    return anime.get("title") or "Unknown"

def _fetch_prefix_json(query, media_type="all", timeout=15.0, max_retries=5):
    params = {"type": media_type, "keyword": query, "v": 1}
 
    for attempt in range(max_retries):
        try:
            resp = requests.get(PREFIX_URL, params=params, timeout=timeout)
        except requests.RequestException as e:
            print_status(f"Request error (attempt {attempt + 1}): {e}", "warning")
            time.sleep(1.5 * (attempt + 1))
            continue
 
        if resp.status_code == 429:
            wait = 1.5 * (attempt + 1)
            print_status(f"Rate limited (429). Waiting {wait:.1f}s...", "warning")
            time.sleep(wait)
            continue
 
        break
 
    if resp is None or resp.status_code != 200:
        status = resp.status_code if resp is not None else "no response"
        print_status(f"Failed to fetch prefix.json (status: {status})", "warning")
        return None
 
    try:
        return resp.json()
    except ValueError:
        print_status("Failed to parse JSON response", "warning")
        return None
 
 
def _flatten_categories(data, wanted_type=None):
    if not data:
        return []
 
    results = []
    for category in data.get("categories", []):
        cat_type = category.get("type")
        if wanted_type and cat_type != wanted_type:
            continue
        for item in category.get("items", []):
            results.append(item)
    return results

def _auto_select_by_es_score(results, gap_ratio=2.0):
    if not results:
        return None

    if len(results) == 1:
        return results[0]

    scored = sorted(results, key=lambda r: r.get("es_score", 0), reverse=True)
    top, runner_up = scored[0], scored[1]

    top_score = top.get("es_score", 0)
    runner_up_score = runner_up.get("es_score", 0)

    if runner_up_score <= 0:
        return top

    if top_score >= runner_up_score * gap_ratio:
        return top

    return None


def search_anime_on_mal(anime_name, interactive=True, alt_names=None):
    cache_key = anime_name.lower().strip()
    if cache_key in _mal_search_cache:
        print_status(f"Using cached MAL data for: {anime_name}", "info")
        return _mal_search_cache[cache_key]

    seen = set()
    queries = []
    for name in [anime_name] + list(alt_names or []):
        key = name.lower().strip()
        if name and key not in seen:
            seen.add(key)
            queries.append(name)

    all_results = []
    for query in queries:
        print_status(f"Searching MAL for: {query}", "info")

        data = _fetch_prefix_json(query, media_type="anime")
        results = _flatten_categories(data, wanted_type="anime")
        if not results:
            continue
        all_results = results

        tv_series = [r for r in results if (r.get("payload", {}).get("media_type") or "").lower() in ["tv", "ona"]]
        other_types = [r for r in results if r not in tv_series]

        name_normalized = normalize(query)
        for item in tv_series + other_types:
            if normalize(item.get("name")) == name_normalized:
                print_status(f"Found exact match: {item['name']}", "success")
                result = {
                    "mal_id": item.get("id"),
                    "title": item.get("name"),
                    "type": item.get("payload", {}).get("media_type"),
                }
                _mal_search_cache[cache_key] = result
                return result

        auto_match = _auto_select_by_es_score(results)
        if auto_match:
            print_status(f"Auto-selected top result: {auto_match['name']}", "success")
            result = {
                "mal_id": auto_match.get("id"),
                "title": auto_match.get("name"),
                "type": auto_match.get("payload", {}).get("media_type"),
            }
            _mal_search_cache[cache_key] = result
            return result

    if not all_results:
        print_status(f"No results found for '{anime_name}'", "warning")
        _mal_search_cache[cache_key] = None
        return None

    tv_series = [r for r in all_results if (r.get("payload", {}).get("media_type") or "").lower() in ["tv", "ona"]]

    if interactive:
        candidates = tv_series if tv_series else all_results
        print_status("No exact match. Candidates:", "info")
        for idx, item in enumerate(candidates):
            payload = item.get("payload", {})
            print(f"  [{idx}] {item['name']} "
                  f"({payload.get('media_type')}, {payload.get('start_year')}, "
                  f"score {payload.get('score')})")

        choice = input("Select index (or blank to skip): ").strip()
        if not choice.isdigit() or int(choice) >= len(candidates):
            _mal_search_cache[cache_key] = None
            return None

        selected = candidates[int(choice)]
        result = {
            "mal_id": selected.get("id"),
            "title": selected.get("name"),
            "type": selected.get("payload", {}).get("media_type"),
        }
        _mal_search_cache[cache_key] = result
        return result
    else:
        first_item = tv_series[0] if tv_series else all_results[0]
        print_status(f"Using first result: {first_item['name']}", "info")
        result = {
            "mal_id": first_item.get("id"),
            "title": first_item.get("name"),
            "type": first_item.get("payload", {}).get("media_type"),
        }
        _mal_search_cache[cache_key] = result
        return result

def create_match_file(save_dir, anime_name, interactive=True, alt_names=None):
    with _cache_lock:
        try:
            if not anime_name:
                print_status("Cannot create match file: anime_name is empty", "error")
                return
            
            match_file_path = os.path.join(save_dir, '.match')
            cache_key = anime_name.lower().strip()
            
            if cache_key in _mal_search_cache:
                if cache_key not in _mal_cache_hit_announced:
                    _mal_cache_hit_announced.add(cache_key)
                    print_status(f"Using cached MAL data (already in memory)", "info")
                return
            
            if os.path.exists(match_file_path):
                print_status(f"Match file already exists: {match_file_path}", "info")
                
                try:
                    with open(match_file_path, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                        mal_id = None
                        title = None
                        for line in lines:
                            if line.startswith('mal-id:'):
                                mal_id_str = line.split(':', 1)[1].strip()
                                if mal_id_str != 'unknown':
                                    mal_id = int(mal_id_str)
                            elif line.startswith('title:'):
                                title = line.split(':', 1)[1].strip()
                        
                        if mal_id and title:
                            _mal_search_cache[cache_key] = {
                                "mal_id": mal_id,
                                "title": title,
                                "type": "TV"
                            }
                            print_status(f"Loaded MAL data from existing file into cache", "info")
                        else:
                            _mal_search_cache[cache_key] = None
                except Exception as e:
                    print_status(f"Could not read existing match file: {e}", "warning")
                    _mal_search_cache[cache_key] = None
                
                return
            
            print_separator()
            print(f"{Colors.BOLD}{Colors.HEADER}🔍 Searching for anime on MyAnimeList...{Colors.ENDC}")
            print_separator()
            
            mal_data = search_anime_on_mal(anime_name, interactive=interactive, alt_names=alt_names)
            
            if mal_data:
                with open(match_file_path, 'w', encoding='utf-8') as match_file:
                    match_file.write(f"title: {mal_data['title']}\n")
                    match_file.write(f"mal-id: {mal_data['mal_id']}\n")
                
                print_separator()
                print_status(f"✓ Match file created: {match_file_path}", "success")
                print_status(f"  → Title: {mal_data['title']}", "info")
                print_status(f"  → MAL ID: {mal_data['mal_id']}", "info")
                print_status(f"  → Type: {mal_data['type']}", "info")
                print_separator()
            else:
                with open(match_file_path, 'w', encoding='utf-8') as match_file:
                    match_file.write(f"title: {anime_name}\n")
                    match_file.write("mal-id: unknown\n")
                
                print_separator()
                print_status(f"Match file created with default values: {match_file_path}", "warning")
                print_status(f"Could not find or match anime on MAL", "warning")
                print_separator()
                
        except Exception as e:
            print_status(f"Error creating match file: {str(e)}", "error")


def download_episode(episode_num, url, video_source, anime_name, save_dir, use_ts_threading=False, automatic_mp4=False, pre_selected_tool=None, no_mal=False, interactive=True):
    if not video_source:
        print_status(f"Could not extract video source for episode {episode_num}", "error")
        return False, None
    
    print_separator()
    print_status(f"Processing episode: {episode_num}", "info")
    print_status(f"Source: {url[:60]}...", "info")
    
    season_dir = save_dir
    os.makedirs(season_dir, exist_ok=True)

    if no_mal:
        print_status("Skipping MAL matching (--no-mal)", "info")
    elif not anime_name:
        print_status("anime_name is empty, skipping MAL matching", "warning")
    else:
        create_match_file(season_dir, anime_name, interactive=interactive)
    
    save_path = os.path.join(season_dir, f"{anime_name if anime_name else 'episode'}_{episode_num}.mp4")
    
    print(f"\n{Colors.BOLD}{Colors.HEADER}⬇️ DOWNLOADING EPISODE {episode_num}{Colors.ENDC}")
    print_separator()
    
    try:
        success, output_path = download_video(video_source, save_path, use_ts_threading=use_ts_threading, url=url, automatic_mp4=automatic_mp4, interactive=interactive)
    except Exception as e:
        print_status(f"Download failed for episode {episode_num}: {str(e)}", "error")
        return False, None
    
    if not success:
        print_status(f"Failed to download episode {episode_num}", "error")
        return False, None
    
    print_separator()
    
    if ('m3u8' in video_source or 'LULU_DEFERRED:' in video_source) and output_path and output_path.endswith('.ts'):
        print_status(f"Video saved as {output_path} (MPEG-TS format, playable in VLC or similar players)", "success")
        if automatic_mp4:
            success, final_path = convert_ts_to_mp4(output_path, save_path, pre_selected_tool)
            if success:
                print_status(f"Episode {episode_num} successfully saved to: {final_path}", "success")
                try:
                    os.remove(output_path)
                    print_status(f"Removed temporary .ts file: {output_path}", "info")
                except Exception as e:
                    print_status(f"Could not remove temporary .ts file: {str(e)}", "warning")
                return True, final_path
            else:
                print_status(f"Conversion failed for episode {episode_num}, keeping .ts file: {output_path}", "error")
                return False, output_path
        else:
            print_status(f"Keeping .ts file for episode {episode_num}: {output_path}", "info")
            return True, output_path
    else:
        print_status(f"Episode {episode_num} successfully saved to: {save_path}", "success")
        return True, save_path
