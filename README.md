# Modal Personal DevBox Launcher

## Table of Contents

- [Backstory](#backstory)
- [Quick Start](#quick-start)
- [Overview](#overview)
- [Features](#features)
- [Launcher Options](#launcher-options)
- [GPU Options](#gpu-options)
- [Prerequisites](#prerequisites)
- [Setup](#setup)
- [Connecting](#connecting)
- [Important Notes](#important-notes)
- [Troubleshooting](#troubleshooting)
- [Architecture](#architecture)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [Thanks & Inspirations](#thanks--inspirations)

## Backstory

Most of us aren't privileged enough to buy those high end PCs or pay for cloud VPS subscriptions from AWS, GCP, and the rest. We mostly stick to their free tiers which, let's be real, are super limited. But either way, we are forever grateful for the generosity from these companies 🙏.

### The AI Exploration Rabbit Hole

About a while back last year, I was actively exploring the AI landscape. And when I say explore, I mean *explore* — I was freaking looking into a lot of new technologies as they came to the space. New models, new prompting techniques, image and video generation, embeddings — I mean virtually everything! Heck, at one point I had wanted to train my own AI model 😅, but I told myself calm down, you no fit sabi everything (although, not totally crossed off my checklist yet 😉).

But anyone who's been in the AI space already knows you can't run AI models on potato hardware. Even at that, you can't get decent results from some models under 4B parameters, and from 4B above you're looking at purchasing expensive GPUs to get something going. Ayoo! Doesn't mean I didn't try running some models on my potato PC 😂, but damn was it slow. I'll leave this at that.

### My Hardware Reality

```
u0_a191 @localhost
-----------------
OS: Android 7.1.1 armv7l
Host: samsung SM-G600S
Kernel: 3.10.49-13209801
CPU: Qualcomm MSM8916 (4) @ 998MHz
Memory: 1484MiB / 1889MiB
```

Yeah not exactly a powerhouse this phone. Most stuff I did on it was through Termux and trying to do any kind of serious work on it was a constant struggle. The thing would get hot enough to be uncomfortable, lag at the worst possible moments 😭, and just couldn't handle the tools I wanted to experiment with. It was frustrating but I loved the little guy either ways 😆

```
Potato PC
---------
CPU: Intel Celeron N3150 @ 2.08GHz (max)
RAM: 8GB
```

I did also have a laptop with entry level specs but bandwidth data where I'm from is a huge problem and really expensive. Downloading large packages was a straight up NO GO zone!

### The VPS Search

At about the same time, I was also scanning the VPS landscape, constantly looking for an affordable but quality solution for my use case. Although the search didn't quite come out successfully because of my budget at the time.

### The Rabbit Hole Journey

I am one of those guys who has watched nearly every YouTube video promising "free VPS servers". Man that was a wild and fun rabbit hole. It exposed me to a ton of scripts clever workarounds, which ultimately shaped my knowledge in networking and Linux as a whole. Still got a long way to go sha, but it was a good run.

### Discovering Modal and the Spark

But as time moved on, I casually stumbled across this platform — Modal. Look man, I think this has got to be one of the most insane coincidences ever. *The AI Platform For Developers* was the first message I was greeted with on their website. Then I started looking around, read their docs, looked at their example codes, and went through their guide on how to get started.

I was experimenting, trying out their examples, noting down key points, ran some AI models I always wanted to try out, saw that their systems use Linux underneath the hood, saw in the docs the ability to expose ports as tunnels, saw storage functionality, and the mindmap just kept expanding — linking pieces together, running some awesome stuff from their docs. And boom, an idea emerged 💡.

### My Conviction and Closing Note

One thing has always been crystal clear to me though, true innovation comes from the most trying and difficult times in a person's life. You look at every available option and alternative, dig deeper than anyone else into a specific problem, and just when everything feels pointless BAM! you hit a breakthrough. One that doesn't just solve your problem but ends up helping others too.

My brothers and sisters the world is EVIL. But do not conform to the pattern of this world. Love one another, help others in need and be the reason someone smiles today 😊

Which brings me, ladies and gentlemen, to the main focus of my creation log and overview — DevBox.

I hope you enjoy using DevBox as much as I am!

## ⚠️ Warnings & Open Letter

I plead with all users of this project to refrain from any illegal activities on the Modal platform. This includes but is not limited to:

- **Cryptocurrency mining** — Do not use DevBox for mining any cryptocurrency
- **DDoS attacks** — Do not use this project to launch distributed denial-of-service attacks
- **Hosting illegal content** — Do not store or distribute illegal material
- **Spam & botnets** — Do not run spam operations or botnet infrastructure
- **Password cracking** — Do not use DevBox for unauthorized credential attacks
- **Any activity that violates Modal's Terms of Service**

It's common for people to try and abuse free or generous cloud platforms, which ultimately hurts legitimate experimenters, researchers, and developers who are just trying to learn, build, and create awesome stuff. Don't be that person.

---

**An open letter to the team at Modal:**

I plead with you to ban only the accounts of people who actively abuse your platform, and leave legitimate users be. The vast majority of us are here to experiment, learn, and build real things. Please don't let the actions of a few bad actors restrict the many who use your platform responsibly.

---

Thank you all for your understanding. Enjoy DevBox!

## Quick Start

Already got Python and a Modal account? You're 3 commands away from your first DevBox.

**Step 1:** Install the Modal CLI:

```bash
pip install modal
modal setup
```

**Step 2:** Set up your SSH key (DevBox needs this to let you in):

```bash
modal secret create ssh-public-key PUBKEY="$(cat ~/.ssh/id_rsa.pub)"
```

**Step 3:** Launch it:

```bash
modal run devbox.py
```

After a bit (first run takes 30-45 mins to build the image), you'll see something like this:

```
🚀 Your DevBox is ready!
Paste this command into your terminal:
ssh root@<host> -p <port>
```

Paste that SSH command into a new terminal and you're in. That's it.

> **Heads up:** Only the `/data` directory is persistent. Save your work there. Everything else resets on each launch.

For the full setup guide (all 3 secrets, GPU options, RDP, WebUI), check the sections below.
## Overview

This repository contains a Modal script (`devbox.py`) for launching a secure, personal, and on-demand remote development environment (DevBox). It provides a flexible and cost-effective way to get a powerful, cloud-based development environment with persistent storage, accessible via SSH.

The script launches a general-purpose DevBox, a Debian environment with essential development tools, and allows for the dynamic installation of extra packages at launch time.

## Features

-   **Standard DevBox**: A general-purpose Debian environment with essential development tools (`git`, `vim`, `curl`, `build-essential`, etc.). Supports optional GPU acceleration (T4, L4, A10G). Allows dynamic installation of extra `apt` packages at launch time.
-   **Persistent Storage**: Uses a `modal.Volume` to provide a persistent `/data` directory, ensuring your work is saved between sessions.
-   **Secure SSH Access**: Automatically injects your public SSH key for secure, passwordless access.
-   **Auto-Shutdown**: Includes an idle timer that automatically shuts down the container after 5 minutes of inactivity to save costs.
-   **Resource Allocation**: The environment is configured with appropriate CPU and memory resources for its intended task.
-   **Interactive Launcher**: A simple command-line prompt to choose from 7 specialized DevBox configurations.

## Launcher Options

When you run `modal run devbox.py`, you'll be presented with 7 DevBox configurations. Here's what each one does:

### 1. 🛠️ Standard DevBox

A general-purpose Debian environment with essential dev tools — `git`, `nano`, `neovim`, `curl`, `build-essential`, `clang`, `cmake`, `htop`, and more. You can optionally attach a GPU (T4, L4, or A10G) at launch. Install extra `apt` packages on the fly.

**Best for:** Everyday coding, scripting, compiling, general Linux work.

**Resources:** 0.5 vCPU / 1GB RAM (CPU) · 1.0 vCPU / 2GB RAM (GPU)

---

### 2. 📄 Document Processing Box

Comes with **Pandoc** and a full **TeX Live** distribution pre-installed. Convert between document formats (Markdown → PDF, LaTeX → HTML, etc.) with everything you need for professional document workflows.

**Best for:** LaTeX/PDF generation, academic papers, technical documentation, format conversion.

**Resources:** 1.0 vCPU / 2GB RAM

---

### 3. 🤖 AI Assistants Box

Pre-installed with **OpenCode** and **Gemini CLI** for AI-assisted coding sessions right out of the box.

**Best for:** AI-powered pair programming, code review, and development assistance.

**Resources:** 0.5 vCPU / 1GB RAM

---

### 4. 🧪 LLM Playroom

Comes with **Ollama** pre-installed. Pull and run any open-source model with a single command — no local hardware needed.

**Best for:** Running and testing open-source language models, AI experimentation.

**Resources:** 1.0 vCPU / 2GB RAM

---

### 5. 🖥️ RDP Desktop Box

A full **XFCE graphical desktop** accessible via RDP. Comes with `xrdp`, `xfce4`, and a suite of desktop goodies. Username is `root`, password is `devbox123`. Optional GPU acceleration available.

**Best for:** When you need a full desktop environment — GUI apps, browsers, visual workflows.

**Resources:** 1.0 vCPU / 2GB RAM (CPU) · 1.5 vCPU / 4GB RAM (GPU)

---

### 6. 🔬 llama.cpp Research Center

The most feature-rich box. Comes with a curated catalog of **7 pre-configured GGUF models** plus the ability to load any custom HuggingFace GGUF. Each model has individually tuned temperature, top_p, and top_k settings. Includes a built-in **WebUI** (SvelteKit-based chat interface on port 8080) and **EXA Search integration** for function-calling web search.

**Models available:**
- Qwen3.5-9B (General reasoning, 256K context)
- Dolphin3.0-3B (Fast, abliterated)
- DeepSeek-R1-7B-Uncensored (Math/science specialist)
- Qwen2.5-Coder-7B (Coding specialist)
- SmolVLM-500M (Image captioning)
- Gemma3-4B (Multimodal)
- Custom (Any HuggingFace GGUF URL)

**Note:** Model selection happens *after* you connect via SSH — you'll be prompted interactively.

**Resources:** 2.0 vCPU / 8GB RAM · 1 hour idle timeout

---

### 7. 🔍 Forensics Analysis Box

Comes with **Volatility3** and symbol files for Windows, Linux, and macOS pre-installed. Memory forensics is a branch of digital forensics that involves extracting evidence and artifacts from a RAM image or dump of a running computer. This lets you analyze running processes, environment variables, active network connections, loaded kernel modules, and much more.

**Best for:** CTF challenges, incident response, malware analysis, digital forensics investigations.

**Resources:** 0.5 vCPU / 1GB RAM

## GPU Options

Several DevBox types support optional GPU acceleration. Here's a quick comparison:

| GPU | Best For | VRAM |
|-----|----------|------|
| **T4** | Cost-effective inference, light workloads | 16 GB |
| **L4** | Newer architecture, better performance than T4 | 24 GB |
| **A10G** | Heavy workloads, more VRAM, highest performance | 24 GB |

> ⚠️ GPU usage incurs charges on your Modal account. See [modal.com/pricing](https://modal.com/pricing) for current rates.

For reference, Modal's free tier covers approximately **270 hours/month** of CPU-only usage. GPU hours are billed separately.

## Prerequisites

Before you can use this script, you need to have the following:

1.  **Python**: Python 3.10 or newer installed on your local machine.
2.  **Modal Account**: A free Modal account. You can sign up at [modal.com](https://modal.com/).
3.  **Modal CLI**: The `modal` Python library installed and configured.
    ```bash
    pip install modal
    modal setup
    ```
4.  **SSH Key Pair**: An SSH key pair generated on your local machine. If you don't have one, you can create it with:
    ```bash
    ssh-keygen -t rsa -b 4096
    ```
> This will work on both Windows, Mac & Linux Machines

## Setup

DevBox uses **Modal Secrets** to securely store your credentials. Here's what you need:

### Required: SSH Key

This is needed for **all** DevBox types. Without it, the container will still start but you won't be able to connect via SSH.

1. **Find your public key**: Your public key is usually at `~/.ssh/id_rsa.pub` (or `~/.ssh/id_ed25519.pub` if you use ed25519). Copy the entire content.

2. **Create the secret**:

```bash
modal secret create ssh-public-key PUBKEY="$(cat ~/.ssh/id_rsa.pub)"
```

### Optional: Gemini API Key

Only needed if you plan to use the **AI Assistants Box** (OpenCode + Gemini CLI). If missing, Gemini CLI will prompt you for the key on first use — no hard crash.

Get your key from [Google AI Studio](https://aistudio.google.com/apikey), then:

```bash
modal secret create gemini-api-key GEMINI_API_KEY="your-api-key-here"
```

### Optional: EXA API Key

Only needed if you plan to use the **llama.cpp Research Center** with web search. If missing, EXA Search is disabled and the box prints a warning, but everything else works fine.

Get your key from [EXA Platform](https://exa.ai/), then:

```bash
modal secret create exa-api-key EXA_API_KEY="your-api-key-here"
```

## Connecting

After launching your DevBox, Modal will print the connection info once the container is ready. How you connect depends on which box type you chose:

### SSH (All Boxes)

Every DevBox supports SSH access. Once ready, you'll see:

```
🚀 Your DevBox is ready!
Paste this command into your terminal:
ssh root@<host> -p <port>
```

Just copy and paste that command into a new terminal window and you're in.

### RDP (RDP Desktop Box)

The RDP Desktop Box gives you a full XFCE graphical desktop. Once ready, you'll see:

```
============================================================
🖥️ Your RDP Desktop is ready!
============================================================

📡 RDP Address: <host>:<port>
👤 Username: root
🔑 Password: devbox123

============================================================
```

Use those credentials with an RDP client:

| Platform | Recommended Client |
|----------|-------------------|
| **Android/iOS** | Haven SSH Client, aRDP, or Windows App |
| **Windows** | Built-in Remote Desktop (`mstsc.exe`) |
| **macOS** | [Microsoft Remote Desktop](https://apps.apple.com/app/microsoft-remote-desktop/id1295203466) (App Store) |
| **Linux** | [Remmina](https://remmina.org/) |

### WebUI (llama.cpp Research Center)

The llama.cpp Research Center includes a built-in **WebUI** — a browser-based chat interface powered by llama-server's SvelteKit frontend. Once ready, you'll see:

```
🌐 WebUI: http://<host>:<port>
   (Open in browser for chat interface)
```

Just paste that URL into any modern browser (Chrome, Firefox, Safari, Edge) and you'll get a full chat interface with your selected model. No additional setup needed.

### Alias for Quick Launch

To make launching your DevBox even faster, you can create an alias for the `modal run devbox.py` command in your shell configuration file (e.g., `.bashrc`, `.zshrc`, or PowerShell profile).

**For Bash/Zsh:**

Add the following line to your `~/.bashrc` or `~/.zshrc` file:

```bash
alias devbox="modal run -d /path/to/your/DevBox/devbox.py"
```

> Here i added the "-d" flag for the container to run in "detached" mode, when network hiccups occur, the instances are usually terminated when run with the normal "modal run devbox.py" command, but by using "modal run -d devbox.py" it runs without direct connection to your device, but uhm... Just don't forget to terminate when you're done 🙂

Remember to replace `/path/to/your/DevBox/` with the actual path to your `devbox.py` file. After saving, reload your shell configuration:

```bash
source ~/.bashrc  # or source ~/.zshrc
```

Now you can simply type `devbox` in your terminal to launch your DevBox.

**For PowerShell:**

Add the following lines to your PowerShell profile (you can open it by typing `$profile` and then `notepad $profile` in PowerShell):

```powershell
function Start-DevBox { modal run C:\path\to\your\DevBox\devbox.py }
Set-Alias -Name devbox -Value Start-DevBox
```

Remember to replace `C:\path\to\your\DevBox\devbox.py` with the actual path to your `devbox.py` file. After saving, restart PowerShell or run `. $profile`.

## Important Notes

### Storage

- **`/data` is persistent**: This is the only directory that survives between sessions. Save all your important work here.
- **`/root` is ephemeral**: Your home directory resets on every container start. Dotfiles, installed packages, and configs in `/root` will be wiped.

### Idle Timeouts

- **Standard boxes**: Auto-shutdown after **5 minutes** of no active SSH connection.
- **llama.cpp Research Center**: Extended timeout of **1 hour** to accommodate long-running inference sessions.
- A countdown warning will appear in the terminal where you ran `modal run` before shutdown.

### First Build Time

The first run will take **30-45 minutes** to build the container image. Subsequent runs are instant — Modal caches the image so you're up and running in seconds.

### Cost Estimate

Running a Standard DevBox for 1 hour costs approximately **$0.20**. GPU usage incurs additional charges — see [modal.com/pricing](https://modal.com/pricing) for current rates.

### Modal Platform Constraints

Modal containers run in a sandboxed environment. Here are some things to be aware of:

- **Init system**: Containers use `dumb-init`, not `systemd`. You won't have systemd services available.

  ```sh
  root@modal:/data# ps -p 1 -o comm=
  dumb-init
  root@modal:/data#
  ```

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

| Secret | Env Var | Required For | If Missing |
|--------|---------|-------------|------------|
| `ssh-public-key` | `PUBKEY` | All boxes | Container starts, but you can't SSH in |
| `gemini-api-key` | `GEMINI_API_KEY` | AI Assistants Box | Gemini CLI prompts for key on first use |
| `exa-api-key` | `EXA_API_KEY` | llama.cpp Research Center | EXA Search disabled, everything else works |

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

### RDP not connecting

Double-check the address, username, and password printed when the container started. Make sure your RDP client is connecting to the right port. If you're on mobile, try a different client — some can be finicky.

### llama.cpp model download fails

Check your internet connection and make sure the HuggingFace URL is valid. Some models require you to be logged in to HuggingFace — if it's a gated model, you'll need to set up HF token authentication. Try a different model from the catalog first to isolate the issue.

## Architecture

The codebase is currently flat — all files live in the root directory. A structure rehaul is planned for the future, but for now here's what each file does:

| File | Purpose |
|------|---------|
| `devbox.py` | Main launcher — interactive menu, Modal function definitions, entry point |
| `config.py` | Resource allocations (CPU, memory, timeouts), package lists, GPU configs |
| `images.py` | Container image definitions for all 7 DevBox types |
| `shared_runtime.py` | Shared runtime logic — SSH/RDP idle monitoring, auto-shutdown, connection output |
| `utils.py` | SSH key injection utility |
| `gpu_utils.py` | GPU configuration helpers and base GPU launch args |
| `exa_helper.py` | EXA Search integration for llama.cpp Research Center |
| `quotes_loader.py` | Random motivational quotes displayed at launcher startup |
| `quotes.json` | Quote catalog loaded by `quotes_loader.py` |
| `ui_utils.py` | UI helper functions — `create_box()`, `show_spinner()` |
| `backup_utils.py` | Backup registration and data persistence helpers |
| `persistence_utils.py` | Symlink management for dotfiles persistence across sessions |

## Roadmap

See [ROADMAP.md](ROADMAP.md) for planned improvements and future work.

## Contributing

The project is open to contributions and optimizations. No formal guidelines yet — just make sure your changes work and don't break existing functionality. If you want to add a new DevBox type, look at how the existing ones are defined in `devbox.py` and `images.py` — they follow a consistent pattern.

## Thanks & Inspirations

- Using Google's Colaboratory as a VPS - [Ragug/colab-as-Vps](https://github.com/Ragug/colab-as-Vps)
- OpenCode and Oh-My-Opencode for programming assistance for tough concepts - [anomalyco/opencode](https://github.com/anomalyco/opencode) | [code-yeongyu/oh-my-opencode](https://github.com/code-yeongyu/oh-my-opencode)

## The Project Is Open To Your Contributions And Or Optimizations 🙏