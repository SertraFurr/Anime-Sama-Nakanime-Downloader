import os
import re
import requests
import threading
from tqdm                               import tqdm
from src.var                            import print_separator, print_status, Colors
from src.utils.download.download_video  import download_video
from src.utils.ts.convert_ts_to_mp4     import convert_ts_to_mp4
from src.utils.download.verify_video_file import verify_or_warn
import time

PREFIX_URL = "https://myanimelist.net/search/prefix.json"
TENRAI_EPISODES_URL = "https://api.tenrai.org/v1/anime/{id}/episodes?page={page}"
TENRAI_DETAILS_URL = "https://api.tenrai.org/v1/anime/{id}"

_mal_search_cache = {}
_cache_lock = threading.Lock()
# Tracks which anime we've already printed the "using cached MAL data"
# message for, so a multi-threaded batch download doesn't print it once
# per episode (it was flooding the interleaved progress bars).
_mal_cache_hit_announced = set()


def _fetch_mal_english_title(mal_id, timeout=10):
    """English title for a MAL entry, so the candidate picker isn't showing
    romaji-only names ("Enen no Shouboutai") to someone who doesn't read
    Japanese - falls back to None (caller just shows the romaji name alone)
    if the lookup fails or there's no English title on MAL for this entry."""
    try:
        resp = requests.get(TENRAI_DETAILS_URL.format(id=mal_id), timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError):
        return None
    return (data.get("data") or {}).get("title_english") or None


