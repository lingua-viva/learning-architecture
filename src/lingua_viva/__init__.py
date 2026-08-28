"""Native Lingua Viva runtime module."""

__all__ = ["__version__"]

# Keep in sync with pyproject.toml [project] version. In the desktop bundle
# pyproject.toml is not shipped, so this is the engine-version fallback that
# drives the first-launch template reconcile (src/lingua_viva/reconcile.py
# engine_version()) — a stale value here means updates never reconcile.
__version__ = "1.0.7"
