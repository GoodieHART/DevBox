"""Unit tests for the `dove` download helper.

Network-free by design: only URL classification, pointer extraction, filename
handling, and backend routing are exercised. The actual downloads are covered
by the structural image tests plus manual runs on a live box.
"""

import ast
import pathlib

import pytest

from integrations import dove


@pytest.mark.parametrize(
    "url,kind",
    [
        ("https://drive.google.com/file/d/1abcDEF/view?usp=sharing", dove.KIND_DRIVE),
        ("https://docs.google.com/document/d/1abc/edit", dove.KIND_DRIVE),
        ("https://mega.nz/file/abc123#key456", dove.KIND_MEGA),
        ("https://mega.io/file/abc", dove.KIND_MEGA),
        ("https://t.me/c/123456/789", dove.KIND_TELEGRAM),
        ("https://telegram.me/somechannel/1", dove.KIND_TELEGRAM),
        ("https://www.terabox.com/s/abc", dove.KIND_TERABOX),
        ("https://www.1024tera.com/s/abc", dove.KIND_TERABOX),
        ("https://example.com/files/archive.zip", dove.KIND_DIRECT),
        ("https://drive.google.com.evil.com/x", dove.KIND_DIRECT),
        ("https://notmega.nz.example/x", dove.KIND_DIRECT),
    ],
)
def test_classify(url, kind):
    assert dove.classify(url) == kind


def test_classify_handles_garbage():
    assert dove.classify("not a url") == dove.KIND_DIRECT
    assert dove.classify("") == dove.KIND_DIRECT


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://drive.google.com/drive/folders/1abc", True),
        ("https://drive.google.com/drive/u/0/folders/1abc", True),
        ("https://drive.google.com/file/d/1abc/view", False),
    ],
)
def test_is_drive_folder(url, expected):
    assert dove.is_drive_folder(url) is expected


def test_pointer_bare_url():
    assert dove.extract_pointer("  https://example.com/file.zip\n") == (
        "https://example.com/file.zip"
    )


def test_pointer_bare_url_absolutised():
    assert dove.extract_pointer("/files/a.zip", "https://example.com/landing") == (
        "https://example.com/files/a.zip"
    )


@pytest.mark.parametrize(
    "body,expected",
    [
        ('<html><head><meta http-equiv="refresh" content="0; url=https://cdn.example.com/a.zip"></head></html>', "https://cdn.example.com/a.zip"),
        ('<meta content="1;URL=\'https://cdn.example.com/b.zip\'" http-equiv="Refresh">', "https://cdn.example.com/b.zip"),
        ("<script>window.location.href = 'https://cdn.example.com/c.zip';</script>", "https://cdn.example.com/c.zip"),
        ("<script>location.replace('https://cdn.example.com/d.zip')</script>", "https://cdn.example.com/d.zip"),
    ],
    ids=["meta_refresh", "meta_refresh_attribute_order", "js_assignment", "js_replace"],
)
def test_pointer_redirect(body, expected):
    assert dove.extract_pointer(body) == expected


@pytest.mark.parametrize(
    "body",
    [
        "",
        "   ",
        "<html><body><h1>Nothing to see here</h1></body></html>",
        "<script>javascript:void(0)</script>",
        "just some prose mentioning a link",
    ],
)
def test_pointer_absent(body):
    assert dove.extract_pointer(body) is None


def test_pointer_ignores_javascript_scheme():
    html = "<script>window.location = 'javascript:alert(1)'</script>"
    assert dove.extract_pointer(html) is None


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("../../etc/passwd", "passwd"),
        ("..\\..\\windows\\system32", "system32"),
        ("..", "download"),
        (".", "download"),
        ("", "download"),
        ("  spaced.zip  ", "spaced.zip"),
        ("a\x00b\x1fc.zip", "abc.zip"),
        ("normal.tar.gz", "normal.tar.gz"),
    ],
)
def test_safe_name(raw, expected):
    assert dove.safe_name(raw) == expected


@pytest.mark.parametrize(
    "header,expected",
    [
        ('attachment; filename="report final.pdf"', "report final.pdf"),
        ("attachment; filename=report.pdf", "report.pdf"),
        ("attachment; filename*=UTF-8''na%C3%AFve.zip", "naïve.zip"),
        ("attachment; filename*=iso-8859-1''caf%E9.zip", "café.zip"),
        ("inline", None),
        (None, None),
    ],
)
def test_filename_from_content_disposition(header, expected):
    assert dove.filename_from_content_disposition(header) == expected


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://example.com/files/a.zip", "a.zip"),
        ("https://example.com/files/", "files"),
        ("https://example.com/a%20b.zip", "a b.zip"),
        ("https://example.com/", None),
    ],
)
def test_filename_from_url(url, expected):
    assert dove.filename_from_url(url) == expected


def test_dispatch_routes_to_the_matching_backend(monkeypatch):
    seen = []

    def record(name):
        def backend(*_args, **_kwargs):
            seen.append(name)
            return name

        return backend

    for kind in (dove.KIND_DRIVE, dove.KIND_MEGA, dove.KIND_TELEGRAM, dove.KIND_TERABOX):
        monkeypatch.setitem(dove.BACKENDS, kind, record(kind))
    monkeypatch.setattr(dove, "download_direct", record("direct"))

    dove.dispatch("https://drive.google.com/file/d/1/view", ".", None, True)
    dove.dispatch("https://mega.nz/file/a#b", ".", None, True)
    dove.dispatch("https://t.me/c/1/2", ".", None, True)
    dove.dispatch("https://terabox.com/s/x", ".", None, True)
    dove.dispatch("https://example.com/a.zip", ".", None, True)

    assert seen == ["drive", "mega", "telegram", "terabox", "direct"]


