#!/usr/bin/env python3
import argparse
import json
import shlex
import subprocess
import sys
from dataclasses import dataclass


def sh(cmd: list[str], check=True) -> str:
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if check and p.returncode != 0:
        raise RuntimeError(f"cmd failed: {' '.join(cmd)}\n{p.stdout}")
    return p.stdout


def ssh_cmd(host: str, user: str, key: str, connect_timeout: int, known_hosts: str, command: list[str]) -> list[str]:
    # Build a single remote command string with proper quoting.
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


@dataclass
class ContainerInfo:
    host: str
    name: str
    image_ref: str
    image_id_before: str
    ports: str


def run_docker(host: str, docker_args: list[str], ssh_user: str, ssh_key: str, connect_timeout: int) -> str:
    if host == "local":
        return sh(["docker", *docker_args], check=False)

    known_hosts = f"/tmp/openclaw_docker_upgrader_known_hosts_{host.replace('.', '_')}"
    cmd = ssh_cmd(host, ssh_user, ssh_key, connect_timeout, known_hosts, ["docker", *docker_args])
    return sh(cmd, check=False)


def list_running(host: str, ssh_user: str, ssh_key: str, connect_timeout: int) -> tuple[list[ContainerInfo], str]:
    out = run_docker(host, ["ps", "--format", "{{.Names}}\t{{.Image}}\t{{.Ports}}"], ssh_user, ssh_key, connect_timeout)
    items: list[ContainerInfo] = []
    err = ""

    # detect common permission error
    if "permission denied" in out.lower() and "docker daemon socket" in out.lower():
        return [], out.strip()

    for line in out.splitlines():
        if not line.strip() or "\t" not in line:
            continue
        name, image_ref, ports = (line.split("\t") + ["", ""])[:3]
        img_id = run_docker(host, ["inspect", name, "--format", "{{.Image}}"], ssh_user, ssh_key, connect_timeout).strip()
        items.append(ContainerInfo(host=host, name=name, image_ref=image_ref, image_id_before=img_id, ports=ports))

    return items, err


def pull(host: str, image_ref: str, ssh_user: str, ssh_key: str, connect_timeout: int) -> str:
    return run_docker(host, ["pull", image_ref], ssh_user, ssh_key, connect_timeout)


def image_id(host: str, image_ref: str, ssh_user: str, ssh_key: str, connect_timeout: int) -> str:
    out = run_docker(host, ["image", "inspect", image_ref, "--format", "{{.Id}}"], ssh_user, ssh_key, connect_timeout)
    return out.strip()


def match_filter(ci: ContainerInfo, filter_name: str | None, filter_port: int | None) -> bool:
    if filter_name and filter_name not in ci.name:
        return False
    if filter_port is not None:
        if f":{filter_port}->" not in ci.ports:
            return False
    return True


def main():
    ap = argparse.ArgumentParser(description="Check docker container image upgrades by pulling tags (local or remote via ssh)")
    ap.add_argument("--hosts", default="local", help="Comma-separated hosts: local,192.168.100.21")
    ap.add_argument("--ssh-user", default="vincent08080", help="SSH username for remote hosts")
    ap.add_argument(
        "--ssh-key",
        default="/root/.openclaw/workspace/keys/id_ed25519_opencode_mcp",
        help="SSH private key path (do NOT commit secrets)",
    )
    ap.add_argument("--connect-timeout", type=int, default=6, help="SSH connect timeout seconds")
    ap.add_argument("--filter-name", default="", help="Substring filter for container name")
    ap.add_argument("--filter-port", type=int, default=None, help="Host port filter")
    ap.add_argument("--json", action="store_true", help="Output JSON")
    args = ap.parse_args()

    hosts = [h.strip() for h in args.hosts.split(",") if h.strip()]

    checked_all = []
    upgradable = []
    host_errors = {}

    for host in hosts:
        running, err = list_running(host, args.ssh_user, args.ssh_key, args.connect_timeout)
        if err:
            host_errors[host] = err
            continue

        filtered = [
            ci
            for ci in running
            if match_filter(ci, args.filter_name or None, args.filter_port)
        ]

        for ci in filtered:
            before = ci.image_id_before
            pull_out = pull(host, ci.image_ref, args.ssh_user, args.ssh_key, args.connect_timeout)
            after = image_id(host, ci.image_ref, args.ssh_user, args.ssh_key, args.connect_timeout) or before
            changed = after != before
            row = {
                "host": host,
                "name": ci.name,
                "image": ci.image_ref,
                "ports": ci.ports,
                "before": before,
                "after": after,
                "changed": changed,
                "pull_error": "permission denied" if ("permission denied" in pull_out.lower()) else "",
            }
            checked_all.append(row)

    # assign global indices to changed rows (across hosts)
    changed_rows = [r for r in checked_all if r.get("changed")]
    for i, row in enumerate(changed_rows, start=1):
        upgradable.append({"index": i, **row})

    payload = {
        "hosts": hosts,
        "host_errors": host_errors,
        "count_checked": len(checked_all),
        "count_upgradable": len(upgradable),
        "upgradable": upgradable,
        "checked": checked_all,
    }

    if args.json:
        print(json.dumps(payload, ensure_ascii=False))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(2)
