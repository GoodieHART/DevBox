# Modal Rules and Guidelines for LLMs

This file provides rules and guidelines for LLMs when implementing Modal code.

## General

- Modal is a serverless cloud platform for running Python code with minimal configuration.
- Designed for AI/ML workloads but supports general-purpose cloud compute.
- Serverless billing model - you only pay for resources used.

## Modal documentation

- Extensive documentation is available at: modal.com/docs (and in markdown format at modal.com/llms-full.txt)
- A large collection of examples is available at: modal.com/docs/examples (and github.com/modal-labs/modal-examples)
- Reference documentation is available at: modal.com/docs/reference
- The Modal CLI ships agent skills: `modal skills install` (see modal.com/docs/guide/agent-skills).

Always refer to documentation and examples for up-to-date functionality and exact syntax. Modal evolves quickly and prints deprecation warnings; never use deprecated features in new code.

## Core Modal concepts

### App

- A group of functions, classes, and sandboxes that are deployed together.
- `app = modal.App(name="my-app")`. Apps can be tagged: `modal.App(name="...", tags={"team": "..."})`.
- Use `with app.run():` for ephemeral runs, `modal deploy` for persistent apps.

### Function

- The basic unit of serverless execution on Modal.
- Each Function executes in its own container, and you can configure different Images for different Functions within the same App:

  ```python
  image = (
    modal.Image.debian_slim(python_version="3.13")
    .pip_install("torch", "numpy", "transformers")
    .apt_install("ffmpeg")
    .run_commands("mkdir -p /models")
  )

  @app.function(image=image)
  def square(x: int) -> int:
    return x * x
  ```

- Configure hardware requirements per Function:

  ```python
  @app.function(
    gpu="H100",
    cpu=2.0,
    memory=4096,
    timeout=3600,
    min_containers=1,
    max_containers=10,
    buffer_containers=2,
    scaledown_window=300,
    single_use_containers=False,
    include_source=True,
    retries=modal.Retries(max_retries=3, backoff_coefficient=2.0),
  )
  def inference():
    ...
  ```

- Invocation methods:

  ```python
  square.remote(5)               # run in a separate container
  square.local(5)                # run in the caller's context
  square.map([1, 2, 3])          # parallel map
  square.starmap([(1,), (2,)])   # parallel map over argument tuples
  square.spawn(5)                # fire-and-forget; returns a FunctionCall
  square.spawn_map([1, 2, 3])
  square.remote_gen(...)         # generator that streams results
  await square.remote.aio(5)     # async variant
  ```

- `FunctionCall` objects: `call = square.spawn(5)`; `call.get(timeout=60)`; `modal.FunctionCall.from_id("fc-...")`.
- Look up deployed functions: `modal.Function.from_name("app", "fn")` (pin a version with `version=...`).
- Parametrize with `modal.parameter()`:

  ```python
  @app.function()
  def greet(name: str = modal.parameter()):
    return f"hello {name}"
  ```

- Concurrency and batching:

  ```python
  @app.function()
  @modal.concurrent(max_inputs=100, target_inputs=80)
  def handle(req):
    ...

  @app.function()
  @modal.batched(max_batch_size=32, wait_ms=100)
  def embed(texts: list[str]) -> list[list[float]]:
    ...
  ```

  Dynamic reconfiguration: `fn.with_concurrency(...)`, `fn.with_batching(...)`, `fn.with_options(...)`.

- Web endpoints:

  ```python
  @app.function()
  @modal.fastapi_endpoint()          # replaces deprecated @modal.web_endpoint
  def fastapi_endpoint():
    return {"status": "ok"}

  @app.function()
  @modal.asgi_app()
  def asgi_app():
    app = FastAPI()
    ...
    return app

  @app.function()
  @modal.wsgi_app()
  def wsgi_app():
    ...

  @app.function()
  @modal.web_server(port=8000)
  def serve():
    subprocess.Popen(["python", "-m", "http.server", "8000"])
  ```

- `modal.forward(port)` opens a tunnel inside a running container; `modal.interact()` attaches an interactive shell.

- Scheduling:

  ```python
  @app.function(schedule=modal.Period(minutes=5))
  @app.function(schedule=modal.Cron("0 9 * * *", timezone="America/New_York"))
  def scheduled():
    ...
  ```

- Clustered (multi-node) functions:

  ```python
  @app.function(gpu="H100:8")
  @modal.clustered(size=2, rdma=True)
  def train():
    import modal
    rank = modal.container_rank()   # 0..size-1
    ips = modal.container_ips()
  ```

  Multi-node functions require GPUs on every node; CPU-only clusters are not supported.

