#!/usr/bin/env python3
import argparse
import json
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone


def sh(cmd: list[str], check=True) -> str:
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if check and p.returncode != 0:
        raise RuntimeError(f"cmd failed: {' '.join(cmd)}\n{p.stdout}")
    return p.stdout


def ssh_cmd(host: str, user: str, key: str, connect_timeout: int, known_hosts: str, command: list[str]) -> list[str]:
    remote = " ".join(shlex.quote(c) for c in command)
    return [
        "ssh",
        "-F",
        "/dev/null",
        "-i",
        key,
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "BatchMode=yes",
        "-o",
        f"ConnectTimeout={connect_timeout}",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        f"UserKnownHostsFile={known_hosts}",
        f"{user}@{host}",
        remote,
    ]


def run_docker(host: str, docker_args: list[str], ssh_user: str, ssh_key: str, connect_timeout: int) -> str:
    if host == "local":
        return sh(["docker", *docker_args], check=False)

    known_hosts = f"/tmp/openclaw_docker_upgrader_known_hosts_{host.replace('.', '_')}"
    cmd = ssh_cmd(host, ssh_user, ssh_key, connect_timeout, known_hosts, ["docker", *docker_args])
    return sh(cmd, check=False)


def now_utc():
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ContainerSpec:
    name: str
    image: str
    binds: list[str]
    env: list[str]
    port_args: list[str]
    restart: str


def inspect_spec(host: str, ssh_user: str, ssh_key: str, connect_timeout: int, name: str) -> ContainerSpec:
    raw = run_docker(host, ["inspect", name], ssh_user, ssh_key, connect_timeout)
    obj = json.loads(raw)[0]

    image = obj["Config"]["Image"]
    env = obj["Config"].get("Env") or []

    binds = obj["HostConfig"].get("Binds") or []
    restart = (obj["HostConfig"].get("RestartPolicy") or {}).get("Name") or ""

    # PortBindings -> -p host:container
    pb = obj["HostConfig"].get("PortBindings") or {}
    port_args = []
    for cport, bindings in pb.items():
        if not bindings:
            continue
        container_port = cport.split("/")[0]
        for b in bindings:
            hp = b.get("HostPort")
            if hp:
                port_args += ["-p", f"{hp}:{container_port}"]

    return ContainerSpec(name=name, image=image, binds=binds, env=env, port_args=port_args, restart=restart)


def health_status(host: str, ssh_user: str, ssh_key: str, connect_timeout: int, name: str) -> str:
    out = run_docker(
        host,
        [
            "inspect",
            name,
            "--format",
            "{{if .State.Health}}{{.State.Health.Status}}{{else}}no-health{{end}}",
        ],
        ssh_user,
        ssh_key,
        connect_timeout,
    ).strip()
    return out.strip('"')


def state_running(host: str, ssh_user: str, ssh_key: str, connect_timeout: int, name: str) -> bool:
    out = run_docker(host, ["inspect", name, "--format", "{{.State.Running}}"], ssh_user, ssh_key, connect_timeout).strip()
    return out == "true"


def wait_healthy(host: str, ssh_user: str, ssh_key: str, connect_timeout: int, name: str, seconds: int) -> tuple[bool, str]:
    # If container has no healthcheck, accept running.
    hs = health_status(host, ssh_user, ssh_key, connect_timeout, name)
    if hs == "":
        # no health section; wait for running true
        deadline = time.time() + seconds
        while time.time() < deadline:
            if state_running(host, ssh_user, ssh_key, connect_timeout, name):
                return True, "running"
            time.sleep(1)
        return False, "not running"

    deadline = time.time() + seconds
    last = hs
    while time.time() < deadline:
        hs = health_status(host, ssh_user, ssh_key, connect_timeout, name)
        last = hs
        if hs == "healthy":
            return True, hs
        if hs == "unhealthy":
            return False, hs
        time.sleep(2)
    return False, last


def run_new(host: str, ssh_user: str, ssh_key: str, connect_timeout: int, spec: ContainerSpec, name: str, image: str) -> str:
    cmd = ["run", "-d", "--name", name]
    cmd += spec.port_args
    for e in spec.env:
        # keep value, but caller should avoid printing env content
        cmd += ["-e", e]
    for b in spec.binds:
        cmd += ["-v", b]
    if spec.restart:
        cmd += ["--restart", spec.restart]
    cmd += [image]
    # Do NOT print env values.
    return run_docker(host, cmd + [image], ssh_user, ssh_key, connect_timeout).strip()


