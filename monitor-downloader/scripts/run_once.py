#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import os
import re
import shutil
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple


DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")


def load_config(path: Optional[str]) -> dict:
    cfg_path = path or DEFAULT_CONFIG_PATH
    if os.path.exists(cfg_path):
        with open(cfg_path, "r", encoding="utf-8") as f:
            return json.load(f)
    # minimal defaults
    return {
        "sender_whitelist": [7856041838],
        "services": {
            "xhs": "http://192.168.100.21:1002",
            "weibo": "http://192.168.100.21:1003",
            "x": "http://192.168.100.21:2028",
        },
        "nfs_map": {},
        "out_dir": "out/monitor-downloader",
        "limits": {"max_files": 30, "max_total_mb": 500, "poll_seconds": 60, "poll_interval": 2},
    }


def http_json(method: str, url: str, payload: Optional[dict] = None, timeout: int = 20) -> dict:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            if not raw:
                return {}
            return json.loads(raw)
    except urllib.error.HTTPError as e:
        raw = ""
        try:
            raw = e.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        msg = raw
        try:
            j = json.loads(raw) if raw else {}
            msg = j.get("message") or j.get("detail") or raw
        except Exception:
            msg = raw or str(e)
        raise RuntimeError(f"HTTP {e.code}: {msg}")
    except socket.timeout:
        raise TimeoutError("socket timeout")


def extract_urls(text: str) -> List[str]:
    # simple URL extractor
    urls = re.findall(r"https?://[^\s<>\]\)]+", text)
    # de-dup while keeping order
    seen = set()
    out = []
    for u in urls:
        if u not in seen:
            out.append(u)
            seen.add(u)
    return out


def domain_of(url: str) -> str:
    try:
        return urllib.parse.urlparse(url).netloc.lower()
    except Exception:
        return ""


def route(url: str) -> Optional[str]:
    d = domain_of(url)
    if not d:
        return None
    if any(x in d for x in ["xiaohongshu.com", "xhslink.com"]):
        return "xhs"
    if any(x in d for x in ["weibo.com", "m.weibo.cn"]):
        return "weibo"
    if any(x in d for x in ["x.com", "twitter.com", "t.co"]):
        return "x"
    return None


def ensure_dir(p: str) -> None:
    os.makedirs(p, exist_ok=True)


def map_path(nfs_map: Dict[str, str], p: str) -> str:
    # map by longest prefix
    best_src = None
    for src in nfs_map.keys():
        if p.startswith(src) and (best_src is None or len(src) > len(best_src)):
            best_src = src
    if best_src:
        return nfs_map[best_src] + p[len(best_src) :]
    return p


def list_recent_files(root: str, seconds: int = 300) -> List[str]:
    now = time.time()
    out = []
    for dirpath, _, filenames in os.walk(root):
        for fn in filenames:
            fp = os.path.join(dirpath, fn)
            try:
                st = os.stat(fp)
            except FileNotFoundError:
                continue
            if now - st.st_mtime <= seconds:
                out.append(fp)
    out.sort(key=lambda p: os.stat(p).st_mtime, reverse=True)
    return out


def copy_files_to_out(paths: List[str], out_dir: str, max_files: int, max_total_mb: int) -> Tuple[str, List[str]]:
    job_id = str(int(time.time()))
    job_out = os.path.join(out_dir, job_id)
    ensure_dir(job_out)

    copied = []
    total = 0
    for p in paths:
        if not os.path.exists(p) or not os.path.isfile(p):
            continue
        size = os.stat(p).st_size
        if len(copied) >= max_files:
            break
        if total + size > max_total_mb * 1024 * 1024:
            break
        base = os.path.basename(p)
        dst = os.path.join(job_out, base)
        # avoid overwrite
        if os.path.exists(dst):
            root, ext = os.path.splitext(base)
            i = 2
            while True:
                dst = os.path.join(job_out, f"{root}_{i}{ext}")
                if not os.path.exists(dst):
                    break
                i += 1
        shutil.copy2(p, dst)
        copied.append(dst)
        total += size
    return job_out, copied


