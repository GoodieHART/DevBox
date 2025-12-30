# Modal Personal DevBox Launcher

## Backstory

I'm not a developer with a fancy laptop. My setup is humble, just my trusty old Samsung phone. This is my digital workhorse:

```
u0_a191 @localhost
-----------------
OS: Android 7.1.1 armv7l
Host: samsung SM-G600S
Kernel: 3.10.49-13209801
CPU: Qualcomm MSM8916 (4) @ 998MHz
Memory: 1484MiB / 1889MiB
```

As you can see, it's not exactly a powerhouse. Trying to do any kind of serious work on it was a constant struggle. The phone would get hot enough to be uncomfortable, lag at the worst possible times, and just couldn't handle the tools I wanted to experiment with. It was frustrating.

Then, I remembered hearing about Modal and its serverless platform. A lightbulb went on. What if I could stop fighting my phone's limitations and just... bypass them? The idea was born: to create a simple way to launch a powerful, full-featured development environment in the cloud, offloading all the heavy lifting.

This project is the result of that idea. It's a script that lets me—and you—spin up a personal DevBox from anywhere, turning even a modest device into a portal to a powerful remote machine.

## Overview

This repository contains a Modal script (`devbox.py`) for launching a secure, personal, and on-demand remote development environment (DevBox). It provides a flexible and cost-effective way to get a powerful, cloud-based development environment with persistent storage, accessible via SSH.

The script launches a general-purpose DevBox, a Debian environment with essential development tools, and allows for the dynamic installation of extra packages at launch time.

## Features

-   **Standard DevBox**: A general-purpose Debian environment with essential development tools (`git`, `vim`, `curl`, `build-essential`, etc.). Allows for dynamic installation of extra `apt` packages at launch time.
-   **GPU DevBoxes**: T4, L4, and A10G GPU instances for machine learning and compute-intensive tasks.
-   **Document Processing Box**: Pandoc + Full TeX Live for academic and technical writing.
-   **Gemini CLI Box**: AI-powered development assistant with pre-installed Google Gemini CLI.
-   **Windows Sandbox**: Functional Windows containers via RDP (✅  Works with Modal Sandboxes).
-   **Persistent Storage**: Uses `modal.Volume` to provide a persistent `/data` directory, ensuring your work is saved between sessions.
-   **Secure SSH Access**: Automatically injects your public SSH key for secure, passwordless access.
-   **Auto-Shutdown**: Includes an idle timer that automatically shuts down the container after 5 minutes of inactivity to save costs.
-   **Resource Allocation**: The environment is configured with appropriate CPU and memory resources for its intended task.
-   **Interactive Launcher**: A simple command-line prompt to customize your DevBox at launch.

### Key Architectures and Virtualization Limitations

**Modal Functions Architecture:**
- Serverless execution model using Python functions
- Automatic scaling and resource management
- Requires Python runtime environment
- No direct access to host devices or capabilities
- Cannot run KVM-based virtualization
- Suitable for stateless workloads and APIs

**Modal Sandboxes Architecture:**
- Interactive container execution with arbitrary code
- Uses gVisor container runtime for strong isolation and security
- Supports any container image and runtime (including Windows)
- Virtualized networking environment with restricted device access
- No access to `/dev/kvm`, `/dev/net/tun`, or `NET_ADMIN` capabilities
- Cannot run KVM-based virtualization inside containers
- Suitable for stateful applications and interactive sessions

**Virtualization Limitations:**
- **KVM Hardware Access**: Modal sandboxes cannot access host KVM devices for hardware virtualization
- **Network Device Access**: No access to `/dev/net/tun` for network tunneling or bridging
- **Linux Capabilities**: Missing `NET_ADMIN` capability required for network configuration
- **gVisor Isolation**: Strong security isolation prevents privileged operations needed for VM hosting

**dockurr/windows Requirements vs Modal Limitations:**
- dockurr/windows requires: `/dev/kvm`, `/dev/net/tun`, `NET_ADMIN` capability
- Modal sandboxes provide: gVisor isolation, virtual networking, no device passthrough
- Result: dockurr/windows cannot create Windows VMs in Modal sandbox environment

**Sources:**
- [Modal Functions Documentation](https://modal.com/docs/guide/functions)
- [Modal Sandboxes Documentation](https://modal.com/docs/guide/sandboxes)
- [gVisor Security Model](https://gvisor.dev/docs/architecture/)
- [dockurr/windows Requirements](https://github.com/dockur/windows)

**Network Interface Auto-Detection:**
The system automatically detects the correct network interface name in Modal sandboxes by trying common interface names (eth0, ens4, enp0s3, eno1, enp1s0, eth1) and attempting dynamic detection. This resolves the "Network interface does not exist" error.

## Prerequisites

Before you can use this script, you need to have the following:

1.  **Python**: Python 3.8 or newer installed on your local machine.
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

## Setup

The script requires your **public SSH key** to be stored in a Modal Secret.

1.  **Find your public key**: Your public key is usually located at `~/.ssh/id_rsa.pub`. Copy the entire content of this file.

2.  **Create a Modal Secret**: Create a secret on Modal named `ssh-public-key` with a key of `PUBKEY`.

    You can do this from your terminal:
    ```bash
    modal secret create ssh-public-key PUBKEY="$(cat ~/.ssh/id_rsa.pub)"
    ```
    This command creates the secret and securely stores your public key in it.

## Usage

Once the setup is complete, you can launch a DevBox by running the script:

```bash
modal run devbox.py
```

You will be prompted to enter any additional `apt` packages you want to install (e.g., `htop tmux`).

After making a selection, Modal will build the container image (if it's the first time) and start the environment. Once ready, it will print the SSH command you need to connect:

```
🚀 Your DevBox is ready!
Paste this command into your terminal:

ssh root@<host> -p <port>
```

Copy and paste this command into a new terminal window to connect to your remote DevBox.

### Alias for Quick Launch

To make launching your DevBox even faster, you can create an alias for the `modal run devbox.py` command in your shell configuration file (e.g., `.bashrc`, `.zshrc`, or PowerShell profile).

**For Bash/Zsh:**

Add the following line to your `~/.bashrc` or `~/.zshrc` file:

```bash
alias devbox="modal run /path/to/your/modal-terminal/devbox.py"
```

Remember to replace `/path/to/your/modal-terminal/` with the actual path to your `devbox.py` file. After saving, reload your shell configuration:

```bash
source ~/.bashrc  # or source ~/.zshrc
```

Now you can simply type `devbox` in your terminal to launch your DevBox.

**For PowerShell:**

Add the following lines to your PowerShell profile (you can open it by typing `$profile` and then `notepad $profile` in PowerShell):

```powershell
function Start-DevBox { modal run C:\path\to\your\modal-terminal\devbox.py }
Set-Alias -Name devbox -Value Start-DevBox
```

Remember to replace `C:\path\to\your\modal-terminal\devbox.py` with the actual path to your `devbox.py` file. After saving, restart PowerShell or run `. $profile`.

### Important Notes

-   **Persistent Storage**: Only the `/data` directory is persistent. Your home directory (`/root`) is ephemeral and will be reset every time the container starts. **Always save your important work in the `/data` directory.**
-   **Idle Timeout**: The container will automatically shut down after 5 minutes if there is no active SSH connection. A countdown will be displayed in the terminal where you ran the `modal run` command.
-   **Package Installation**: If you need `python`, type `python-is-python3` in the package list to ensure the correct Debian package is installed. The script handles this replacement automatically if you enter `python`.

## The Project Is Open To Your Contributions And Or Optimizations 🙏
