"""Feature router registry — src/web.py imports and includes each module's
``router`` (a fastapi.APIRouter) at startup.

Contract for modules listed here:
- expose module-level ``router`` (a fastapi.APIRouter). Prefix is optional:
  small feature areas use ``APIRouter(prefix="/api")``; large moved-from-web.py
  areas (students) use no prefix so every decorator keeps its full literal
  path and stays greppable.
- NEVER import src.web (circular import) — shared web-surface definitions
  live in src.lingua_viva.web_helpers
- one module per feature area; add your module name below on its own line
"""

ROUTER_MODULES: list[str] = [
    "sources",
    "safeguarding",
    "artifacts",
    "assessment",
    "document_import",
    "students",
    "admin_query",
]