def rollback(host: str, ssh_user: str, ssh_key: str, connect_timeout: int, old_name: str, backup_name: str, new_name: str):
    run_docker(host, ["rm", "-f", new_name], ssh_user, ssh_key, connect_timeout)
    run_docker(host, ["rename", backup_name, old_name], ssh_user, ssh_key, connect_timeout)
    run_docker(host, ["start", old_name], ssh_user, ssh_key, connect_timeout)


def main():
    ap = argparse.ArgumentParser(description="Upgrade a docker container by recreating it with the same config; rollback on failure (local or remote via ssh)")
    ap.add_argument("--host", default="local", help="Target host: local or ip")
    ap.add_argument("--ssh-user", default="vincent08080", help="SSH username")
    ap.add_argument(
        "--ssh-key",
        default="/root/.openclaw/workspace/keys/id_ed25519_opencode_mcp",
        help="SSH private key path (do NOT commit secrets)",
    )
    ap.add_argument("--connect-timeout", type=int, default=6, help="SSH connect timeout seconds")
    ap.add_argument("--container", required=True, help="Container name")
    ap.add_argument("--wait-seconds", type=int, default=120, help="Wait for healthy/running")
    args = ap.parse_args()

    host = args.host
    name = args.container
    backup = f"{name}.bak.{int(time.time())}"
    new_name = f"{name}.new.{int(time.time())}"

    spec = inspect_spec(host, args.ssh_user, args.ssh_key, args.connect_timeout, name)
    image_before = run_docker(host, ["inspect", name, "--format", "{{.Image}}"], args.ssh_user, args.ssh_key, args.connect_timeout).strip()

    run_docker(host, ["pull", spec.image], args.ssh_user, args.ssh_key, args.connect_timeout)
    desired_image = run_docker(host, ["image", "inspect", spec.image, "--format", "{{.Id}}"], args.ssh_user, args.ssh_key, args.connect_timeout).strip() or spec.image

    # stop and backup
    run_docker(host, ["stop", name], args.ssh_user, args.ssh_key, args.connect_timeout)
    rb = run_docker(host, ["rename", name, backup], args.ssh_user, args.ssh_key, args.connect_timeout)
    if "permission denied" in rb.lower():
        raise SystemExit(rb.strip())

    ok = False
    reason = ""

    try:
        _ = run_new(host, args.ssh_user, args.ssh_key, args.connect_timeout, spec, new_name, spec.image)
        run_docker(host, ["rename", new_name, name], args.ssh_user, args.ssh_key, args.connect_timeout)
        ok, status = wait_healthy(host, args.ssh_user, args.ssh_key, args.connect_timeout, name, args.wait_seconds)
        if not ok:
            reason = f"healthcheck failed: {status}"
            raise RuntimeError(reason)

        # success: remove backup
        run_docker(host, ["rm", "-f", backup], args.ssh_user, args.ssh_key, args.connect_timeout)

        image_after = run_docker(host, ["inspect", name, "--format", "{{.Image}}"], args.ssh_user, args.ssh_key, args.connect_timeout).strip()
        report = {
            "ok": True,
            "host": host,
            "container": name,
            "image_tag": spec.image,
            "image_before": image_before,
            "image_after": image_after,
            "desired_image": desired_image,
            "ts_utc": now_utc(),
        }
        print(json.dumps(report, ensure_ascii=False))
        return

    except Exception as e:
        reason = str(e)
        rollback(host, args.ssh_user, args.ssh_key, args.connect_timeout, name, backup, new_name)
        image_after = run_docker(host, ["inspect", name, "--format", "{{.Image}}"], args.ssh_user, args.ssh_key, args.connect_timeout).strip()
        report = {
            "ok": False,
            "host": host,
            "container": name,
            "error": reason,
            "rolled_back": True,
            "image_before": image_before,
            "image_after": image_after,
            "ts_utc": now_utc(),
        }
        print(json.dumps(report, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main()
