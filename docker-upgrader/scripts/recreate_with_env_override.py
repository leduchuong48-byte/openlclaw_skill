#!/usr/bin/env python3
import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone


def sh(cmd: list[str], check=True) -> str:
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if check and p.returncode != 0:
        raise RuntimeError(f"cmd failed: {' '.join(cmd)}\n{p.stdout}")
    return p.stdout


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_inspect(name: str) -> dict:
    raw = sh(["docker", "inspect", name])
    return json.loads(raw)[0]


def parse_kv(s: str) -> tuple[str, str]:
    if "=" not in s:
        raise ValueError(f"invalid --set {s}, expected KEY=VALUE")
    k, v = s.split("=", 1)
    return k, v


def health_status(name: str) -> str:
    out = sh([
        "docker",
        "inspect",
        name,
        "--format",
        "{{if .State.Health}}{{.State.Health.Status}}{{else}}no-health{{end}}",
    ], check=False).strip()
    return out


def state_running(name: str) -> bool:
    out = sh(["docker", "inspect", name, "--format", "{{.State.Running}}"], check=False).strip()
    return out == "true"


def wait_ready(name: str, seconds: int) -> tuple[bool, str]:
    hs = health_status(name)
    if hs == "no-health":
        # accept running
        deadline = time.time() + seconds
        while time.time() < deadline:
            if state_running(name):
                return True, "running"
            time.sleep(1)
        return False, "not running"

    deadline = time.time() + seconds
    last = hs
    while time.time() < deadline:
        hs = health_status(name)
        last = hs
        if hs == "healthy":
            return True, hs
        if hs == "unhealthy":
            return False, hs
        time.sleep(2)
    return False, last


def http_check(url: str, timeout: int = 5) -> tuple[bool, str]:
    # Use curl if available
    try:
        out = sh(["curl", "-fsS", "-o", "/dev/null", "-w", "%{http_code}", url], check=False).strip()
        return out in ("200", "302"), out
    except Exception as e:
        return False, str(e)


def run_new(name: str, image: str, env: list[str], binds: list[str], port_args: list[str], restart: str) -> str:
    cmd = ["docker", "run", "-d", "--name", name]
    cmd += port_args
    for e in env:
        cmd += ["-e", e]
    for b in binds:
        cmd += ["-v", b]
    if restart:
        cmd += ["--restart", restart]
    cmd += [image]
    return sh(cmd).strip()


def main():
    ap = argparse.ArgumentParser(description="Recreate a container with env overrides; rollback on failure")
    ap.add_argument("--container", required=True)
    ap.add_argument("--set", action="append", default=[], help="KEY=VALUE (repeatable)")
    ap.add_argument("--wait-seconds", type=int, default=120)
    ap.add_argument("--check-url", default="", help="Optional http(s) url to verify after start")
    args = ap.parse_args()

    name = args.container
    overrides = dict(parse_kv(x) for x in args.set)

    obj = get_inspect(name)
    image = obj["Config"]["Image"]
    env = obj["Config"].get("Env") or []
    binds = obj["HostConfig"].get("Binds") or []
    restart = (obj["HostConfig"].get("RestartPolicy") or {}).get("Name") or ""

    pb = obj["HostConfig"].get("PortBindings") or {}
    port_args: list[str] = []
    for cport, bindings in pb.items():
        if not bindings:
            continue
        container_port = cport.split("/")[0]
        for b in bindings:
            hp = b.get("HostPort")
            if hp:
                port_args += ["-p", f"{hp}:{container_port}"]

    # apply overrides
    new_env = []
    seen = set()
    for e in env:
        k = e.split("=", 1)[0]
        if k in overrides:
            new_env.append(f"{k}={overrides[k]}")
            seen.add(k)
        else:
            new_env.append(e)
    for k, v in overrides.items():
        if k not in seen:
            new_env.append(f"{k}={v}")

    backup = f"{name}.bak.{int(time.time())}"
    new_name = f"{name}.new.{int(time.time())}"

    image_before = sh(["docker", "inspect", name, "--format", "{{.Image}}"], check=True).strip()

    # stop and backup
    sh(["docker", "stop", name], check=False)
    sh(["docker", "rename", name, backup], check=True)

    try:
        run_new(new_name, image, new_env, binds, port_args, restart)
        sh(["docker", "rename", new_name, name], check=True)
        ok, status = wait_ready(name, args.wait_seconds)
        if not ok:
            raise RuntimeError(f"not ready: {status}")
        if args.check_url:
            ok2, code = http_check(args.check_url)
            if not ok2:
                raise RuntimeError(f"http check failed: {code}")

        sh(["docker", "rm", "-f", backup], check=False)
        image_after = sh(["docker", "inspect", name, "--format", "{{.Image}}"], check=True).strip()

        print(
            json.dumps(
                {
                    "ok": True,
                    "host": "local",
                    "container": name,
                    "overrides": list(overrides.keys()),
                    "image_tag": image,
                    "image_before": image_before,
                    "image_after": image_after,
                    "ts_utc": now_utc(),
                },
                ensure_ascii=False,
            )
        )
        return

    except Exception as e:
        # rollback
        sh(["docker", "rm", "-f", name], check=False)
        sh(["docker", "rename", backup, name], check=True)
        sh(["docker", "start", name], check=False)

        image_after = sh(["docker", "inspect", name, "--format", "{{.Image}}"], check=False).strip()
        print(
            json.dumps(
                {
                    "ok": False,
                    "host": "local",
                    "container": name,
                    "overrides": list(overrides.keys()),
                    "error": str(e),
                    "rolled_back": True,
                    "image_before": image_before,
                    "image_after": image_after,
                    "ts_utc": now_utc(),
                },
                ensure_ascii=False,
            )
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
