#!/usr/bin/env python3
import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import uiautomator2 as u2

STAMP_RE = re.compile(r"_(\d{8}_\d{6})\.(jpg|jpeg|png|mp4)$", re.IGNORECASE)
RES_RE = re.compile(r"_(\d+)x(\d+)_")


def _shell(d, cmd: str) -> str:
    return d.shell(cmd).output or ""


def _find_files(d, remote_dir: str) -> list[str]:
    # Only current folder; TweetDownloader writes flat in practice.
    out = _shell(d, f'find "{remote_dir}" -maxdepth 1 -type f 2>/dev/null')
    paths = [ln.strip() for ln in out.splitlines() if ln.strip().startswith("/")]
    return paths


def _stat_mtime_size(d, remote_path: str) -> tuple[int, int]:
    out = _shell(d, f'stat -c "%Y %s" "{remote_path}" 2>/dev/null || echo "0 0"').strip().split()
    if len(out) == 2 and out[0].isdigit() and out[1].isdigit():
        return int(out[0]), int(out[1])
    return 0, 0


def _pick_highest_res(filenames: list[str]) -> str:
    def key(fn: str):
        m = RES_RE.search(fn)
        if not m:
            return (0, 0)
        return (int(m.group(1)), int(m.group(2)))

    return max(filenames, key=key)


def _group_key(filename: str, stamp: str) -> str:
    # Examples:
    # shark199607_10_1080x1134_<stamp>.jpg
    # shark199607_750x787_<stamp>.jpg (no index)
    m = re.match(r"^(.*?)(?:_(\d+))?_(\d+)x(\d+)_" + re.escape(stamp) + r"\.[^.]+$", filename)
    if not m:
        return "_ungrouped"
    prefix = m.group(1)
    idx = m.group(2) or "_noidx"
    return f"{prefix}_{idx}"


def detect_latest_stamp(d, remote_dir: str) -> str:
    paths = _find_files(d, remote_dir)
    best_stamp = ""
    best_mtime = -1

    for p in paths:
        name = Path(p).name
        m = STAMP_RE.search(name)
        if not m:
            continue
        stamp = m.group(1)
        mtime, _ = _stat_mtime_size(d, p)
        if mtime > best_mtime:
            best_mtime = mtime
            best_stamp = stamp

    if not best_stamp:
        raise SystemExit(f"no stamp-like files found in {remote_dir}")
    return best_stamp


def main():
    ap = argparse.ArgumentParser(
        description="Pull a TweetDownloader batch: select highest resolution per item and pull to local folder"
    )
    ap.add_argument("--serial", default=os.environ.get("ANDROID_SERIAL", ""), help="Device serial")
    ap.add_argument("--remote-dir", default="/sdcard/Download/TweetDownloader", help="Remote TweetDownloader dir")
    ap.add_argument("--dest-dir", required=True, help="Local directory to store pulled files")
    ap.add_argument(
        "--stamp",
        default="",
        help="Batch stamp like 20260223_001602. If empty, auto-detect newest.",
    )
    ap.add_argument(
        "--ext",
        default="jpg,jpeg,png,mp4",
        help="Comma-separated allowed extensions",
    )
    ap.add_argument(
        "--json",
        action="store_true",
        help="Output MANIFEST_JSON=...",
    )
    args = ap.parse_args()

    if not args.serial:
        raise SystemExit("--serial required (or set ANDROID_SERIAL)")

    d = u2.connect(args.serial)

    stamp = args.stamp.strip() or detect_latest_stamp(d, args.remote_dir)

    allowed_ext = {e.strip().lower().lstrip(".") for e in args.ext.split(",") if e.strip()}

    paths = _find_files(d, args.remote_dir)
    candidates = []
    for p in paths:
        name = Path(p).name
        if stamp not in name:
            continue
        ext = name.lower().split(".")[-1]
        if allowed_ext and ext not in allowed_ext:
            continue
        candidates.append((name, p))

    if not candidates:
        raise SystemExit(f"no files for stamp={stamp} in {args.remote_dir}")

    grouped: dict[str, list[str]] = {}
    remote_by_name: dict[str, str] = {}
    for name, remote in candidates:
        remote_by_name[name] = remote
        gk = _group_key(name, stamp)
        if gk == "_ungrouped":
            continue
        grouped.setdefault(gk, []).append(name)

    selected_names = []
    for gk, names in grouped.items():
        selected_names.append(_pick_highest_res(names))

    # Stable ordering: by optional index then name
    def order_key(n: str):
        m = re.search(r"_(\d+)_", n)
        return (int(m.group(1)) if m else 999999, n)

    selected_names.sort(key=order_key)

    dest_dir = Path(args.dest_dir).expanduser().resolve()
    dest_dir.mkdir(parents=True, exist_ok=True)

    pulled_files = []
    for name in selected_names:
        remote = remote_by_name[name]
        local = dest_dir / f"{stamp}__{name}"
        d.pull(remote, str(local))
        pulled_files.append(str(local))

    manifest = {
        "stamp": stamp,
        "remote_dir": args.remote_dir,
        "pulled_files": pulled_files,
        "count": len(pulled_files),
        "ts_utc": datetime.now(timezone.utc).isoformat(),
    }

    if args.json:
        print("MANIFEST_JSON=" + json.dumps(manifest, ensure_ascii=False))
    else:
        print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
