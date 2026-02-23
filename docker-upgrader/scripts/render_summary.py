#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


def short(s: str, n=12) -> str:
    if not s:
        return ""
    s = s.replace("sha256:", "")
    return s[:n]


def main():
    ap = argparse.ArgumentParser(description="Render a human summary from upgrade_container JSONL outputs")
    ap.add_argument("--jsonl", required=True, help="Path to JSONL file (one JSON per line)")
    ap.add_argument("--format", default="text", choices=["text", "markdown"], help="Output format")
    args = ap.parse_args()

    p = Path(args.jsonl)
    if not p.exists():
        raise SystemExit(f"jsonl not found: {p}")

    rows = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue

    ok = [r for r in rows if r.get("ok") is True]
    fail = [r for r in rows if r.get("ok") is False]

    def render_row(r):
        host = r.get("host", "local")
        name = r.get("container", "")
        tag = r.get("image_tag", "")
        before = short(r.get("image_before", ""))
        after = short(r.get("image_after", ""))
        rb = r.get("rolled_back")
        err = r.get("error", "")
        if r.get("ok") is True:
            return {
                "host": host,
                "container": name,
                "status": "OK",
                "image": tag,
                "before": before,
                "after": after,
                "rollback": "-",
                "error": "-",
            }
        return {
            "host": host,
            "container": name,
            "status": "FAIL",
            "image": tag or "-",
            "before": before,
            "after": after or "-",
            "rollback": "yes" if rb else "no",
            "error": (err[:120] + ("…" if len(err) > 120 else "")) if err else "-",
        }

    items = [render_row(r) for r in rows]

    if args.format == "markdown":
        print(f"升级汇总：成功 {len(ok)} / 失败 {len(fail)} / 总计 {len(rows)}")
        print("\n| 主机 | 容器 | 状态 | 镜像(tag) | before | after | 回滚 | 失败原因 |\n|---|---|---|---|---|---|---|---|")
        for it in items:
            print(
                f"| {it['host']} | {it['container']} | {it['status']} | {it['image']} | {it['before']} | {it['after']} | {it['rollback']} | {it['error']} |"
            )
        return

    # text
    print(f"升级汇总：成功 {len(ok)} / 失败 {len(fail)} / 总计 {len(rows)}")
    for it in items:
        line = (
            f"- [{it['host']}] {it['container']}: {it['status']} | {it['image']} | {it['before']} -> {it['after']}"
        )
        if it["status"] != "OK":
            line += f" | rollback={it['rollback']} | {it['error']}"
        print(line)


if __name__ == "__main__":
    main()
