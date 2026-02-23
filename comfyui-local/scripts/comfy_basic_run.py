#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Basic ComfyUI runner for a small, stable Flux T2I workflow.

- Submit a workflow JSON to /prompt
- Poll /history/<prompt_id>
- Download outputs via /view into workspace out/

Intentionally minimal: no PuLID/SUPIR/Detailer.
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_BASE = "http://127.0.0.1:8188"


def http_json(method: str, url: str, payload=None, timeout: int = 60) -> dict:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = ""
        try:
            raw = e.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        raise RuntimeError(f"HTTP {e.code}: {raw or e}")


def ensure_dir(p: str):
    os.makedirs(p, exist_ok=True)


def load_template(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def patch_prompt(workflow: dict, prompt: str) -> dict:
    wf = json.loads(json.dumps(workflow))
    # support CLIPTextEncodeFlux node id 4 by convention
    if "4" in wf and wf["4"].get("class_type") == "CLIPTextEncodeFlux":
        wf["4"].setdefault("inputs", {})
        wf["4"]["inputs"]["clip_l"] = prompt
        wf["4"]["inputs"]["t5xxl"] = prompt
    return wf


def view_url(base: str, filename: str, subfolder: str = "", typ: str = "output") -> str:
    q = {"filename": filename, "type": typ}
    if subfolder:
        q["subfolder"] = subfolder
    return base.rstrip("/") + "/view?" + urllib.parse.urlencode(q)


def download(url: str, dst: str, timeout: int = 180):
    ensure_dir(os.path.dirname(dst))
    with urllib.request.urlopen(url, timeout=timeout) as r:
        data = r.read()
    with open(dst, "wb") as f:
        f.write(data)


def run(base: str, template_path: str, prompt: str, out_dir: str, poll_seconds: int, poll_interval: int):
    base = base.rstrip("/")
    tpl = load_template(template_path)
    wf = patch_prompt(tpl, prompt)

    resp = http_json("POST", base + "/prompt", {"prompt": wf}, timeout=60)
    prompt_id = resp.get("prompt_id")
    if not prompt_id:
        raise RuntimeError(f"missing prompt_id: {resp}")

    deadline = time.time() + poll_seconds
    history = None
    while time.time() < deadline:
        h = http_json("GET", base + f"/history/{prompt_id}", None, timeout=30)
        history = h.get(prompt_id) if isinstance(h, dict) and prompt_id in h else h
        if history and history.get("outputs"):
            break
        time.sleep(poll_interval)

    if not history:
        raise RuntimeError("no history")

    outputs = history.get("outputs") or {}
    copied = []
    ensure_dir(out_dir)

    for _, out in outputs.items():
        imgs = out.get("images") or []
        for it in imgs:
            fn = it.get("filename")
            if not fn:
                continue
            sub = it.get("subfolder") or ""
            typ = it.get("type") or "output"
            url = view_url(base, fn, sub, typ)
            dst = os.path.join(out_dir, fn)
            download(url, dst)
            copied.append(dst)

    print("MANIFEST_JSON=" + json.dumps({"prompt_id": prompt_id, "copied_files": copied, "out_dir": out_dir}, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=DEFAULT_BASE)
    ap.add_argument("--template", default=os.path.join(os.path.dirname(__file__), "workflows", "flux-basic-t2i.json"))
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--out-dir", default="out/comfyui-local")
    ap.add_argument("--poll-seconds", type=int, default=600)
    ap.add_argument("--poll-interval", type=int, default=2)
    args = ap.parse_args()

    run(args.base, args.template, args.prompt, args.out_dir, args.poll_seconds, args.poll_interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