- GPU options:

  ```python
  @app.function(gpu="T4")                # single GPU
  @app.function(gpu="A100:2")            # multiple GPUs
  @app.function(gpu=["H100", "A100"])    # fallbacks
  @app.function(gpu="H100!")             # strict (no fallback)
  ```

  Supported GPUs: `T4`, `L4`, `A10`, `L40S`, `A100`, `A100-40GB`, `A100-80GB`, `RTX-PRO-6000`, `H100`, `H200`, `B200`, `B300`, `any`.

### Classes (a.k.a. `Cls`)

- For stateful operations with startup/shutdown lifecycle hooks. Do **not** define a custom `__init__`; use `modal.parameter()` instead.

  ```python
  @app.cls(gpu="A100")
  class ModelServer:
      @modal.enter()
      def load_model(self):
          self.model = load_model()

      @modal.method()
      def predict(self, text: str) -> str:
          return self.model.generate(text)

      @modal.exit()
      def cleanup(self):
          cleanup()
  ```

- `@modal.concurrent`, `@modal.batched`, and `@modal.parameter` can decorate cls methods.
- Web lifecycle: `@modal.asgi_app()` / `@modal.wsgi_app()` can be methods on a cls.

### Other important concepts

- **Image**: Represents a container image. Build with `modal.Image.debian_slim()`, `modal.Image.from_registry()`, `modal.Image.from_dockerfile()`, `modal.Image.from_scratch()`. Chain `.pip_install()`, `.uv_pip_install()` (preferred), `.apt_install()`, `.run_commands()`, `.run_function()`, `.add_local_file()`, `.add_local_dir()`, `.add_local_python_source()`, `.imports()`. Publish named images with `.publish()` / `Image.from_name()`. Force rebuilds with `force_build=True` or `MODAL_FORCE_BUILD=1`.
- **Sandbox**: Secure runtime containers for arbitrary code. `modal.Sandbox.create(app=..., image=..., volumes=..., cpu=..., memory=..., gpu=..., runtime="vm", timeout=..., idle_timeout=..., readiness_probe=..., tags=..., include_oidc_identity_token=...)`. Methods: `.exec()`, `.filesystem` (read/write/list/mkdir/rm/watch), `.terminate(wait=...)`, `.detach()`, `.snapshot_filesystem()`, `.snapshot_directory()`, `.mount_image()`, `.unmount_image()`, `.logs()`, `.from_name()`, `.from_id()`, `.create_connect_token()`. Networking via `outbound_cidr_allowlist`, `outbound_domain_allowlist`, `inbound_cidr_allowlist`, `custom_domain`.
- **Volume**: Distributed file system. `modal.Volume.from_name("name", create_if_missing=True, version=2)`. Methods: `.commit()`, `.reload()`, `.with_mount_options(read_only=True, sub_path="...")`. CLI: `modal volume create/list/get/put/rm/snapshot`. Sync with `modal volume sync`.
- **CloudBucketMount**: Mount S3, R2, or GCS buckets into containers.
- **Secret**: Secure credentials. `modal.Secret.from_name("name")`, `modal.Secret.from_dict({...})`, `modal.Secret.from_dotenv()`. Update with `Secret.update()`.
- **Dict**: Distributed key/value store. `modal.Dict.from_name("name", create_if_missing=True)`.
- **Queue**: Distributed FIFO queue. `modal.Queue.from_name("name", create_if_missing=True)`.
- **Server**: Sticky-session server. `@app.server()` + `@modal.sessioned()`; `modal.Server.from_name()`, `Server.sessions.start/terminate`, `Server.get_url()`.
- **Endpoint**: Managed inference endpoints. `modal endpoint create/list/info/logs/stats/stop`.
- **Cluster**: Multi-node. `@modal.clustered(size=..., rdma=True)`, `modal.Cluster.from_context()`.

## Differences from standard Python development

- Modal always executes code in the cloud, even while you are developing. Use Environments for separating development and production deployments.
- Dependencies: It's common and encouraged to have different dependency requirements for different Functions within the same App. Consider defining dependencies in Image definitions (see Image docs) that are attached to Functions, rather than in global `requirements.txt`/`pyproject.toml` files, and putting `import` statements inside the Function `def`. Any code in the global scope needs to be executable in all environments where that App source will be used (locally, and any of the Images the App uses).

## Modal coding style

