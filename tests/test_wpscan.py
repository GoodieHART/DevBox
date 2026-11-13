"""Tests for the WPScan/Ruby stack in the Forensics image.

WPScan is a gem, so its version and Ruby toolchain live in `config.py` and the
install step in `images.py`. 4.x needs Ruby >= 3.3; bookworm ships 3.1, so the
pin stays on 3.x.
"""

import pathlib

from devbox_core import config

ROOT = pathlib.Path(__file__).resolve().parent.parent


def source(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def _forensic_block() -> str:
    images = source("devbox_core/images.py")
    return images.split("forensic_analysis_image = (", 1)[1].split(
        "llm_playroom_image", 1
    )[0]


def test_wpscan_version_is_pinned_below_the_ruby_4x_requirement():
    parts = tuple(int(part) for part in config.WPSCAN_VERSION.split("."))
    assert len(parts) == 3
    assert parts < (4, 0, 0), (
        "WPScan 4.x requires Ruby >= 3.3; Debian bookworm ships Ruby 3.1, so "
        "the pinned version must stay on 3.x"
    )


def test_wordpress_package_groups_carry_the_ruby_toolchain():
    assert config.WORDPRESS_GEM_PACKAGES == ["wpscan"]
    for package in ("ruby", "ruby-dev", "build-essential", "libcurl4"):
        assert package in config.WORDPRESS_APT_PACKAGES


def test_forensic_image_installs_the_gem_after_the_ruby_toolchain():
    forensic = _forensic_block()
    assert "*WORDPRESS_APT_PACKAGES" in forensic
    assert "gem install" in forensic
    assert "WPSCAN_VERSION" in forensic
    assert "--no-document" in forensic
    assert "--bindir /usr/local/bin" in forensic
    assert "test -x /usr/local/bin" in forensic
    assert forensic.index("*WORDPRESS_APT_PACKAGES") < forensic.index("gem install")


def test_wpscan_is_installed_only_in_the_forensics_image():
    images = source("devbox_core/images.py")
    assert images.count("*WORDPRESS_APT_PACKAGES") == 1
    assert images.count("gem install") == 1


def test_wpscan_is_allowed_by_the_denylist():
    packages = list(config.WORDPRESS_APT_PACKAGES) + list(config.WORDPRESS_GEM_PACKAGES)
    assert config.find_prohibited_packages(packages) == []


def test_readme_lists_wpscan_for_the_forensics_box():
    readme = source("README.md")
    assert "WPScan" in readme