def poll_logs_for_paths(base: str, cursor0: int, poll_seconds: int, poll_interval: int, kind: str) -> List[str]:
    deadline = time.time() + poll_seconds
    extracted: List[str] = []

    # regexes
    if kind == "xhs":
        patterns = [
            # 路径里可能包含空格（例如话题标签之间），所以不能用 \S 简单截断
            re.compile(r"save image\s+(data/xhs/.*?\.(?:png|jpg|jpeg|webp))\s+success", re.IGNORECASE),
            re.compile(r"save video\s+(data/xhs/.*?\.(?:mp4|mov))\s+success", re.IGNORECASE),
        ]
    elif kind == "weibo":
        patterns = [
            re.compile(r"->\s*(/app/weibo_media/[^\s]+)"),
            re.compile(r"\b(/app/weibo_media/[^\s]+)"),
        ]
    else:
        patterns = []

    while time.time() < deadline:
        try:
            logs = http_json("GET", f"{base}/logs?since={cursor0}")
        except Exception:
            time.sleep(poll_interval)
            continue

        lines = []
        if isinstance(logs, dict):
            # common shapes: {logs:[...]} or {lines:[...]} or direct list under key
            for key in ["logs", "lines", "data"]:
                v = logs.get(key)
                if isinstance(v, list):
                    lines = [str(x) for x in v]
                    break
            if not lines and "result" in logs and isinstance(logs["result"], list):
                lines = [str(x) for x in logs["result"]]
        elif isinstance(logs, list):
            lines = [str(x) for x in logs]

        for line in lines:
            for pat in patterns:
                m = pat.search(line)
                if not m:
                    continue
                p = m.group(1)
                if p.startswith("data/xhs/"):
                    p = "/" + p
                extracted.append(p)
        if extracted:
            break
        time.sleep(poll_interval)

    # de-dup keep order
    seen = set()
    out = []
    for p in extracted:
        if p not in seen:
            out.append(p)
            seen.add(p)
    return out


def run_xhs(cfg: dict, url: str) -> List[str]:
    base = cfg["services"]["xhs"].rstrip("/")

    # 先 resolve：短链/分享链接 → 标准链接（保留 xsec_token/xsec_source）
    target = url
    try:
        resolved = http_json("POST", f"{base}/api/xhs/resolve", {"url": url})
        if isinstance(resolved, dict) and resolved.get("url"):
            target = str(resolved["url"])
    except Exception:
        # resolve 失败不阻断，继续用原链接
        target = url

    c0 = http_json("GET", f"{base}/logs/cursor").get("cursor", 0)

    # /run 默认 mode=creator；对“笔记链接”必须用 mode=detail，否则会报“目标不是用户主页链接”
    payload = {"target": target, "mode": "detail"}

    # /run 可能会阻塞很久（直到下载结束）；我们用短超时触发，超时视为“已启动”
    # 若已有任务在跑，先 stop 再重试一次
    try:
        http_json("POST", f"{base}/run", payload, timeout=3)
    except TimeoutError:
        pass
    except Exception as e:
        msg = str(e)
        if "已有任务正在运行" in msg:
            http_json("POST", f"{base}/task/stop", {})
            time.sleep(1)
            try:
                http_json("POST", f"{base}/run", payload, timeout=3)
            except TimeoutError:
                pass
        else:
            raise

    raw_paths = poll_logs_for_paths(
        base,
        int(c0),
        cfg["limits"]["poll_seconds"],
        cfg["limits"]["poll_interval"],
        "xhs",
    )

    mapped = []
    for p in raw_paths:
        # logs often contain /app/data/xhs or data/xhs; map to host prefix
        if p.startswith("/app/data/xhs/"):
            host_p = "/vol1/1000/media/素材/小红书" + p[len("/app/data/xhs") :]
        elif p.startswith("/data/xhs/"):
            host_p = "/vol1/1000/media/素材/小红书" + p[len("/data/xhs") :]
        else:
            host_p = p
        mapped.append(map_path(cfg.get("nfs_map", {}), host_p))
    return mapped


def run_weibo(cfg: dict, url: str) -> List[str]:
    base = cfg["services"]["weibo"].rstrip("/")
    c0 = http_json("GET", f"{base}/logs/cursor").get("cursor", 0)
    http_json("POST", f"{base}/download/single", {"url": url})
    raw_paths = poll_logs_for_paths(base, int(c0), cfg["limits"]["poll_seconds"], cfg["limits"]["poll_interval"], "weibo")

    mapped = []
    for p in raw_paths:
        if p.startswith("/app/weibo_media/"):
            host_p = "/vol1/1000/media/素材/微博" + p[len("/app/weibo_media") :]
        else:
            host_p = p
        mapped.append(map_path(cfg.get("nfs_map", {}), host_p))
    return mapped