- Modal Apps, Volumes, and Secrets should be named using kebab-case.
- Always use `import modal`, and qualified names like `modal.App()`, `modal.Image.debian_slim()`.
- Modal evolves quickly, and prints helpful deprecation warnings when you `modal run` an App that uses deprecated features. When writing new code, never use deprecated features.

## Common commands

Running `modal --help` gives you a list of all available commands. All commands also support `--help` for more details.

### Running your Modal app during development

- `modal run path/to/your/app.py` - Run your app on Modal.
- `modal run -m module.path.to.app` - Run your app on Modal, using the Python module path.
- `modal run -d path/to/your/app.py` - Run detached (survives local disconnects).
- `modal serve modal_server.py` - Run web endpoint(s) associated with a Modal app, and hot-reload code on changes. Will print a URL to the web endpoint(s). Note: you need to use `Ctrl+C` to interrupt `modal serve`.
- `modal deploy path/to/your/app.py` - Deploy your app (Functions, web endpoints, etc.) to Modal.
- `modal shell [container-id]` - Open an interactive shell in a container.
- `modal container exec <id> -- <cmd>` - Execute a command in a running container.
- `modal container list` / `modal container stop <id>` - Manage containers.
- `modal app logs <app_name>` - Stream logs for a deployed app. Note: you need to use `Ctrl+C` to interrupt the stream.
- `modal app info <app>` / `modal app list` / `modal app stop <app>` / `modal app rollback <app>` - Manage apps.

### Resource management

- `modal volume list/create/get/put/rm/snapshot` - Manage Volumes.
- `modal dict list/get/set` - Manage Dicts.
- `modal queue list/get` - Manage Queues.
- `modal secret list/create/delete` - Manage Secrets.
- `modal environment list/create` - Manage Environments.
- `modal billing rates/report/summary` - Billing and cost reporting.
- `modal image logs <image>` - Image build logs.
- `modal function list` / `modal function stats` / `modal function metrics` - Function usage and metrics.
- `modal server list` / `modal endpoint list` - Servers and endpoints.
- `modal token new` / `modal token set` - Authentication.
- `modal workspace` - Workspace management.

### Inspecting and debugging

- `modal run -i` - Run interactively with a REPL.
- `modal.interact()` - Attach an interactive session from inside a function.
- `breakpoint()` works inside Modal functions.
- Set `MODAL_LOGLEVEL=DEBUG` and `MODAL_TRACEBACK=1` for verbose output.
- `modal.enable_output()` wraps `app.deploy()` for more deployment output.

## Testing and debugging

- When using `app.deploy()`, you can wrap it in a `with modal.enable_output():` block to get more output.
- `modal run` validates the app locally before executing remotely; use `modal deploy` for production.
- Use `modal serve` for hot-reload development of web endpoints.
- Debug with `print()` (output streams to the client), `modal app logs`, or `modal container exec`.
- For interactive debugging, use `modal shell` or `modal.interact()`.

## Resource and GPU notes

- Modal containers have minimums: 0.125 CPU cores and 128 MiB memory per container; CPU is priced per physical core (1 physical core = 2 vCPU).
- Memory is billed on max(requested, used); CPU on max(requested, used).
- Billing includes app load, input processing, and the scaledown window (default 60 s after the last input).
- GPU usage requires a payment method on the account; run with CPU-only gating if you need CPU-only mode.
- Free tier covers roughly 270 hours/month of CPU-only usage; GPU hours are billed separately.

## Deprecations (do not use in new code)

| Deprecated | Replacement |
|---|---|
| `@modal.web_endpoint` | `@modal.fastapi_endpoint` |
| `modal.build` | `Image.run_function` or `Volume` |
| `Mount`, `mount=`, `Image.copy_mount`, `Image.copy_local_file`, `Image.copy_local_dir` | `Image.add_local_*` |
| `.lookup()` | `.from_name()` (use `.hydrate()` for metadata) |
| `modal.gpu.*` objects | GPU strings (`"T4"`, `"H100"`, ...) |
| `allow_concurrent_inputs` | `@modal.concurrent` |
| `max_inputs` (on function/cls) | `single_use_containers` |
| `NetworkFileSystem` | `Volume` / `CloudBucketMount` |
| `Sandbox.open`, `ls`, `mkdir`, `rm`, `watch`, `FileIO` | `Sandbox.filesystem.*` |
| static `.delete()` / `.create_deployed()` | `.objects.delete()` / `.objects.create()` |
| `cidr_allowlist` | `outbound_cidr_allowlist` |
| `.resolve()` | `.hydrate()` |
| `wrap_returned_exceptions` | (removed) |
| `environment_name`, `namespace`, `pty_info`, `client` params | (removed) |
| `grpclib.GRPCError` | `modal.Error` subclasses |

