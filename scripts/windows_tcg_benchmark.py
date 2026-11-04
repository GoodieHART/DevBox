#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["modal>=1.6.3"]
# ///
"""Decision-grade infrastructure baseline for the Windows VM execution path.

The guest runs under QEMU TCG in a disposable Modal VM Sandbox. The harness
does not download an ISO or touch the Windows installation. Host-side monotonic
timing is used for every measured interval; guest /proc/uptime is not used.

Examples:
    uv run scripts/windows_tcg_benchmark.py --scenario matrix --repetitions 3
    uv run scripts/windows_tcg_benchmark.py --scenario smoke --profile 2c-4g
"""

from __future__ import annotations

import argparse
import base64
import csv
import json
import re
import sys
import time
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from collections.abc import Mapping
from typing import Final

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
GUEST_SCRIPT: Final[str] = import_module("scripts.windows_tcg_guest").GUEST_SCRIPT

import modal


@dataclass(frozen=True, slots=True)
class BenchmarkConfig:
    name: str
    host_cpu: int
    host_memory_mib: int
    guest_cpu: int
    guest_memory_mib: int


CONFIGS: Final[tuple[BenchmarkConfig, ...]] = (
    BenchmarkConfig("2c-4g", 2, 4096, 2, 2048),
    BenchmarkConfig("4c-8g", 4, 8192, 4, 4096),
    BenchmarkConfig("8c-16g", 8, 16384, 8, 8192),
    BenchmarkConfig("10c-32g", 10, 32768, 10, 16384),
)
APP_NAME = "devbox-windows-tcg-benchmark"
VOLUME_NAME = "windows-vm-data"
IMAGE = modal.Image.debian_slim(python_version="3.12").apt_install(
        "qemu-system-x86", "linux-image-amd64", "busybox-static", "cpio", "e2fsprogs", "curl", "gcc", "libc6-dev"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=("boot", "cpu", "memory", "smoke", "storage", "network", "matrix"), default="matrix")
    parser.add_argument("--profile", choices=[c.name for c in CONFIGS])
    parser.add_argument("--scenarios", help="comma-separated guest scenarios for matrix mode")
    parser.add_argument("--storage", choices=("ephemeral", "persistent", "both"), default="both")
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--output", type=Path, default=Path("artifacts/windows_tcg_results.json"))
    return parser.parse_args()


def host_network_probe(public: bool, launch_log: Path) -> dict[str, object]:
    started = time.monotonic_ns()
    url = "https://speed.cloudflare.com/__down?bytes=10485760" if public else "http://127.0.0.1:8080/payload"
    command = (
        "dd if=/dev/zero of=/tmp/payload bs=1M count=10 2>/dev/null; "
        "busybox httpd -f -p 8080 -h /tmp >/tmp/http.log 2>&1 & server=$!; "
        f"curl -L --fail --silent --show-error --max-time 30 -o /dev/null {url}; "
        "status=$?; kill $server 2>/dev/null || true; exit $status"
    )
    result = modal.Sandbox.create(app=modal.App.lookup(APP_NAME, create_if_missing=True), image=IMAGE, timeout=60)
    sandbox_id = result.object_id
    event = {"event": "created", "sandbox_id": sandbox_id, "app": APP_NAME,
             "scenario": "network", "target": "public" if public else "local", "created_at_unix": time.time()}
    append_launch_event(launch_log, event)
    print(f"SANDBOX_ID={sandbox_id} NETWORK_TARGET={event['target']}", flush=True)
    try:
        process = result.exec("bash", "-lc", command)
        process.wait()
        elapsed = (time.monotonic_ns() - started) / 1e9
        return {"target": "public" if public else "local", "sandbox_id": sandbox_id,
                "elapsed_s": elapsed, "exit_code": process.returncode}
    finally:
        append_launch_event(launch_log, {**event, "event": "terminating", "terminated_at_unix": time.time()})
        result.terminate()
        append_launch_event(launch_log, {**event, "event": "terminated", "terminated_at_unix": time.time()})


