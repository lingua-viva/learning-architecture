"""Feature router registry — src/web.py imports and includes each module's
``router`` (a fastapi.APIRouter) at startup.

Contract for modules listed here:
- expose module-level ``router = APIRouter(prefix="/api/...")``
- NEVER import src.web (circular import)
- one module per feature area; add your module name below on its own line
"""

ROUTER_MODULES: list[str] = [
    "sources",
    "safeguarding",
    "artifacts",
    "document_import",
]
