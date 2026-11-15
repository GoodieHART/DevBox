"""Tests for the zsh setup: packages, baked rc, and login shell."""

import ast
import pathlib

from devbox_core import config
from runtime import persistence_utils as persistence

ROOT = pathlib.Path(__file__).resolve().parent.parent
IMAGES = ROOT / "devbox_core" / "images.py"
ZSHRC = ROOT / "integrations" / "zshrc"
BASE_BUILDERS = ("create_base_devbox_image", "create_base_minimal_image")


def source(path):
    return path.read_text(encoding="utf-8")


def _tree():
    return ast.parse(source(IMAGES))


def _assignments():
    text = source(IMAGES)
    return {
        node.targets[0].id: ast.get_source_segment(text, node) or ""
        for node in _tree().body
        if isinstance(node, ast.Assign)
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id.endswith("_image")
    }


def _functions():
    text = source(IMAGES)
    return {
        node.name: ast.get_source_segment(text, node) or ""
        for node in _tree().body
        if isinstance(node, ast.FunctionDef)
    }


def test_core_packages_install_zsh_and_the_apt_plugins():
    for package in ("zsh", "zsh-autosuggestions", "zsh-syntax-highlighting"):
        assert package in config.CORE_DEV_PACKAGES, package


def test_completions_are_pinned_because_debian_lacks_the_package():
    assert config.ZSH_COMPLETIONS_VERSION
    functions = _functions()
    for builder in BASE_BUILDERS:
        segment = functions[builder]
        assert "zsh-completions" in segment, builder
        assert "ZSH_COMPLETIONS_VERSION" in segment, builder
    cuda = _assignments()["cuda_devbox_image"]
    assert "zsh-completions" in cuda
    assert "ZSH_COMPLETIONS_VERSION" in cuda


def _desktop_layer():
    text = source(IMAGES)
    for node in _tree().body:
        if (
            isinstance(node, ast.Assign)
            and getattr(node.targets[0], "id", None) == "_rdp_desktop_layer"
        ):
            return ast.get_source_segment(text, node) or ""
    raise AssertionError("_rdp_desktop_layer assignment missing")


def test_every_image_reaches_the_zshrc():
    # Sandboxes get no mounts, so the rc has to be copied in. The bases bake
    # it; the CUDA image bypasses them and carries its own copy.
    functions = _functions()
    assert any('"/etc/devbox/zshrc"' in functions[b] for b in BASE_BUILDERS)
    assert any(f"{builder}(" in _desktop_layer() for builder in BASE_BUILDERS)

    for name, segment in _assignments().items():
        direct = '"/etc/devbox/zshrc"' in segment
        derives = any(
            (f"{builder}(" if builder in BASE_BUILDERS else builder) in segment
            for builder in (*BASE_BUILDERS, "_rdp_desktop_layer")
        )
        assert direct or derives, f"{name} has no zshrc"
        if direct:
            assert "copy=True" in segment, f"{name} mounts the zshrc instead of baking it"
            assert segment.index('"/etc/devbox/zshrc"') < segment.index(
                ".add_local_python_source("
            ), f"{name} bakes the zshrc after a mount-mode add"


def test_base_builders_hook_the_rc_and_switch_the_login_shell():
    functions = _functions()
    for builder in BASE_BUILDERS:
        segment = functions[builder]
        assert "/etc/devbox/zshrc" in segment, builder
        assert "copy=True" in segment, builder
        assert ">> /etc/zsh/zshrc" in segment, builder
        assert "chsh -s /usr/bin/zsh root" in segment, builder


def test_cuda_image_hooks_the_rc_despite_bypassing_the_bases():
    segment = _assignments()["cuda_devbox_image"]
    assert "/etc/devbox/zshrc" in segment
    assert ">> /etc/zsh/zshrc" in segment
    assert "chsh -s /usr/bin/zsh root" in segment


def test_zshrc_loads_plugins_with_highlighting_last():
    text = source(ZSHRC)
    autosuggestions = text.index("zsh-autosuggestions.zsh")
    highlighting = text.index("zsh-syntax-highlighting.zsh")
    assert autosuggestions < highlighting


def test_zshrc_keeps_bash_parity_and_completions():
    text = source(ZSHRC)
    assert "zsh-completions" in text
    assert "compinit" in text
    assert "menu select" in text
    assert "starship init zsh" in text
    assert "/etc/profile.d/devbox-forensics.sh" in text
    assert "[[ -o login ]]" in text
    assert "/etc/devbox-banner" in text


def test_zsh_history_is_persisted():
    assert ".zsh_history" in persistence.SSH_PERSISTENCE_ITEMS
    assert ".zsh_history" in persistence.RDP_PERSISTENCE_ITEMS