def append_launch_event(path: Path, event: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        handle.write(json.dumps(event) + "\n")


def parse_storage_timing(stdout: str) -> dict[str, float]:
    timings: dict[str, float] = {}
    for operation in ("WRITE", "READ"):
        match = re.search(rf"STORAGE_{operation}_NS=(\d+),(\d+)", stdout)
        if match is not None:
            elapsed = (int(match.group(2)) - int(match.group(1))) / 1_000_000_000
            timings[f"{operation.lower()}_seconds"] = elapsed
            timings[f"{operation.lower()}_mib_per_second"] = 256 / elapsed if elapsed > 0 else 0.0
    return timings


def run_case(
    app: modal.App,
    config: BenchmarkConfig,
    scenario: str,
    storage: str,
    run: int,
    launch_log: Path,
) -> dict[str, object]:
    volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True) if storage == "persistent" else None
    sandbox = modal.Sandbox.create(
        app=app, image=IMAGE, runtime="vm", cpu=config.host_cpu, memory=config.host_memory_mib,
        timeout=420, volumes={"/benchmark-volume": volume} if volume else {},
    )
    sandbox_id = sandbox.object_id
    launch_event = {
        "event": "created", "sandbox_id": sandbox_id, "app": APP_NAME,
        "profile": config.name, "scenario": scenario, "storage": storage, "run": run,
        "created_at_unix": time.time(),
    }
    append_launch_event(launch_log, launch_event)
    print(f"SANDBOX_ID={sandbox_id} LAUNCH_LOG={launch_log}", flush=True)
    started = time.monotonic_ns()
    disk = "/benchmark-volume/tcg-benchmark/" + f"{config.name}-run-{run}.raw" if volume else ""
    try:
        encoded = base64.b64encode(GUEST_SCRIPT.encode()).decode()
        command = (
            f"mkdir -p /benchmark-volume/tcg-benchmark 2>/dev/null || true; "
            f"echo {encoded} | base64 -d > /tmp/run.sh; chmod +x /tmp/run.sh; "
            f"SCENARIO={scenario} GUEST_CPU={config.guest_cpu} "
            f"GUEST_MEMORY_MIB={config.guest_memory_mib} DISK_PATH={disk} /tmp/run.sh & "
            "job=$!; while kill -0 $job 2>/dev/null; do echo HOST_HEARTBEAT; sleep 10; done; wait $job"
        )
        process = sandbox.exec("bash", "-lc", command, timeout=400)
        stdout_lines = list(process.stdout)
        process.wait()
        stdout = "".join(stdout_lines)
        stderr = process.stderr.read()
        guest_failed = "GUEST_FAILED" in stdout
        guest_done = f"GUEST_DONE {scenario}" in stdout
        timing = parse_storage_timing(stdout) if scenario == "storage" else {}
        return {"profile": config.name, "scenario": scenario, "storage": storage, "run": run,
                "sandbox_id": sandbox_id,
                "elapsed_s": (time.monotonic_ns() - started) / 1e9, "exit_code": process.returncode,
                "guest_done": guest_done, "guest_failed": guest_failed,
                "outcome": "valid" if guest_done else ("guest_failed" if guest_failed else "guest_timeout"),
                **timing, "stdout": stdout[-20000:], "stderr": stderr[-4000:]}
    finally:
        append_launch_event(launch_log, {**launch_event, "event": "terminating", "terminated_at_unix": time.time()})
        sandbox.terminate()
        append_launch_event(launch_log, {**launch_event, "event": "terminated", "terminated_at_unix": time.time()})


def write_results(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, indent=2) + "\n")
    csv_path = path.with_suffix(".csv")
    fields = sorted({key for row in rows for key in row})
    with csv_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(rows)


def main() -> None:
    args = parse_args()
    if args.repetitions < 1: raise SystemExit("--repetitions must be positive")
    app = modal.App.lookup(APP_NAME, create_if_missing=True)
    launch_log = args.output.with_name("windows_tcg_sandboxes.jsonl")
    configs = tuple(c for c in CONFIGS if not args.profile or c.name == args.profile)
    requested_scenarios = tuple(args.scenarios.split(",")) if args.scenarios else ("boot", "cpu", "memory", "storage")
    scenarios = requested_scenarios if args.scenario == "matrix" else (() if args.scenario == "network" else (args.scenario,))
    stores = ("ephemeral", "persistent") if args.storage == "both" else (args.storage,)
    rows: list[dict[str, object]] = [{"kind": "metadata", "modal_version": modal.__version__, "runtime": "vm-tcg", "kvm": False}]
    print(f"MODAL_VERSION={modal.__version__} SCENARIO={args.scenario} REPS={args.repetitions}")
    for config in configs:
        for scenario in scenarios:
            for storage in stores:
                for run in range(1, args.repetitions + 1):
                    print(f"RUN profile={config.name} scenario={scenario} storage={storage} repetition={run}", flush=True)
                    row = run_case(app, config, scenario, storage, run, launch_log); rows.append(row)
                    print(json.dumps({k: row[k] for k in ("profile", "scenario", "storage", "run", "elapsed_s", "exit_code", "guest_done")}))
    if args.scenario == "network":
        rows.append({"kind": "network", **host_network_probe(False, launch_log)})
        rows.append({"kind": "network", **host_network_probe(True, launch_log)})
    write_results(args.output, rows)
    print(f"RESULTS={args.output} CSV={args.output.with_suffix('.csv')}")


if __name__ == "__main__":
    main()