def test_cli_rejects_non_http_url(capsys):
    assert dove.main(["ftp://example.com/x"]) == 2
    assert "not an http(s) URL" in capsys.readouterr().err


def test_cli_flags_are_wired():
    parser = dove.build_parser()
    args = parser.parse_args(
        ["https://example.com/a.zip", "-o", "b.zip", "-d", "/tmp", "-q", "--probe", "--no-pointer"]
    )
    assert args.url == "https://example.com/a.zip"
    assert args.output == "b.zip"
    assert args.dir == "/tmp"
    assert args.quiet is True
    assert args.probe is True
    assert args.no_pointer is True


def test_human_sizes():
    assert dove._human(0) == "0 B"
    assert dove._human(1023) == "1023 B"
    assert dove._human(1024) == "1.0 KiB"
    assert dove._human(5 * 1024 * 1024) == "5.0 MiB"


ROOT = pathlib.Path(__file__).resolve().parent.parent
IMAGES = ROOT / "devbox_core" / "images.py"
DOVE_SOURCE = ROOT / "integrations" / "dove.py"
BASE_BUILDERS = ("create_base_devbox_image", "create_base_minimal_image")


def _images_tree() -> ast.Module:
    return ast.parse(IMAGES.read_text(encoding="utf-8"))


def _assignments() -> dict[str, str]:
    source = IMAGES.read_text(encoding="utf-8")
    return {
        node.targets[0].id: ast.get_source_segment(source, node) or ""
        for node in _images_tree().body
        if isinstance(node, ast.Assign)
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id.endswith("_image")
    }


def _functions() -> dict[str, str]:
    source = IMAGES.read_text(encoding="utf-8")
    return {
        node.name: ast.get_source_segment(source, node) or ""
        for node in _images_tree().body
        if isinstance(node, ast.FunctionDef)
    }


def test_both_base_builders_install_dove():
    functions = _functions()
    for builder in BASE_BUILDERS:
        assert "/usr/local/bin/dove" in functions[builder], builder


def test_cuda_installs_dove_despite_bypassing_the_bases():
    assert "/usr/local/bin/dove" in _assignments()["cuda_devbox_image"]


def test_every_dove_host_installs_megatools():
    """dove's Mega backend shells out to `megadl`, so megatools must exist."""
    functions = _functions()
    for builder in BASE_BUILDERS:
        assert "DOWNLOAD_APT_PACKAGES" in functions[builder], builder
    assert "DOWNLOAD_APT_PACKAGES" in _assignments()["cuda_devbox_image"]


def test_every_image_reaches_dove():
    """Each image either wires dove itself or inherits a base that does."""
    functions = _functions()
    inherited = any("/usr/local/bin/dove" in functions[b] for b in BASE_BUILDERS)

    for name, segment in _assignments().items():
        direct = "/usr/local/bin/dove" in segment
        derives = any(f"{builder}(" in segment for builder in BASE_BUILDERS)
        assert direct or (inherited and derives), f"{name} has no path to dove"


def test_dove_is_installed_executable():
    source = IMAGES.read_text(encoding="utf-8")
    assert '"/usr/local/bin/dove"' in source
    assert "chmod 755 /usr/local/bin/dove" in source


BUILD_STEPS = (".run_commands(", ".pip_install(", ".apt_install(")
LOCAL_STEPS = (".add_local_file(", ".add_local_python_source(", ".add_local_dir(")


def _local_calls(segment: str) -> list[tuple[int, bool]]:
    """Every add_local_* call as (offset, is_copy) pairs."""
    found: list[tuple[int, bool]] = []
    for step in LOCAL_STEPS:
        start = 0
        while True:
            index = segment.find(step, start)
            if index == -1:
                break
            found.append((index, "copy=True" in segment[index:index + 300]))
            start = index + 1
    return sorted(found)


def _assert_local_steps_last(segment: str, label: str) -> None:
    for index, is_copy in _local_calls(segment):
        if is_copy:
            continue  # copy=True bakes the file, so later build steps are legal
        tail = segment[index:]
        for step in BUILD_STEPS:
            assert step not in tail, (
                f"{label}: {step} appears after a mount-mode add_local_*. Modal "
                "refuses to build that; either move add_local_* last or use copy=True."
            )


def test_no_build_step_follows_a_mounted_local_file():
    """Regression guard for the Modal 'build step after add_local_*' error."""
    for name, segment in _functions().items():
        _assert_local_steps_last(segment, name)
    for name, segment in _assignments().items():
        _assert_local_steps_last(segment, name)


def test_base_builders_copy_dove_because_callers_add_build_steps():
    """Base images are composed by callers that chain apt/pip/run_commands on top."""
    for builder in BASE_BUILDERS:
        segment = _functions()[builder]
        assert "copy=True" in segment, builder
        assert '"/usr/local/bin/dove"' in segment, builder


def test_dove_is_self_contained():
    """It is copied to /usr/local/bin, so it cannot import first-party modules."""
    source = DOVE_SOURCE.read_text(encoding="utf-8")
    assert source.startswith("#!/usr/bin/env python3")

    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names = [alias.name.split(".")[0] for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [(node.module or "").split(".")[0]]
        else:
            continue
        for name in names:
            assert name not in {"devbox_core", "runtime", "ui", "integrations"}, name
