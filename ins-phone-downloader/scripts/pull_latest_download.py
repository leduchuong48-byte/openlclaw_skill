#!/usr/bin/env python3
import argparse
import os
import re
from datetime import datetime
from pathlib import Path

import uiautomator2 as u2


def list_files(d, remote_dir: str):
    # Prefer recursive find because many downloaders save into subfolders like
    # /sdcard/Download/TweetDownloader/*.mp4
    cmds = [
        f'find "{remote_dir}" -maxdepth 2 -type f 2>/dev/null',
        f'find "{remote_dir}" -type f 2>/dev/null',
    ]
    paths = []
    for cmd in cmds:
        out = d.shell(cmd).output
        if out and ("Unknown option" not in out) and ("unknown predicate" not in out):
            for line in out.splitlines():
                line = line.strip()
                if not line:
                    continue
                if line.startswith("/"):
                    paths.append(line)
            if paths:
                break

    files = []
    for p in paths:
        name = Path(p).name
        files.append({"name": name, "remote": p})

    return files


def main():
    ap = argparse.ArgumentParser(description="Pull newest file from /sdcard/Download")
    ap.add_argument("--serial", default=os.environ.get("ANDROID_SERIAL", ""), help="ADB device serial")
    ap.add_argument("--remote-dir", default="/sdcard/Download", help="Remote download dir")
    ap.add_argument("--dest-dir", required=True, help="Local destination dir")
    ap.add_argument(
        "--ext",
        default="",
        help="Optional comma-separated ext filter, e.g. mp4,jpg,png. Leave empty to allow all.",
    )
    args = ap.parse_args()

    if not args.serial:
        raise SystemExit("--serial required (or set ANDROID_SERIAL)")

    d = u2.connect(args.serial)

    exts = [e.strip().lower().lstrip(".") for e in args.ext.split(",") if e.strip()]

    candidates = list_files(d, args.remote_dir)
    if exts:
        candidates = [c for c in candidates if c["name"].lower().split(".")[-1] in exts]

    if not candidates:
        raise SystemExit(f"no files in {args.remote_dir}")

    enriched = []
    for c in candidates:
        st = d.shell(f'stat -c "%Y %s" "{c["remote"]}" 2>/dev/null || echo "0 0"').output.strip().split()
        if len(st) == 2 and st[0].isdigit() and st[1].isdigit():
            mtime = int(st[0])
            size = int(st[1])
        else:
            mtime = 0
            size = 0
        enriched.append({**c, "mtime": mtime, "size": size})

    enriched.sort(key=lambda x: (x["mtime"], x["size"]), reverse=True)
    newest = enriched[0]

    dest_dir = Path(args.dest_dir).expanduser().resolve()
    dest_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    local_path = dest_dir / f"{ts}__{Path(newest['name']).name}"

    d.pull(newest["remote"], str(local_path))

    print(str(local_path))


if __name__ == "__main__":
    main()
