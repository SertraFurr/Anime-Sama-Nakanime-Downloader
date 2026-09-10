"""Standalone entry point for running fix_ts() in its own process.

Run as: python _fix_ts_worker.py <infile> <outfile>

fix_ts() (PyAV-based remux/encode) has been observed to hang indefinitely
on certain input files with no CPU usage - a genuine block inside the
native av library, not something Python-level code can interrupt (a
blocked thread can't be killed). Running it in a separate OS process
instead lets the caller enforce a hard timeout and kill it if needed.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from src.utils.ts.fix_ts import fix_ts

if __name__ == "__main__":
    infile, outfile = sys.argv[1], sys.argv[2]
    try:
        fix_ts(infile, outfile)
        sys.exit(0)
    except Exception as e:
        print(f"fix_ts failed: {e}", file=sys.stderr)
        sys.exit(1)
