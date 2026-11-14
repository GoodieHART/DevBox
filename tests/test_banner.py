"""Tests for the login banner shown by every box, VM included."""

from runtime import shared_runtime as shared


def test_banner_names_the_box_and_carries_the_quote(monkeypatch):
    monkeypatch.setattr(
        shared,
        "get_random_quote",
        lambda: {"text": "Code wins.", "author": "Someone"},
    )

    banner = shared.format_banner("standard_devbox")

    assert "Standard DevBox" in banner
    assert "Persistent: /data" in banner
    assert "Code wins." in banner
    assert "- Someone" in banner


def test_banner_accepts_extra_rows(monkeypatch):
    monkeypatch.setattr(
        shared, "get_random_quote", lambda: {"text": "x", "author": "y"}
    )

    banner = shared.format_banner(
        "forensic_analysis", ("OpenCode web on :4096", "RDP desktop on :3389")
    )
    rows = banner.splitlines()

    assert "Forensics Analysis Box" in banner
    assert any("OpenCode web on :4096" in row for row in rows)
    assert rows[0].startswith("╔")
    assert any(row.startswith("╚") for row in rows)


def test_banner_still_renders_without_a_quote(monkeypatch):
    def unavailable():
        raise OSError("no catalogue")

    monkeypatch.setattr(shared, "get_random_quote", unavailable)

    banner = shared.format_banner("standard_devbox")

    assert "Standard DevBox" in banner
    assert banner.rstrip().endswith("╝")
