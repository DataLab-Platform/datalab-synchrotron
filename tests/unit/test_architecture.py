"""Dependency rules for host-independent plugin layers."""

from __future__ import annotations

import ast
from pathlib import Path

PACKAGE_ROOT = Path(__file__).parents[2] / "src" / "datalab_synchrotron"
PACKAGE_NAME = "datalab_synchrotron"
#: The core must also run in DataLab-Web: no host, no compiled reader library
FORBIDDEN_IN_CORE = (
    "PyQt5",
    "PyQt6",
    "PySide6",
    "datalab",
    "qtpy",
    "js",
    "pyodide",
    "silx",
    "fabio",
    "tango",
    "sigimax",
    f"{PACKAGE_NAME}.adapters",
    f"{PACKAGE_NAME}.formats",
    f"{PACKAGE_NAME}.mappings",
)


def _module_imports(filename: Path) -> set[str]:
    """Return absolute names of the modules imported by one source file."""
    tree = ast.parse(filename.read_text(encoding="utf-8"), filename=str(filename))
    relative_parts = filename.relative_to(PACKAGE_ROOT).with_suffix("").parts
    package_parts = (PACKAGE_NAME, *relative_parts[:-1])
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                imports.add(node.module or "")
                continue
            base_parts = package_parts[: len(package_parts) - node.level + 1]
            if node.module is not None:
                imports.add(".".join((*base_parts, *node.module.split("."))))
            else:
                imports.update(
                    ".".join((*base_parts, *alias.name.split(".")))
                    for alias in node.names
                )
    return imports


def test_package_root_does_not_import_host_adapters() -> None:
    """Importing package identity must not load a host adapter."""
    imports = _module_imports(PACKAGE_ROOT / "__init__.py")
    assert not any(name.startswith(f"{PACKAGE_NAME}.") for name in imports)


def test_core_is_portable() -> None:
    """The core imports neither a host nor a compiled reader library."""
    violations = [
        f"{filename.relative_to(PACKAGE_ROOT)} imports {name}"
        for filename in sorted((PACKAGE_ROOT / "core").rglob("*.py"))
        for name in sorted(_module_imports(filename))
        if any(name == p or name.startswith(f"{p}.") for p in FORBIDDEN_IN_CORE)
    ]
    assert not violations, "\n".join(violations)


def test_workflow_is_headless() -> None:
    """Recipes use DataLab's headless contracts only, not its user interface."""
    allowed = ("datalab.plugins.recipes", "datalab.plugins.examples")
    forbidden = (*FORBIDDEN_IN_CORE, f"{PACKAGE_NAME}.mappings")
    violations = [
        f"{filename.relative_to(PACKAGE_ROOT)} imports {name}"
        for filename in sorted((PACKAGE_ROOT / "workflow").rglob("*.py"))
        for name in sorted(_module_imports(filename))
        if name not in allowed
        and any(name == p or name.startswith(f"{p}.") for p in forbidden)
    ]
    assert not violations, "\n".join(violations)
