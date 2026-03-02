# Modal Personal DevBox Launcher

## Backstory

Most of us aren't privileged enough to buy those high end PCs or pay for cloud VPS subscriptions from AWS GCP and the rest. We mostly stick to their free tiers which lets be real are super limited. I mean, I speak for the majority of us who have ever used any of them. But either ways, we are forever grateful for the generosity from the companies 🙏.

### The Rabbit Hole Journey

I am one of those guys who has watched nearly every YouTube video promising "free VPS servers". Man that was a wild and fun rabbit hole. It exposed me to a ton of scripts clever workarounds, which ultimately shaped my knowledge in networking and Linux as a whole. Still got a long way to go sha, but it was a good run.

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

Yeah not exactly a powerhouse this phone. Most stuff i did on it was through Termux and trying to do any kind of serious work on it was a constant struggle. The thing would get hot enough to be uncomfortable lag at the worst possible moments 😭 and just couldn't handle the tools I wanted to experiment with. It was frustrating but i loved the little guy either ways 😆

I did also have a laptop with entry level specs but bandwidth data where I'm from is a huge problem and really expensive. Downloading large packages was a straight up NO GO zone!

### Discovering Modal and the Spark

I don't even remember exactly how I stumbled across Modal but I'm seriously grateful it happened. I played around on the platform a little, started connecting pieces and components together then bam! the idea struck and DevBox was born.

### My Conviction and Closing Note

One thing has always been crystal clear to me though, true innovation comes from the most trying and difficult times in a person's life. You look at every available option and alternative, dig deeper than anyone else into a specific problem, and just when everything feels pointless BAM! you hit a breakthrough. One that doesn't just solve your problem but ends up helping others too

My brothers and sisters the world is EVIL But do not conform to the pattern of this world. Love one another, help others in need and be the reason someone smiles today 😊

I hope you enjoy using DevBox as much as I am!

## Overview

This repository contains a Modal script (`devbox.py`) for launching a secure, personal, and on-demand remote development environment (DevBox). It provides a flexible and cost-effective way to get a powerful, cloud-based development environment with persistent storage, accessible via SSH.

The script launches a general-purpose DevBox, a Debian environment with essential development tools, and allows for the dynamic installation of extra packages at launch time.

## Features

-   **Standard DevBox**: A general-purpose Debian environment with essential development tools (`git`, `vim`, `curl`, `build-essential`,  etc.). Allows for dynamic installation of extra `apt` packages at launch time.
-   **Persistent Storage**: Uses a `modal.Volume` to provide a persistent `/data` directory, ensuring your work is saved between sessions.
-   **Secure SSH Access**: Automatically injects your public SSH key for secure, passwordless access.
-   **Auto-Shutdown**: Includes an idle timer that automatically shuts down the container after 5 minutes of inactivity to save costs.
-   **Resource Allocation**: The environment is configured with appropriate CPU and memory resources for its intended task.
-   **Interactive Launcher**: A simple command-line prompt to customize your DevBox at launch.

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
> This will work on both Windows, Mac & Linux Machines

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

> FYI: Because of the various image definitions currently, during the first run, expect it's setup completion in about 30-45 mins. After that, subsequent runs are instant.

You'll be welcomed with the quotes and configuration menus, you then will be prompted to enter any additional `apt` packages you want to install (e.g., `htop tmux`).

After making a selection, Modal will build the container image (if it's the first time) and start the environment. Once ready, it will print the SSH command you need to connect:

```
🚀 Your DevBox is ready!
Paste this command into your terminal:

ssh root@<host> -p <port>
```
> Currently the default user is "root"

Copy and paste this command into a new terminal window to connect to your remote DevBox.

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

### Important Notes

-   **Persistent Storage**: Only the `/data` directory is persistent. Your home directory (`/root`) is ephemeral and will be reset every time the container starts. **Always save your important work in the `/data` directory.**
-   **Idle Timeout**: The container will automatically shut down after 5 minutes if there is no active SSH connection. A countdown will be displayed in the terminal where you ran the `modal run` command.
-   **Package Installation**: If you need `python`, type `python-is-python3` in the package list to ensure the correct Debian package is installed. The script handles this replacement automatically if you enter `python`.

## Notes On The Use and Improvement Of The Script
- The first build will take at least 45mins, but subsequent runs will be much faster.
- Some refactoring and component tracing is still going on ("MAJOR REFACTOR" gone wrong at some point 😅)


> .... still in progress, more content will be added, still compiling essentials.


## Important Docs For Better Understanding
- Modal's Official Docs - https://modal.com/docs
- Gvisor Runtime - https://gvisor.dev/

> .... still in progress, more content will be added, still compiling essentials.

## Thanks & Inspirations
- Using Google's Colaboratary as a VPS - (https://github.com/Ragug/colab-as-Vps)
- OpenCode and Oh-My-Opencode for programming assistance for tough concepts - https://github.com/anomalyco/opencode | https://github.com/code-yeongyu/oh-my-opencode

> .... still in progress, more content will be added, still compiling essentials.

## The Project Is Open To Your Contributions And Or Optimizations 🙏