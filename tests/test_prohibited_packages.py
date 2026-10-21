"""Tests for the prohibited-package denylist.

Covers the denylist definitions in `devbox_core/config.py` and the two
enforcement points: every image build (`devbox_core/images.py`) and the
runtime `extra_packages` install path (`runtime/shared_runtime.py`).
"""

import ast
import pathlib

from devbox_core import config

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _source(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def _tree(name: str) -> ast.Module:
    return ast.parse(_source(name))


# --- denylist contents ---


def test_denylist_covers_headline_tools():
    for name in ("xmrig", "xmr-stak", "cgminer", "cpuminer-multi", "hashcat", "john"):
        assert name in config.PROHIBITED_PACKAGES_DENYLIST


def test_mining_and_cracking_denylists_are_separate_definitions():
    assert config.MINING_PACKAGES_DENYLIST
    assert config.CREDENTIAL_CRACKING_PACKAGES_DENYLIST
    assert not (config.MINING_PACKAGES_DENYLIST & config.CREDENTIAL_CRACKING_PACKAGES_DENYLIST)
    assert config.PROHIBITED_PACKAGES_DENYLIST == (
        config.MINING_PACKAGES_DENYLIST | config.CREDENTIAL_CRACKING_PACKAGES_DENYLIST
    )


# --- matching behaviour ---


def test_miners_and_crackers_are_denied():
    denied = [
        "xmrig",
        "xmr-stak",
        "cgminer",
        "bfgminer",
        "cpuminer-multi",
        "ethminer",
        "kdevtmpfsi",
        "hashcat",
        "john",
    ]
    assert config.find_prohibited_packages(denied) == denied


def test_ordinary_development_packages_are_allowed():
    allowed = [
        "git",
        "curl",
        "wget",
        "build-essential",
        "clang",
        "cmake",
        "htop",
        "nano",
        "neovim",
        "openssh-server",
        "python3-dev",
        "pandoc",
        "texlive-full",
        "xrdp",
        "xfce4",
        "gdb",
        "binwalk",
        "tshark",
        "wabt",
        "volatility3",
        "pciutils",
        "lshw",
        "zstd",
        "libssl3",
        "libcurl4",
        "zlib1g",
        "procps",
        "unzip",
        "p7zip-full",
        "megatools",
        "nodejs",
        "jq",
        "ripgrep",
        "imagemagick",
    ]
    assert config.find_prohibited_packages(allowed) == []


def test_apt_spec_variants_cannot_smuggle_a_denied_package():
    for spec in (
        "hashcat=6.2.6-1",
        "hashcat/stable",
        "hashcat:amd64",
        "XMRIG",
        "  xmrig  ",
        "./xmrig.deb",
        "/tmp/xmrig",
        "xmrig-custom",
        "john-data",
    ):
        assert config.find_prohibited_packages([spec]) == [spec]


def test_similar_names_are_not_false_positives():
    allowed = ["johnny", "trexy", "maven", "xmrigx", "hashcats", "miner"]
    assert config.find_prohibited_packages(allowed) == []


def test_validate_raises_and_names_the_offending_package():
    try:
        config.validate_prohibited_packages(["git", "xmrig"])
    except ValueError as exc:
        message = str(exc)
    else:
        raise AssertionError("expected ValueError for a prohibited package")

    assert "xmrig" in message
    assert "git" not in message


def test_validate_accepts_allowed_packages():
    assert config.validate_prohibited_packages(["git", "build-essential"]) is None
    assert config.validate_prohibited_packages([]) is None
    assert config.validate_prohibited_packages(None) is None


def test_shipped_package_lists_are_clean():
    for packages in (
        config.CORE_DEV_PACKAGES,
        config.EXTENDED_DEV_PACKAGES,
        config.DOWNLOAD_APT_PACKAGES,
    ):
        assert config.find_prohibited_packages(packages) == []


# --- enforcement wiring ---


def test_every_image_apt_install_goes_through_the_guard():
    tree = _tree("devbox_core/images.py")
    guard = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_apt_install"
    )
    guarded = {
        id(node)
        for node in ast.walk(guard)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "apt_install"
    }
    unguarded = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "apt_install"
        and id(node) not in guarded
    ]
    assert unguarded == []


def test_no_apt_get_install_outside_the_runtime_guard():
    tree = _tree("runtime/shared_runtime.py")
    guard = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "install_extra_packages"
    )
    guarded = {id(node) for node in ast.walk(guard)}

    offenders = []
    for node in ast.walk(tree):
        if id(node) in guarded or not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute) or node.func.attr != "run":
            continue
        if not node.args or not isinstance(node.args[0], ast.List):
            continue
        elements = node.args[0].elts
        if elements and isinstance(elements[0], ast.Constant) and elements[0].value == "apt-get":
            offenders.append(node)

    assert offenders == []


def test_runtime_guard_validates_before_apt_get_update():
    guard = next(
        node
        for node in _tree("runtime/shared_runtime.py").body
        if isinstance(node, ast.FunctionDef) and node.name == "install_extra_packages"
    )
    calls = [
        node
        for node in ast.walk(guard)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "validate_prohibited_packages"
    ]
    assert calls, "install_extra_packages must validate before installing"

    validate_line = calls[0].lineno
    apt_lines = [
        node.lineno
        for node in ast.walk(guard)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "run"
        and node.args
        and isinstance(node.args[0], ast.List)
        and node.args[0].elts
        and isinstance(node.args[0].elts[0], ast.Constant)
        and node.args[0].elts[0].value == "apt-get"
    ]
    assert apt_lines
    assert all(line > validate_line for line in apt_lines)


# --- documentation ---


def test_readme_warnings_block_states_the_policy():
    readme = _source("README.md")
    assert "MINING_PACKAGES_DENYLIST" in readme
    assert "CREDENTIAL_CRACKING_PACKAGES_DENYLIST" in readme
    assert "https://modal.com/legal/terms" in readme
    assert "https://modal.com/blog/catching-cryptominers" in readme
