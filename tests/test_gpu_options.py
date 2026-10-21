"""Structural tests for the GPU launcher options.

The GPU launchers are registered with @app.function(...), and importing
devbox.py performs Volume/Secret lookups at import time. These tests inspect
the source tree instead, matching the approach in tests/test_opencode.py.
"""

import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent

GPU_LAUNCHERS = {
    "launch_devbox_t4": "t4",
    "launch_devbox_l4": "l4",
    "launch_devbox_a10g": "a10g",
    "launch_devbox_l40s": "L40S",
    "launch_rdp_devbox_t4": "t4",
    "launch_rdp_devbox_l4": "l4",
    "launch_rdp_devbox_a10g": "a10g",
    "launch_rdp_devbox_l40s": "L40S",
}


def _source(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def _tree(name: str) -> ast.Module:
    return ast.parse(_source(name))


def _functions(name: str) -> dict[str, ast.FunctionDef]:
    return {
        node.name: node
        for node in _tree(name).body
        if isinstance(node, ast.FunctionDef)
    }


def _decorator_gpu(fn: ast.FunctionDef):
    for decorator in fn.decorator_list:
        for node in ast.walk(decorator):
            if isinstance(node, ast.Call):
                for keyword in node.keywords:
                    if keyword.arg == "gpu" and isinstance(keyword.value, ast.Constant):
                        return keyword.value.value
    return None


def test_every_gpu_launcher_exists():
    functions = _functions("devbox.py")
    for name in GPU_LAUNCHERS:
        assert name in functions, f"missing launcher: {name}"


def test_gpu_launchers_request_the_right_gpu_type():
    functions = _functions("devbox.py")
    for name, gpu in GPU_LAUNCHERS.items():
        assert _decorator_gpu(functions[name]) == gpu, f"{name} should request gpu={gpu}"


def test_gpu_launchers_are_skipped_in_cpu_only_mode():
    functions = _functions("devbox.py")
    for name in GPU_LAUNCHERS:
        assert any(
            isinstance(decorator, ast.Call)
            and getattr(decorator.func, "id", None) == "_unless_cpu_only"
            for decorator in functions[name].decorator_list
        ), f"{name} must be wrapped in _unless_cpu_only"


def test_menu_offers_four_gpu_choices():
    menu = _source("ui/launcher_menu.py")
    assert '"4": ("L40S", launch_devbox_l40s)' in menu
    assert '"4": ("L40S", launch_rdp_devbox_l40s)' in menu
    assert menu.count("L40S") >= 4


def test_gpu_picker_prompts_for_four_options():
    picker = _source("ui/gpu_picker.py")
    assert "Choose GPU (1-4)" in picker
    assert picker.count("L40S GPU") == 2


def test_banner_knows_the_l40s_box():
    assert '"cuda_devbox_l40s"' in _source("runtime/shared_runtime.py")


def test_readme_gpu_table_lists_l40s():
    readme = _source("README.md")
    assert "| **L40S** |" in readme
    assert "48 GB" in readme
    assert "(T4, L4, A10G, L40S)" in readme
