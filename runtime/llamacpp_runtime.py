"""llama.cpp playroom runtime (runs inside the Modal remote container).

All Modal/local imports stay function-local so the module remains
import-safe both locally and on the remote side.
"""


def build_server_cmd(model_path, settings, mode):
    """Build the llama-server command line for cpu/gpu mode."""
    settings = settings or {}
    temp = str(settings.get("temp", 0.7))
    top_p = str(settings.get("top_p", 0.9))
    top_k = str(settings.get("top_k", 40))
    if mode == "gpu":
        return [
            "llama-server",
            "-m", model_path,
            "--host", "0.0.0.0",
            "--port", "8080",
            "--ctx-size", "32768",
            "--batch-size", "512",
            "-ngl", "99",
            "-fa", "on",
            "-ctk", "q8_0",
            "-ctv", "q8_0",
            "--jinja",
            "--temp", temp,
            "--top-p", top_p,
            "--top-k", top_k,
        ]
    return [
        "llama-server",
        "-m", model_path,
        "--host", "0.0.0.0",
        "--port", "8080",
        "--threads", "2",
        "--ctx-size", "4096",
        "--batch-size", "512",
        "--mlock",
        "--jinja",
        "--temp", temp,
        "--top-p", top_p,
        "--top-k", top_k,
    ]


def download_model(selected_model, model_dir="/data/models"):
    """Download the GGUF model if not cached. Returns path or None."""
    import os
    import subprocess

    os.makedirs(model_dir, exist_ok=True)
    model_path = f"{model_dir}/{selected_model['filename']}"

    if not os.path.exists(model_path):
        print(f"\n📦 Downloading {selected_model['repo_id']}/{selected_model['filename']}...")
        print("   This may take a few minutes on first run...")

        try:
            subprocess.run([
                "hf", "download",
                selected_model["repo_id"],
                selected_model["filename"],
                "--local-dir", model_dir
            ], check=True)
            print(f"✅ Model downloaded to {model_path}")
        except subprocess.CalledProcessError:
            print("❌ Download failed. Check repo_id and filename.")
            print(f"   Repo: {selected_model['repo_id']}")
            print(f"   File: {selected_model['filename']}")
            return None
    else:
        print(f"✅ Model already cached: {model_path}")
    return model_path


def wait_for_server(server_process, timeout_secs=30):
    """Poll /health until llama-server is ready. Returns True/False."""
    import time
    import httpx

    time.sleep(3)
    for _ in range(timeout_secs):
        try:
            resp = httpx.get("http://localhost:8080/health", timeout=1.0)
            if resp.status_code == 200:
                print("✅ llama-server ready!")
                return True
        except Exception:
            pass
        time.sleep(1)
    print("❌ llama-server failed to start. Check model file.")
    server_process.terminate()
    return False


def run_idle_monitor(server_process, idle_timeout):
    """Idle monitor shared by cpu/gpu playrooms."""
    import subprocess
    import time
    import httpx

    idle_time = 0
    check_interval = 30

    while idle_time < idle_timeout:
        time.sleep(check_interval)

        try:
            from runtime.cost_tracker import checkpoint
            checkpoint()
        except Exception:
            pass

        ssh_result = subprocess.run(
            "ps -ef | grep 'sshd: root@' | grep -v grep",
            shell=True,
            capture_output=True,
        )

        web_active = False
        try:
            httpx.get("http://localhost:8080/health", timeout=1.0)
            web_active = True
        except Exception:
            pass

        if ssh_result.stdout or web_active:
            idle_time = 0
        else:
            idle_time += check_interval
            remaining = idle_timeout - idle_time
            print(f"\r💤 No activity. Shutting down in {remaining // 60}m {remaining % 60}s...", end="", flush=True)

    print(f"\n\n⏰ Idle timeout reached ({idle_timeout}s). Shutting down.")
    server_process.terminate()


