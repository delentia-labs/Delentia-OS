"""
SignedAI Core Router — compatibility shim
Re-exports from rct_platform/services/signedai/legacy/core/router.py

Uses importlib.util.spec_from_file_location to avoid name-clash with
the workspace-level `core/` package that lives on sys.path.
"""
import sys
import os
import types
import importlib.util as _iu

_HERE = os.path.dirname(os.path.abspath(__file__))
_LEGACY_CORE_PATH = os.path.normpath(
    os.path.join(_HERE, '..', '..', 'rct_platform', 'services', 'signedai', 'legacy', 'core')
)
_LEGACY_ROUTER = os.path.join(_LEGACY_CORE_PATH, 'router.py')

# Ensure the legacy models module is already loaded (models.py shim does this)
from signedai.core import models as _models_shim  # noqa: E402, F401
_models_legacy_mod = sys.modules.get("_signedai_legacy_core_models")

# Create/reuse a package alias for the legacy core package
_PKG = "_signedai_legacy_core"
if _PKG not in sys.modules:
    _pkg = types.ModuleType(_PKG)
    _pkg.__path__ = [_LEGACY_CORE_PATH]
    _pkg.__package__ = _PKG
    sys.modules[_PKG] = _pkg

if _models_legacy_mod is not None:
    sys.modules[f"{_PKG}.models"] = _models_legacy_mod
    sys.modules[_PKG].models = _models_legacy_mod  # type: ignore[attr-defined]

# Load the router module under the alias package so `from .models import ...` resolves
_router_mod_name = f"{_PKG}.router"
if _router_mod_name not in sys.modules:
    _spec = _iu.spec_from_file_location(_router_mod_name, _LEGACY_ROUTER)
    _router_mod = _iu.module_from_spec(_spec)
    _router_mod.__package__ = _PKG
    sys.modules[_router_mod_name] = _router_mod
    _spec.loader.exec_module(_router_mod)
else:
    _router_mod = sys.modules[_router_mod_name]

TierRouter = _router_mod.TierRouter

__all__ = ["TierRouter"]