def run_x(cfg: dict, url: str) -> List[str]:
    base = cfg["services"]["x"].rstrip("/")

    # xmonitor 没有 /logs/cursor；采用“触发前时间戳 + 扫描下载目录增量”的方式。
    t0 = time.time()
    try:
        http_json("POST", f"{base}/api/download", {"target_url": url, "options": None})
    except Exception as e:
        print(f"[x] trigger failed: {e}", file=sys.stderr)
        return []

    # 容器内默认 DOWNLOAD_DIR=/downloads；docker-compose 显示宿主机映射：/vol1/1000/media/素材/x -> /downloads
    # 我们直接扫本机 NFS 对应目录：/mnt/fnos_n97/media/素材/x
    candidates = [
        "/mnt/fnos_n97/media/素材/x",
    ]

    status_id = None
    m = re.search(r"/status/(\d+)", url)
    if m:
        status_id = m.group(1)

    deadline = time.time() + int(cfg["limits"].get("poll_seconds", 60))
    poll_interval = int(cfg["limits"].get("poll_interval", 2))
    found: List[str] = []
    while time.time() < deadline:
        for c in candidates:
            if not os.path.isdir(c):
                continue
            recent = [p for p in list_recent_files(c, seconds=int(cfg["limits"].get("poll_seconds", 60)))]
            media = [p for p in recent if os.path.splitext(p)[1].lower() in {".mp4", ".mov", ".jpg", ".jpeg", ".png", ".webp", ".gif"}]
            media = [p for p in media if os.stat(p).st_mtime >= t0 - 2]
            if status_id:
                media = [p for p in media if status_id in os.path.basename(p)]
            if media:
                found = media
                break
        if found:
            break
        time.sleep(poll_interval)

    # 兜底：即使 mtime 早于 t0，也允许按 status_id 精确命中
    if not found and status_id:
        for c in candidates:
            if not os.path.isdir(c):
                continue
            all_recent = list_recent_files(c, seconds=24 * 3600)
            hit = [p for p in all_recent if status_id in os.path.basename(p) and os.path.splitext(p)[1].lower() in {".mp4", ".mov", ".jpg", ".jpeg", ".png", ".webp", ".gif"}]
            if hit:
                found = hit
                break

    return found[: int(cfg["limits"].get("max_files", 30))]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sender-id", type=int, required=True)
    ap.add_argument("--text", type=str, required=True)
    ap.add_argument("--config", type=str, default=None)
    args = ap.parse_args()

    cfg = load_config(args.config)

    if args.sender_id not in set(cfg.get("sender_whitelist", [])):
        print("skip: sender not whitelisted")
        return 0

    urls = extract_urls(args.text)
    if not urls:
        print("skip: no url")
        return 0

    ensure_dir(cfg.get("out_dir", "out/monitor-downloader"))

    all_paths: List[str] = []
    for u in urls:
        kind = route(u)
        if not kind:
            continue
        print(f"route={kind} url={u}")
        if kind == "xhs":
            all_paths.extend(run_xhs(cfg, u))
        elif kind == "weibo":
            all_paths.extend(run_weibo(cfg, u))
        elif kind == "x":
            all_paths.extend(run_x(cfg, u))

    # keep only existing files
    # 去重：避免 xmonitor 多账号重复落盘导致回传重复文件
    existing = []
    seen_key = set()
    for p in all_paths:
        if not os.path.isfile(p):
            continue
        key = (os.path.basename(p), os.stat(p).st_size)
        if key in seen_key:
            continue
        seen_key.add(key)
        existing.append(p)

    if not existing:
        print("no files found (yet)")
        return 2

    job_out, copied = copy_files_to_out(
        existing,
        cfg.get("out_dir", "out/monitor-downloader"),
        int(cfg["limits"].get("max_files", 30)),
        int(cfg["limits"].get("max_total_mb", 500)),
    )

    manifest = {
        "job_out": job_out,
        "copied_files": copied,
    }

    print(f"job_out={job_out}")
    for p in copied:
        st = os.stat(p)
        print(f"copied {p} size={st.st_size}")

    print("MANIFEST_JSON=" + json.dumps(manifest, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