def run_llamacpp_playroom(mode, resources=None):
    """Orchestrator shared by the cpu/gpu launchers. mode is "cpu"|"gpu"."""
    import subprocess
    import modal
    from devbox_core.llamacpp_models import LLAMACPP_MODELS
    from devbox_core.config import LLAMACPP_IDLE_TIMEOUT
    from runtime.persistence_utils import setup_persistence, get_persistence_items
    from runtime.utils import inject_ssh_key
    from integrations.exa_helper import get_exa_api_key

    modal.interact()

    print("\n🧠 Launching llama.cpp Research Center")
    if mode == "gpu":
        print("🚀 GPU-Accelerated Inference (T4)")
    else:
        print("💻 CPU-Optimized Inference")
    print("🔍 EXA Search Integration")
    print("🌐 Built-in WebUI")

    setup_persistence(get_persistence_items("ssh"))

    # Cost tracking: one record per launch (best-effort)
    try:
        from runtime.cost_tracker import start_session, register_cost_flush
        if resources:
            _resources = dict(resources)
        else:
            _gpu = "t4" if mode == "gpu" else None
            _resources = {"cpu": 2.0, "memory": 16384 if mode == "gpu" else 8192, "gpu": _gpu, "timeout": 14400}
        _ct_session = start_session("llamacpp_playroom", _resources)
        register_cost_flush(_ct_session)
    except Exception as _e:
        import sys
        print(f"[cost_tracker] init failed: {_e}", file=sys.stderr)

    # --- Model Selection ---
    print("\n📦 Model Selection:")
    for key, model in LLAMACPP_MODELS.items():
        print(f"{key}. {model['name']} - {model['description']}")
        print(f"   Size: {model['size']} | Type: {model['type']}")

    try:
        model_choice = input("\nEnter model number (1-5): ").strip()
    except EOFError:
        model_choice = "1"

    if model_choice not in LLAMACPP_MODELS:
        print("❌ Invalid choice. Defaulting to Qwen3.5-9B")
        model_choice = "1"

    selected_model = LLAMACPP_MODELS[model_choice].copy()

    # Handle custom model input
    if model_choice == "5":
        print("\n📝 Custom Model Details:")
        repo_id = input("Repo ID (e.g., unsloth/Qwen3.5-9B-GGUF): ").strip()
        filename = input("Filename (e.g., model-Q4_K_M.gguf): ").strip()
        selected_model["repo_id"] = repo_id
        selected_model["filename"] = filename
        selected_model["name"] = filename.replace(".gguf", "")

    model_path = download_model(selected_model)
    if model_path is None:
        return

    # --- EXA Search Check ---
    exa_key = get_exa_api_key()
    if exa_key:
        print("✅ EXA Search API key found")
        use_exa = True
    else:
        print("⚠️  EXA Search API key not found. Web search disabled.")
        print("   Add 'exa-api-key' secret to Modal to enable.")
        use_exa = False

    # --- Start llama-server ---
    model_settings = selected_model.get("settings", {})
    server_cmd = build_server_cmd(model_path, model_settings, mode)

    if mode == "gpu":
        print(f"\n🚀 Starting GPU-accelerated llama-server for {selected_model['name']}...")
        print("   GPU: T4 (all layers offloaded)")
        print(f"   Settings: temp={model_settings.get('temp', 0.7)}, top_p={model_settings.get('top_p', 0.9)}")
        print("   Context: 32K with KV cache quantization")
    else:
        print(f"\n🚀 Starting llama-server for {selected_model['name']}...")
        print(f"   Settings: temp={model_settings.get('temp', 0.7)}, top_p={model_settings.get('top_p', 0.9)}")

    server_process = subprocess.Popen(
        server_cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE
    )

    if not wait_for_server(server_process):
        return

    # --- Start EXA Proxy (if enabled) ---
    if use_exa:
        from integrations.exa_proxy import start_exa_proxy
        print("  Starting EXA Search proxy...")
        start_exa_proxy(port=8081, target_port=8080)
        web_port = 8081
    else:
        web_port = 8080

    # --- SSH Setup ---
    inject_ssh_key()
    subprocess.run(["/usr/sbin/sshd"])

    # Launch a tmux session (3 windows) users can attach to.
    try:
        from runtime.shared_runtime import start_tmux_session
        start_tmux_session()
    except Exception as e:
        import sys
        print(f"\u26a0\ufe0f tmux session setup failed: {e}", file=sys.stderr)

    # --- Port Forwarding ---
    with modal.forward(22, unencrypted=True) as ssh_tunnel:
        ssh_command = f"ssh root@{ssh_tunnel.host} -p {ssh_tunnel.unencrypted_port} -t \"tmux attach -t devbox\""

    with modal.forward(web_port, unencrypted=True) as web_tunnel:
        web_url = f"http://{web_tunnel.host}:{web_tunnel.unencrypted_port}"

        print("\n" + "=" * 60)
        if mode == "gpu":
            print("🚀 Your GPU llama.cpp Research Center is ready!")
        else:
            print("🚀 Your llama.cpp Research Center is ready!")
        print("=" * 60)
        print(f"\n🌐 WebUI: {web_url}")
        print("   (Open in browser for chat interface)")
        print(f"\n🔐 SSH: {ssh_command}")
        print(f"\n🧠 Model: {selected_model['name']} ({selected_model['size']})")
        if mode == "gpu":
            print("🎮 GPU: T4 (all layers offloaded)")
        if use_exa:
            print("🔍 EXA Search: Enabled (function calling)")
        print(f"\n⏰ Idle timeout: {LLAMACPP_IDLE_TIMEOUT // 60} minutes")
        print("\n" + "=" * 60)

        run_idle_monitor(server_process, LLAMACPP_IDLE_TIMEOUT)
