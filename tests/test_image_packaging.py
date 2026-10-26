"""Structural tests for what each DevBox image ships into its container.

Modal imports the app module inside the container before any function runs, so
every first-party module reachable from `devbox.py` has to be packaged into the
image by `add_local_python_source`. A module that is imported at module level but
not packaged fails at container start with ModuleNotFoundError, before the
function body is ever reached.

`rdp_devbox_image` shipped without `ui.quotes_loader` while
`runtime/shared_runtime.py` imports it at module level, which broke every RDP
launch. These tests inspect the source tree instead of importing Modal, matching
tests/test_gpu_options.py.
"""

import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
IMAGES = ROOT / "devbox_core" / "images.py"

FIRST_PARTY_ROOTS = {"devbox_core", "runtime", "ui", "integrations"}


def _tree() -> ast.Module:
    return ast.parse(IMAGES.read_text(encoding="utf-8"))


def _image_assignments() -> dict[str, ast.Assign]:
    """Every module-level `<name>_image = ...` assignment."""
    return {
        node.targets[0].id: node
        for node in _tree().body
        if isinstance(node, ast.Assign)
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id.endswith("_image")
    }


def _chained_strings(node: ast.AST, method: str) -> list[str]:
    """String literals passed to every `<...>.<method>(...)` call in a chain."""
    found = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute):
            if sub.func.attr == method:
                found += [
                    arg.value for arg in sub.args if isinstance(arg, ast.Constant)
                ]
    return found


def _packaged_modules() -> dict[str, list[str]]:
    return {
        name: _chained_strings(node.value, "add_local_python_source")
        for name, node in _image_assignments().items()
    }


def _mounted_files() -> dict[str, list[str]]:
    return {
        name: _chained_strings(node.value, "add_local_file")
        for name, node in _image_assignments().items()
    }


def _imported_modules(module_name: str) -> set[str]:
    """First-party modules imported at module scope by `module_name`."""
    path = ROOT.joinpath(*module_name.split(".")).with_suffix(".py")
    if not path.exists():
        path = ROOT.joinpath(*module_name.split(".")) / "__init__.py"
    assert path.exists(), f"{module_name} is packaged but has no source file"

    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported = set()
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] in FIRST_PARTY_ROOTS:
                imported.add(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in FIRST_PARTY_ROOTS:
                    imported.add(alias.name)
    return imported


def test_every_image_is_discovered():
    assert set(_packaged_modules()) == {
        "standard_devbox_image",
        "cuda_devbox_image",
        "doc_processing_image",
        "assisted_coding_image",
        "forensic_analysis_image",
        "llm_playroom_image",
        "llamacpp_cpu_image",
        "rdp_devbox_image",
    }


def test_packaged_modules_import_only_packaged_modules():
    """No image may ship a module whose module-level imports it leaves behind."""
    for image, modules in _packaged_modules().items():
        packaged = set(modules)
        for module in modules:
            for dependency in _imported_modules(module):
                assert dependency in packaged, (
                    f"{image} packages {module!r}, which imports {dependency!r} "
                    f"at module level, but never packages {dependency!r}. "
                    "The container will fail with ModuleNotFoundError."
                )


def test_every_image_packages_ui_quotes_loader():
    for image, modules in _packaged_modules().items():
        assert "ui.quotes_loader" in modules, f"{image} dropped ui.quotes_loader"


def test_every_image_mounts_the_quote_catalogue():
    for image, files in _mounted_files().items():
        assert any("quotes.json" in path for path in files), (
            f"{image} does not mount ui/quotes.json; the launcher would fall back "
            "to the three hardcoded quotes"
        )


def test_rdp_image_matches_the_standard_image_packaging():
    """The RDP image is a standard image plus desktop packages, nothing less."""
    packaged = _packaged_modules()
    standard = set(packaged["standard_devbox_image"])
    rdp = set(packaged["rdp_devbox_image"])
    assert standard <= rdp, f"rdp image is missing: {sorted(standard - rdp)}"
