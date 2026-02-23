#!/usr/bin/env python3
import argparse
import os
import shutil
from datetime import datetime
from pathlib import Path

def main():
    ap = argparse.ArgumentParser(description="Archive inbound media to NAS dir")
    ap.add_argument("--input-file", required=True, help="Path to inbound media file")
    ap.add_argument("--dest-dir", required=True, help="Destination directory")
    ap.add_argument("--copy", action="store_true", help="Copy instead of move")
    args = ap.parse_args()

    src = Path(args.input_file).expanduser().resolve()
    dest_dir = Path(args.dest_dir).expanduser().resolve()

    if not src.exists() or not src.is_file():
        raise SystemExit(f"input-file not found: {src}")

    dest_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    safe_name = src.name
    dest = dest_dir / f"{ts}__{safe_name}"

    if dest.exists():
        # Extremely unlikely with ts prefix; keep deterministic behavior.
        raise SystemExit(f"destination already exists: {dest}")

    if args.copy:
        shutil.copy2(src, dest)
    else:
        shutil.move(str(src), str(dest))

    print(str(dest))


if __name__ == "__main__":
    main()
