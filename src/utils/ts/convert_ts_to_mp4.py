import subprocess
import os
import sys
from src.var        import print_status

_FIX_TS_WORKER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_fix_ts_worker.py")
_FIX_TS_TIMEOUT = 180


def _run_fix_ts_with_timeout(input_path, output_path, timeout=_FIX_TS_TIMEOUT):
    """Run fix_ts() in a separate process with a hard timeout.

    fix_ts() (PyAV) has been observed to hang indefinitely on certain input
    files with the CPU sitting at 0% - a block inside the native av library
    itself, which a Python thread cannot be interrupted out of. A
    subprocess CAN be killed outright, so that's what enforces the limit.
    """
    try:
        result = subprocess.run(
            [sys.executable, _FIX_TS_WORKER, input_path, output_path],
            timeout=timeout,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.TimeoutExpired:
        raise TimeoutError(f"fix_ts timed out after {timeout}s (likely stuck in PyAV) - {input_path}")
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "fix_ts subprocess failed")

def convert_ts_to_mp4(input_path, output_path, pre_selected_tool=None):
    if not os.path.exists(input_path):
        print_status(f"Input file {input_path} does not exist", "error")
        return False, input_path
    if os.path.exists(output_path):
        print_status(f"Output file {output_path} already exists. deleting...", "error")
        try:
            os.remove(output_path)
        except Exception as e:
            print_status(f"Failed to delete existing output file: {e}", "error")
            return False, input_path
    if pre_selected_tool == 'ffmpeg':
        try:

            output_path = os.path.splitext(input_path)[0] + '.mp4'
            ffmpeg_cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-nostats",
            "-i", input_path,
            "-c:v", "copy",
            "-c:a", "copy",
            output_path
        ]
            print_status(f"Converting with FFmpeg: {os.path.basename(input_path)}", "loading")
            process = subprocess.run(ffmpeg_cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
            if process.stderr.strip():
                print_status(process.stderr.strip(), "warning")
            if process.returncode == 0:
                print_status(f"Video converted successfully to {output_path}", "success")
                return True, output_path
            else:
                print_status("FFmpeg conversion failed", "error")
                return False, input_path
        except Exception as e:
            print_status(f"FFmpeg conversion failed: {str(e)}", "error")
            return False, input_path
    
    elif pre_selected_tool == 'av':
        try:
            _run_fix_ts_with_timeout(input_path, output_path)
            print_status(f"Video converted successfully to {output_path}", "success")
            return True, output_path
        except Exception as e:
            print_status(f"AV conversion failed: {str(e)}", "error")
            try:
                from src.utils.check.check_ffmpeg_installed import check_ffmpeg_installed
                if check_ffmpeg_installed():
                    try:
                        ff_output = os.path.splitext(input_path)[0] + '.mp4'
                        ffmpeg_cmd = [
                            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-nostats",
                            "-i", input_path,
                            "-c:v", "copy",
                            "-c:a", "copy",
                            ff_output
                        ]
                        print_status(f"AV failed - falling back to FFmpeg: {os.path.basename(input_path)}", "loading")
                        process = subprocess.run(ffmpeg_cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
                        if process.stderr.strip():
                            print_status(process.stderr.strip(), "warning")
                        if process.returncode == 0:
                            print_status(f"Video converted successfully to {ff_output}", "success")
                            return True, ff_output
                        else:
                            print_status("FFmpeg fallback conversion failed", "error")
                            return False, input_path
                    except Exception as ff_e:
                        print_status(f"FFmpeg fallback failed: {str(ff_e)}", "error")
                        return False, input_path
                else:
                    print_status("FFmpeg not available for fallback", "error")
                    return False, input_path
            except Exception:
                return False, input_path

    else:
        print_status("No valid conversion tool specified", "error")
        return False, input_path