## Important notes

### Storage

- **`/data` is persistent**: This is the only directory that survives between sessions. Save all your important work here.
- **`/root` is ephemeral**: Your home directory resets on every container start. Dotfiles, installed packages, and configs in `/root` will be wiped.

### Idle Timeouts and Cost

- Auto-shutdown timers save cost; Modal bills for the entire run including idle time.
- Use `scaledown_window` to control how long containers stay warm after the last input.

### Modal Platform Constraints

Modal containers run in a sandboxed environment. Here are some things to be aware of:

- **Init system**: Containers use `dumb-init`, not `systemd`. You won't have systemd services available.
- **No virtualization**: Containers don't have access to `/dev/kvm`, so you can't run VMs or nested virtualization.
- **No Docker/containerd**: Running Docker or containerd inside a Modal container is not supported.
- **No Unix sockets**: Modal doesn't support Unix sockets. This means services like MariaDB that rely on them won't work out of the box.
- **No Homebrew**: `brew` does not work inside Modal containers.
- **No `sudo` by default**: You're already running as `root`, so `sudo` isn't needed (or installed by default).
- **`htop` readings**: Modal containers run on massive shared instances. `htop` shows host-level resource usage, not your container's allocated resources. Don't trust the CPU/RAM percentages you see there.

### Secrets — How They Work

DevBox uses Modal Secrets to securely pass credentials into containers at runtime. Here's the flow:

1. You create secrets locally with `modal secret create <name> KEY="value"`
2. Modal stores them encrypted and injects them as environment variables inside the container
3. DevBox code reads them via `os.environ.get()` — they never appear in your code

### Understanding GGUF Model Names

If you're using the llama.cpp Research Center, you'll see model filenames like `gemma-3-4b-it-Q4_K_S.gguf`. Here's what each part means:

| Part | Meaning | Example |
|------|---------|---------|
| **Model family** | The base model | `gemma-3`, `qwen2.5-coder` |
| **Version** | Model generation | `3`, `2.5` |
| **Parameter count** | Model size | `4b` (4 billion), `7b` (7 billion) |
| **Tuning** | Training type | `it` (instruction-tuned), blank (base) |
| **Quantization** | Compression level | `Q4_K_S` (4-bit, small), `Q5_K_M` (5-bit, medium) |

Lower quantization = smaller file, faster inference, slightly lower quality. Higher quantization = better quality but needs more RAM.

## Troubleshooting

### "Secret not found" errors

Make sure you've created all the required secrets. Run `modal secret list` to check what's stored. If a secret is missing, recreate it with the `modal secret create` commands from the Setup section.

### SSH key not working or stale keys

If you've regenerated your SSH key or it's just not connecting, old keys might be lingering on Modal's side. Delete the stale secret and reinsert it:

```bash
modal secret delete ssh-public-key
modal secret create ssh-public-key PUBKEY="$(cat ~/.ssh/id_rsa.pub)"
```

### First build taking forever

Yep, that's normal. The first run takes 30-45 minutes because Modal is building the container image from scratch. Grab a coffee, stretch your legs — subsequent runs will be instant.

### Container terminated unexpectedly

Usually caused by network hiccups on your end. If you're running in attached mode (`modal run devbox.py`), a dropped connection can kill the container. Try running in detached mode instead:

```bash
modal run -d devbox.py
```

Just don't forget to terminate it when you're done 🙂

### "Payment method" errors on GPU functions

If you see `Please add a payment method to use A10G GPU functions` (or similar for T4/L4), Modal is validating the GPU launchers at app startup — even if you only wanted a CPU box. Either add a payment method, or run in CPU-only mode:

```bash
DEVBOX_CPU_ONLY=1 modal run devbox.py
```

On Windows PowerShell the assignment must target the environment, or Modal never sees it:

```powershell
$env:DEVBOX_CPU_ONLY = "1"; modal run devbox.py
```

## Thanks & Inspirations

- Using Google's Colaboratory as a VPS - [Ragug/colab-as-Vps](https://github.com/Ragug/colab-as-Vps)
- OpenCode and Oh-My-Opencode for programming assistance for tough concepts - [anomalyco/opencode](https://github.com/anomalyco/opencode) | [code-yeongyu/oh-my-opencode](https://github.com/code-yeongyu/oh-my-opencode)

## The Project Is Open To Your Contributions And Or Optimizations 🙏