def _fetch_mal_episode_count(mal_id, timeout=15, max_pages=10):
    """Total episode count for a MAL entry, via the same Tenrai API the Plex
    plugin uses - needed to tell the user exactly where to split files
    between multiple MAL entries covering one downloaded season (e.g. a
    "Part 1" + "Part 2" pair on MAL for one season on the source site)."""
    total = 0
    page = 1
    while page <= max_pages:
        try:
            resp = requests.get(TENRAI_EPISODES_URL.format(id=mal_id, page=page), timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
        except (requests.RequestException, ValueError):
            return total if total else None

        items = data.get("data") or []
        total += len(items)

        pagination = data.get("pagination") or {}
        if not pagination.get("has_next_page"):
            break
        page += 1

    return total or None


_MONTH_NUM = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _air_date_sort_key(item):
    """(year, month, day) for a MAL search result, oldest first - used to
    order multi-part picks by real air date instead of selection order."""
    payload = item.get("payload", {}) or {}
    aired = payload.get("aired") or ""
    m = re.match(r"(\w{3})\s+(\d{1,2}),\s*(\d{4})", aired)
    if m:
        month = _MONTH_NUM.get(m.group(1).lower()[:3], 0)
        return (int(m.group(3)), month, int(m.group(2)))
    start_year = payload.get("start_year") or 0
    return (start_year, 0, 0)


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


_ORDINAL_WORDS = {
    2: "2nd", 3: "3rd", 4: "4th", 5: "5th", 6: "6th", 7: "7th", 8: "8th", 9: "9th", 10: "10th",
}


def _season_query_variants(anime_name, season_number):
    """Build MAL search queries that are more likely to hit the entry for
    this specific season/part rather than the base show (season 1).

    MAL has no single naming convention for sequels ("2nd Season", "Season
    2", "Part 2", a roman numeral, or a completely different subtitle are
    all common) so this tries the frequent patterns rather than guaranteeing
    a hit - search_anime_on_mal() still falls back to the plain name after.
    """
    if not season_number or season_number <= 1:
        return []
    ordinal = _ORDINAL_WORDS.get(season_number, f"{season_number}th")
    return [
        f"{anime_name} {ordinal} Season",
        f"{anime_name} Season {season_number}",
        f"{anime_name} S{season_number}",
        f"{anime_name} Part {season_number}",
        f"{anime_name} {season_number}",
    ]


def search_anime_on_mal(anime_name, interactive=True, alt_names=None, season_number=None):
    # Season-qualified cache key: downloading "Fire Force" saison1 and then
    # saison3 must not collide on the same cached MAL entry (season 1's),
    # which is what silently happened before this was added.
    cache_key = f"{anime_name.lower().strip()}::s{season_number or 1}"
    if cache_key in _mal_search_cache:
        print_status(f"Using cached MAL data for: {anime_name} (season {season_number or 1})", "info")
        return _mal_search_cache[cache_key]

    is_later_season = bool(season_number and season_number > 1)
    season_variants = _season_query_variants(anime_name, season_number)
    season_variant_keys = {v.lower().strip() for v in season_variants}

    seen = set()
    queries = []
    # For a later season, try the season-qualified query variants FIRST -
    # an exact match there is a real signal. The bare name (and alt names)
    # come after, purely as a fallback if none of the variants hit anything.
    for name in season_variants + [anime_name] + list(alt_names or []):
        key = name.lower().strip()
        if name and key not in seen:
            seen.add(key)
            queries.append(name)

    all_results = []
    for query in queries:
        print_status(f"Searching MAL for: {query}", "info")
        # Membership check (not position) so dedup shifting the list can't
        # mislabel a plain-name/alt-name query as a season-qualified one.
        query_is_season_variant = is_later_season and query.lower().strip() in season_variant_keys

        data = _fetch_prefix_json(query, media_type="anime")
        results = _flatten_categories(data, wanted_type="anime")
        if not results:
            continue
        all_results = results

        tv_series = [r for r in results if (r.get("payload", {}).get("media_type") or "").lower() in ["tv", "ona"]]
        other_types = [r for r in results if r not in tv_series]

        name_normalized = normalize(query)
        for item in tv_series + other_types:
            item_normalized = normalize(item.get("name"))
            if item_normalized != name_normalized:
                continue
            # For a later season, an exact match only means something when
            # it came from a season-qualified query ("Fire Force 3rd
            # Season"). An exact match from the bare anime_name OR an
            # alt_name (which can just as easily be the show's original/
            # Japanese title, e.g. "Enen no Shouboutai" for "Fire Force" -
            # still just identifies the base show, season-agnostic) always
            # points at whatever MAL calls the base entry, i.e. season 1 -
            # never trust it here regardless of what string it equals.
            if not query_is_season_variant and is_later_season:
                continue
            print_status(f"Found exact match: {item['name']}", "success")
            result = {
                "mal_id": item.get("id"),
                "title": item.get("name"),
                "type": item.get("payload", {}).get("media_type"),
            }
            _mal_search_cache[cache_key] = result
            return result

        # Auto-select on es_score only for a normal (season 1 / unknown
        # season) search. For a later season, a fuzzy top-score pick from a
        # bare-name/alt-name query is exactly the same "just resolves to the
        # base show" risk as the exact-match case above, and a fuzzy pick
        # against a season-qualified variant is too unreliable to trust
        # blindly either (the variant itself is a guess) - so later seasons
        # always fall through to the candidate picker below instead.
        if not query_is_season_variant and not is_later_season:
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

    # A wrong auto-pick here means the WHOLE season gets tagged under the
    # wrong show, so this always asks - even during an otherwise
    # non-interactive/threaded batch run - rather than silently skipping or
    # guessing. It only fires once per anime (result gets cached), so it
    # doesn't turn into a per-episode prompt storm.
    ask_for_confirmation = interactive or is_later_season

    if ask_for_confirmation:
        candidates = tv_series if tv_series else all_results
        print_status(
            f"No confident match for season {season_number or 1}. Candidates:" if is_later_season
            else "No exact match. Candidates:",
            "info",
        )
        for idx, item in enumerate(candidates):
            payload = item.get("payload", {})
            english_title = _fetch_mal_english_title(item.get("id"))
            name_display = f"{item['name']} ({english_title})" if english_title and english_title.lower() != item['name'].lower() else item['name']
            print(f"  [{idx}] {name_display} "
                  f"({payload.get('media_type')}, {payload.get('start_year')}, "
                  f"score {payload.get('score')})")

        try:
            # Some seasons on the source site cover more than one MAL entry
            # (e.g. a "Part 1" + "Part 2" pair) - comma-separated indices
            # picks several candidates instead of just one.
            choice = input("Select index, or several separated by commas (or blank to skip): ").strip()
        except EOFError:
            # No stdin available at all (fully headless/cron run) - can't ask,
            # so skip rather than crash the whole batch.
            print_status("No stdin available to confirm - skipping MAL match for this anime", "warning")
            _mal_search_cache[cache_key] = None
            return None

        if not choice:
            _mal_search_cache[cache_key] = None
            return None

        raw_indices = [c.strip() for c in choice.split(",") if c.strip()]
        if not all(c.isdigit() and int(c) < len(candidates) for c in raw_indices):
            _mal_search_cache[cache_key] = None
            return None

        selected_items = [candidates[int(c)] for c in raw_indices]
        if len(selected_items) > 1:
            # Always order multi-part picks by actual air date rather than
            # trusting the order the indices were typed in - otherwise a
            # "3,2" typo silently swaps which folder becomes "Part 1".
            selected_items.sort(key=_air_date_sort_key)

        if len(selected_items) == 1:
            selected = selected_items[0]
            result = {
                "mal_id": selected.get("id"),
                "title": selected.get("name"),
                "type": selected.get("payload", {}).get("media_type"),
            }
            _mal_search_cache[cache_key] = result
            return result

        # Multi-select: fetch each part's real episode count so the caller
        # can tell the user exactly where to split the downloaded files.
        parts = []
        for item in selected_items:
            mal_id = item.get("id")
            ep_count = _fetch_mal_episode_count(mal_id)
            parts.append({
                "mal_id": mal_id,
                "title": item.get("name"),
                "type": item.get("payload", {}).get("media_type"),
                "episode_count": ep_count,
            })
        result = {"parts": parts}
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

def create_match_file(save_dir, anime_name, interactive=True, alt_names=None, season_number=None):
    with _cache_lock:
        try:
            if not anime_name:
                print_status("Cannot create match file: anime_name is empty", "error")
                return

            match_file_path = os.path.join(save_dir, '.match')
            cache_key = f"{anime_name.lower().strip()}::s{season_number or 1}"
            
            if cache_key in _mal_search_cache:
                if cache_key not in _mal_cache_hit_announced:
                    _mal_cache_hit_announced.add(cache_key)
                    print_status(f"Using cached MAL data (already in memory)", "info")
                return
            
            # Multi-part case leaves save_dir itself without a .match (files
            # get manually sorted into the sibling "Part" folders instead) -
            # detect that already-done state via the first part folder.
            if os.path.exists(os.path.join(f"{save_dir} Part 1", ".match")):
                if cache_key not in _mal_cache_hit_announced:
                    _mal_cache_hit_announced.add(cache_key)
                    print_status(f"Multi-part match folders already exist for: {save_dir}", "info")
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
            
            mal_data = search_anime_on_mal(anime_name, interactive=interactive, alt_names=alt_names, season_number=season_number)

            if mal_data and "parts" in mal_data:
                print_separator()
                print_status(f"Multiple MAL entries selected for this season - creating one folder per part", "success")
                for i, part in enumerate(mal_data["parts"], start=1):
                    part_dir = f"{save_dir} Part {i}"
                    os.makedirs(part_dir, exist_ok=True)
                    with open(os.path.join(part_dir, ".match"), 'w', encoding='utf-8') as match_file:
                        match_file.write(f"title: {part['title']}\n")
                        match_file.write(f"mal-id: {part['mal_id']}\n")
                    count_str = str(part['episode_count']) if part['episode_count'] else "unknown - check MAL"
                    print_status(f"  → Part {i}: {part['title']} (mal-id {part['mal_id']}) - {count_str} episodes → {part_dir}", "info")
                print_separator()
                print_status(
                    f"Files downloaded to '{save_dir}' still need to be moved into the Part "
                    f"folders above by hand, using the episode counts printed for each part.",
                    "warning",
                )
                print_separator()
                return

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


def convert_episode_ts_to_mp4(episode_num, ts_path, pre_selected_tool=None):
    """Convert one already-downloaded .ts to .mp4, standalone from
    download_episode() - used to run the whole batch's conversions as a
    separate phase after every episode has finished downloading."""
    final_path = ts_path.replace('.ts', '.mp4')
    success, final_path = convert_ts_to_mp4(ts_path, final_path, pre_selected_tool)
    if not success:
        print_status(f"Conversion failed for episode {episode_num}, keeping .ts file: {ts_path}", "error")
        return False, ts_path

    try:
        os.remove(ts_path)
        removed_note = f"\n{Colors.OKBLUE}ℹ️ Removed temporary .ts file: {ts_path}{Colors.ENDC}"
    except Exception as e:
        removed_note = f"\n{Colors.WARNING}⚠️ Could not remove temporary .ts file: {str(e)}{Colors.ENDC}"
    tqdm.write(f"{Colors.OKGREEN}✅ Episode {episode_num} successfully saved to: {final_path}{Colors.ENDC}{removed_note}")
    if not verify_or_warn(final_path, episode_num):
        return False, final_path
    return True, final_path


def download_episode(episode_num, url, video_source, anime_name, save_dir, use_ts_threading=False, automatic_mp4=False, pre_selected_tool=None, no_mal=False, interactive=True, defer_conversion=False):
    if not video_source:
        print_status(f"Could not extract video source for episode {episode_num}", "error")
        return False, None
    
    season_dir = save_dir
    os.makedirs(season_dir, exist_ok=True)

    if no_mal:
        print_status("Skipping MAL matching (--no-mal)", "info")
    elif not anime_name:
        print_status("anime_name is empty, skipping MAL matching", "warning")
    else:
        create_match_file(season_dir, anime_name, interactive=interactive)

    save_path = os.path.join(season_dir, f"{anime_name if anime_name else 'episode'}_{episode_num}.mp4")

    # Batched into a single print() call: when several episodes download in
    # parallel threads, each separate print()/print_status() call is its own
    # stdout write, so another thread's lines can land in between them -
    # producing the garbled, out-of-order header blocks seen in threaded
    # batch runs. One call per block keeps each episode's header intact,
    # and one opening/closing separator (instead of one per sub-line) keeps
    # a whole episode's setup info as a single compact block.
    sep_line = "─" * 65
    header = (
        f"{Colors.OKBLUE}{Colors.BOLD}{sep_line}{Colors.ENDC}\n"
        f"{Colors.OKBLUE}ℹ️ Processing episode: {episode_num}{Colors.ENDC}\n"
        f"{Colors.OKBLUE}ℹ️ Source: {url[:60]}...{Colors.ENDC}\n"
        f"{Colors.BOLD}{Colors.HEADER}⬇️ DOWNLOADING EPISODE {episode_num}{Colors.ENDC}\n"
        f"{Colors.OKCYAN}⏳ Starting download: {os.path.basename(save_path)}{Colors.ENDC}\n"
        f"{Colors.OKBLUE}{Colors.BOLD}{sep_line}{Colors.ENDC}"
    )
    tqdm.write(header)

    try:
        success, output_path = download_video(video_source, save_path, use_ts_threading=use_ts_threading, url=url, automatic_mp4=automatic_mp4, interactive=interactive)
    except Exception as e:
        print_status(f"Download failed for episode {episode_num}: {str(e)}", "error")
        return False, None
    
    if not success:
        print_status(f"Failed to download episode {episode_num}", "error")
        return False, None
    
    if ('m3u8' in video_source or 'LULU_DEFERRED:' in video_source) and output_path and output_path.endswith('.ts'):
        if automatic_mp4 and defer_conversion:
            # Batch mode: conversion happens in a separate phase after every
            # episode's download has finished. No text is printed here - the
            # "Combined .../assembled N/M" messages from download_video.py
            # (deferred and flushed once the whole download phase is done)
            # already confirm success, and printing anything here would
            # interleave with OTHER episodes' still-active download bars,
            # which is what was corrupting the terminal display.
            return True, output_path
        tqdm.write(f"{Colors.OKBLUE}{Colors.BOLD}{sep_line}{Colors.ENDC}\n"
                   f"{Colors.OKGREEN}✅ Video saved as {output_path} (MPEG-TS format, playable in VLC or similar players){Colors.ENDC}")
        if automatic_mp4:
            success, final_path = convert_ts_to_mp4(output_path, save_path, pre_selected_tool)
            if success:
                removed_note = ""
                try:
                    os.remove(output_path)
                    removed_note = f"\n{Colors.OKBLUE}ℹ️ Removed temporary .ts file: {output_path}{Colors.ENDC}"
                except Exception as e:
                    removed_note = f"\n{Colors.WARNING}⚠️ Could not remove temporary .ts file: {str(e)}{Colors.ENDC}"
                tqdm.write(f"{Colors.OKGREEN}✅ Episode {episode_num} successfully saved to: {final_path}{Colors.ENDC}{removed_note}")
                if not verify_or_warn(final_path, episode_num):
                    return False, final_path
                return True, final_path
            else:
                print_status(f"Conversion failed for episode {episode_num}, keeping .ts file: {output_path}", "error")
                return False, output_path
        else:
            print_status(f"Keeping .ts file for episode {episode_num}: {output_path}", "info")
            if not verify_or_warn(output_path, episode_num):
                return False, output_path
            return True, output_path
    else:
        tqdm.write(f"{Colors.OKBLUE}{Colors.BOLD}{sep_line}{Colors.ENDC}\n"
                   f"{Colors.OKGREEN}✅ Episode {episode_num} successfully saved to: {save_path}{Colors.ENDC}")
        if not verify_or_warn(save_path, episode_num):
            return False, save_path
        return True, save_path
