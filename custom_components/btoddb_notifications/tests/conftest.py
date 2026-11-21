"""
Import shim so the pure modules load standalone, bypassing the package ``__init__``.

``sending`` and ``http_request`` import nothing from Home Assistant and nothing from
the package ``__init__`` (which does). ``load_module`` loads them by file path, so
their tests exercise them in isolation. Home Assistant must still be installed
(``requirements.txt``): pytest's importlib mode imports the parent package for this
conftest, and ``test_init.py`` imports the integration package on purpose.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

# With --import-mode=importlib, pytest doesn't add the conftest directory to
# sys.path, so "from conftest import load_module" in test files fails unless
# we're cd'd into the tests dir. Insert it explicitly so pytest can be run
# from the repo root.
sys.path.insert(0, str(Path(__file__).parent))
# Repo root, so ``custom_components.btoddb_notifications`` imports explicitly (as
# test_init.py does) without relying on pytest's rootdir handling.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from types import ModuleType


def load_module(name: str) -> ModuleType:
    """Load ``<package>/<name>.py`` directly, bypassing the package __init__."""
    path = Path(__file__).resolve().parent.parent / f"{name}.py"
    mod_name = f"btoddb_notifications_{name}"
    spec = importlib.util.spec_from_file_location(mod_name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # Register before exec: a frozen dataclass with ``from __future__ import
    # annotations`` resolves its own module out of sys.modules at class-creation time
    # (Python 3.14), which fails if the module isn't registered yet.
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module
