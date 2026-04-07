#!/usr/bin/env python3
"""
Lightweight monitor that displays per-book progress bars by reading
`logs/<db>/status.txt` files written by the ingestion step.

Usage:
  python scripts/monitor_tqdm.py --logs logs --poll 1

This avoids adding external deps. If `tqdm` is installed it will use it,
otherwise it draws simple ASCII progress bars.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from typing import Dict, Optional, Tuple


def format_secs(s: int) -> str:
    h = s // 3600
    m = (s % 3600) // 60
    sec = s % 60
    return f"{h:02d}:{m:02d}:{sec:02d}"


def read_status(status_path: str) -> Optional[Tuple[float, int, int, int]]:
    """Read status.txt and return (started_at, cur, total, elapsed_s).
    Returns None if file can't be parsed.
    """
    try:
        with open(status_path, "r") as f:
            text = f.read()
    except Exception:
        return None

    started_at = None
    cur = 0
    total = 0
    elapsed_s = 0
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("started_at:"):
            try:
                started_at = float(line.split("started_at:", 1)[1].strip())
            except Exception:
                started_at = None
        elif line.startswith("chunk:"):
            # example: chunk: 2/52 elapsed_s: 702
            parts = line.split()
            try:
                # parts[1] is like '2/52'
                cur_tot = parts[1]
                cur_s, tot_s = cur_tot.split("/")
                cur = int(cur_s)
                total = int(tot_s)
                # find elapsed_s if present
                if "elapsed_s:" in line:
                    try:
                        elapsed_s = int(parts[3])
                    except Exception:
                        elapsed_s = 0
            except Exception:
                pass

    if started_at is None:
        return None
    return (started_at, cur, total, elapsed_s)


def draw_bar(cur: int, total: int, width: int = 30) -> str:
    if total <= 0:
        return "[" + " " * width + "]"
    frac = min(max(cur / total, 0.0), 1.0)
    filled = int(round(frac * width))
    bar = "#" * filled + "-" * (width - filled)
    return f"[{bar}] {cur}/{total}"


def scan_logs_dir(logs_dir: str) -> Dict[str, str]:
    """Return mapping db_name -> status_path for subdirs that contain status.txt"""
    out = {}
    if not os.path.isdir(logs_dir):
        return out
    for name in sorted(os.listdir(logs_dir)):
        sub = os.path.join(logs_dir, name)
        if not os.path.isdir(sub):
            continue
        st = os.path.join(sub, "status.txt")
        if os.path.isfile(st):
            out[name] = st
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--logs", default="logs", help="Logs directory (default: logs)")
    p.add_argument("--poll", type=float, default=1.0, help="Polling interval in seconds")
    p.add_argument("--db", default=None, help="(optional) monitor only this DB (subdir name) with a single-line progress bar")
    args = p.parse_args()

    logs_dir = args.logs

    try:
        if args.db:
            # Focused single-line monitor for one DB (prints in-place)
            status_path = os.path.join(logs_dir, args.db, "status.txt")
            if not os.path.isfile(status_path):
                print(f"Status file not found for DB '{args.db}' at {status_path}")
                sys.exit(1)
            while True:
                stat = read_status(status_path)
                now = time.time()
                if stat is None:
                    line = f"{args.db}  status: unreadable"
                else:
                    started_at, cur, total, elapsed_s = stat
                    if elapsed_s and elapsed_s > 0:
                        el = int(elapsed_s)
                    else:
                        el = int(now - started_at)
                    bar = draw_bar(cur, total, width=30)
                    eta = "--:--:--"
                    if total > 0 and cur > 0:
                        rate = cur / max(1, el)
                        remain = max(0, total - cur)
                        eta_s = int(remain / max(1e-6, rate))
                        eta = format_secs(eta_s)
                    line = f"{args.db} {bar} elapsed={format_secs(el)} ETA={eta}"
                # print single-line in-place
                sys.stdout.write("\r" + line + "\033[K")
                sys.stdout.flush()
                time.sleep(args.poll)

        else:
            while True:
                # find status files
                db_to_status = scan_logs_dir(logs_dir)
                now = time.time()

                # header
                os.system("clear")
                print(f"Monitoring {len(db_to_status)} jobs in '{logs_dir}' (press Ctrl-C to exit)")
                print("" + "=" * 80)

                if not db_to_status:
                    print("No status files found. Waiting...")
                else:
                    for db, stpath in db_to_status.items():
                        stat = read_status(stpath)
                        if stat is None:
                            print(f"{db:40s}  status: unreadable")
                            continue
                        started_at, cur, total, elapsed_s = stat
                        # prefer elapsed from status file; otherwise compute from started_at
                        if elapsed_s and elapsed_s > 0:
                            el = int(elapsed_s)
                        else:
                            el = int(now - started_at)

                        bar = draw_bar(cur, total, width=36)
                        # attempt ETA if progress > 0
                        eta = "--:--:--"
                        if total > 0 and cur > 0:
                            rate = cur / max(1, el)
                            remain = max(0, total - cur)
                            eta_s = int(remain / max(1e-6, rate))
                            eta = format_secs(eta_s)

                        print(f"{db:40s} {bar}  elapsed={format_secs(el)}  ETA={eta}")

                # footer
                print("" + "=" * 80)
                time.sleep(args.poll)
    except KeyboardInterrupt:
        print("\nExiting monitor")


if __name__ == "__main__":
    main()
