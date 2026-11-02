"""Structural tests for the Forensics box toolset.

These inspect the source tree instead of importing Modal, matching
tests/test_image_packaging.py and tests/test_prohibited_packages.py.
"""

import ast
import pathlib
import re

from devbox_core import config

ROOT = pathlib.Path(__file__).resolve().parent.parent
IMAGES = ROOT / "devbox_core" / "images.py"
SHARED_RUNTIME = ROOT / "runtime" / "shared_runtime.py"

EXPECTED_APT = {"nmap", "smbclient", "chntpw", "dislocker", "libbde-utils", "libvmdk-utils"}
EXPECTED_PIP = {"pypykatz", "impacket"}


def _image_sources() -> dict[str, str]:
    """Every module-level `<name>_image = ...` assignment, as source text."""
    source = IMAGES.read_text(encoding="utf-8")
    return {
        node.targets[0].id: ast.get_source_segment(source, node) or ""
        for node in ast.parse(source).body
        if isinstance(node, ast.Assign)
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id.endswith("_image")
    }


def test_forensic_package_lists_are_defined():
    assert set(config.FORENSIC_APT_PACKAGES) == EXPECTED_APT
    assert set(config.FORENSIC_PIP_PACKAGES) == EXPECTED_PIP


def test_forensic_packages_are_not_on_the_denylist():
    for packages in (config.FORENSIC_APT_PACKAGES, config.FORENSIC_PIP_PACKAGES):
        assert config.find_prohibited_packages(packages) == []


def test_no_cracking_tools_were_smuggled_in():
    """Password recovery stays out of scope; only unlocking is supported."""
    combined = {p.lower() for p in config.FORENSIC_APT_PACKAGES + config.FORENSIC_PIP_PACKAGES}
    for banned in ("john", "john-data", "hashcat", "bitlocker2john", "rockyou"):
        assert banned not in combined


def test_forensic_image_splats_both_package_groups():
    segment = _image_sources()["forensic_analysis_image"]
    assert "*FORENSIC_APT_PACKAGES" in segment
    assert "*FORENSIC_PIP_PACKAGES" in segment


def test_only_the_forensic_image_gets_the_extras():
    for name, segment in _image_sources().items():
        if name == "forensic_analysis_image":
            continue
        assert "FORENSIC_APT_PACKAGES" not in segment, name
        assert "FORENSIC_PIP_PACKAGES" not in segment, name


def test_pspy_version_is_a_pinned_tag():
    assert re.fullmatch(r"v\d+\.\d+\.\d+", config.PSPY_VERSION), config.PSPY_VERSION


def test_pspy_is_fetched_from_the_pinned_release_not_latest():
    source = IMAGES.read_text(encoding="utf-8")
    assert "/pspy/releases/download/{PSPY_VERSION}/pspy64" in source
    assert "/releases/latest" not in source


def test_pspy_download_is_checksum_verified():
    source = IMAGES.read_text(encoding="utf-8")
    checksum_lines = [
        line for line in source.splitlines() if "sha256sum -c" in line and "pspy64" in line
    ]
    assert len(checksum_lines) == 1, checksum_lines
    digest = re.search(r"\b([0-9a-f]{64})\b", checksum_lines[0])
    assert digest, checksum_lines[0]


def test_forensic_banner_warns_about_fuse_mounts():
    source = SHARED_RUNTIME.read_text(encoding="utf-8")
    assert "if forensic:" in source
    forensic_block = source.split("if forensic:", 1)[1]
    assert "/dev/fuse" in forensic_block
    assert "7z x" in forensic_block
