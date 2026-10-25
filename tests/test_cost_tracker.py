"""Structural/behavioral tests for runtime.cost_tracker (no Modal credentials needed)."""

import json
import os
import tempfile

import pytest

from runtime import cost_tracker as ct


@pytest.fixture
def cost_dir(monkeypatch):
    d = tempfile.mkdtemp()
    monkeypatch.setenv("DEVBOX_COST_DIR", d)
    ct.reset_for_testing()
    return d


def test_estimate_cost_usd_math():
    from devbox_core import config

    # 0.5 cpu, 1024MB, no gpu, 100s
    val = config.estimate_cost_usd(0.5, 1024, None, 100)
    assert val > 0
    # zero elapsed -> zero
    assert config.estimate_cost_usd(0.5, 1024, None, 0) == 0.0
    # gpu adds cost
    cpu_only = config.estimate_cost_usd(0.5, 1024, None, 100)
    with_gpu = config.estimate_cost_usd(0.5, 1024, "t4", 100)
    assert with_gpu > cpu_only


def test_start_session_writes_file(cost_dir):
    s = ct.start_session("standard_devbox", {"cpu": 0.5, "memory": 1024, "timeout": 3600})
    assert s["status"] == "running"
    assert s["started_at"] is not None
    path = os.path.join(cost_dir, "sessions", s["session_id"] + ".json")
    assert os.path.exists(path)
    with open(path) as f:
        on_disk = json.load(f)
    assert on_disk["session_id"] == s["session_id"]
    assert on_disk["devbox_type"] == "standard_devbox"


def test_flush_finalizes(cost_dir):
    ct.start_session("opencode", {"cpu": 2.0, "memory": 8192, "timeout": 10800})
    ct.register_cost_flush()
    # simulate some time
    import time

    time.sleep(0.05)
    ct.flush()
    sessions = ct.list_sessions()
    assert len(sessions) == 1
    s = sessions[0]
    assert s["status"] == "completed"
    assert s["ended_at"] is not None
    assert s["elapsed_s"] >= 0
    assert s["estimated_cost_usd"] >= 0


def test_checkpoint_writes_running(cost_dir):
    ct.start_session("rdp", {"cpu": 1.0, "memory": 2048})
    ct.checkpoint()
    sessions = ct.list_sessions()
    assert len(sessions) == 1
    assert sessions[0]["status"] == "running"


def test_interrupted_status_via_direct_write(cost_dir):
    # A session that never flushes stays "running" (interrupted on hard kill)
    s = ct.start_session("llm_playroom", {"cpu": 1.0, "memory": 2048})
    # no flush
    on_disk = json.load(open(os.path.join(cost_dir, "sessions", s["session_id"] + ".json")))
    assert on_disk["status"] == "running"
    assert on_disk["ended_at"] is None


def test_atomic_write_no_tmp_left(cost_dir):
    s = ct.start_session("forensic_analysis", {"cpu": 0.5, "memory": 1024})
    ct.flush()
    d = os.path.join(cost_dir, "sessions")
    for name in os.listdir(d):
        assert not name.endswith(".tmp"), f"tmp leftover: {name}"


def test_list_and_summarize(cost_dir):
    ct.start_session("standard_devbox", {"cpu": 0.5, "memory": 1024})
    ct.register_cost_flush()
    ct.flush()
    ct.reset_for_testing()
    # second session in same dir
    os.environ["DEVBOX_COST_DIR"] = cost_dir
    ct.start_session("standard_devbox", {"cpu": 0.5, "memory": 1024})
    ct.register_cost_flush()
    ct.flush()
    summary = ct.summarize()
    assert summary["sessions"] == 2
    assert "standard_devbox" in summary["by_type"]


def test_reset_for_testing_clears_state(cost_dir):
    ct.start_session("x", {"cpu": 0.5, "memory": 1024})
    ct.reset_for_testing()
    assert ct._session is None
    assert ct.list_sessions()  # files still on disk, but state cleared


def test_gpu_cost_higher_than_cpu(cost_dir):
    cpu = ct.cost_estimate(0.5, 1024, None, 3600)
    gpu = ct.cost_estimate(0.5, 1024, "t4", 3600)
    assert gpu > cpu
