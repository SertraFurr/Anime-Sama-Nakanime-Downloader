import subprocess

from src.var import print_status


def verify_video_file(path, timeout=30):
    """Sanity-check a downloaded/converted video file with ffprobe.

    Threaded batch downloads have been seen to silently produce corrupted
    output (e.g. "moov atom not found" on the .mp4, or a genuinely damaged
    source stream) while the tool still reported success - this catches
    that instead of leaving a broken file mistaken for a good download.

    Returns (True, None) if the file has a readable, non-zero duration,
    otherwise (False, reason).
    """
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                path,
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        # ffprobe not installed - can't verify, don't block on it
        return True, None
    except subprocess.TimeoutExpired:
        return False, "ffprobe timed out while reading the file"

    if result.returncode != 0:
        reason = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "ffprobe failed"
        return False, reason

    try:
        duration = float(result.stdout.strip())
    except (ValueError, TypeError):
        return False, "no duration reported (empty/corrupted file)"

    if duration <= 0:
        return False, f"invalid duration ({duration}s)"

    return True, None


def verify_or_warn(path, episode_num):
    """Verify a file and print a clear warning (but don't raise) on failure.

    Returns True/False so callers can decide whether to treat the episode
    as failed (e.g. to trigger a fallback-player retry) or just warn.
    """
    ok, reason = verify_video_file(path)
    if not ok:
        print_status(
            f"⚠️ Episode {episode_num} file failed verification ({reason}) - "
            f"the download likely got corrupted: {path}",
            "error",
        )
    return ok
