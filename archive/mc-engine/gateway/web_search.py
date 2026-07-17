"""
Mission Canvas — Web Search (Multi-Backend)

Unified web search interface supporting multiple providers.
Falls back gracefully if a provider is unavailable.

Providers:
    - Perplexity (default, already in MC hub)
    - Exa (AI-native search, exa.ai)
    - Tavily (research-optimized, tavily.com)
    - Firecrawl (extract + crawl, firecrawl.dev)

Environment variables:
    MC_SEARCH_PROVIDER     — Default provider: perplexity|exa|tavily|firecrawl (default: perplexity)
    MC_EXA_API_KEY         — Exa API key
    MC_TAVILY_API_KEY      — Tavily API key
    MC_FIRECRAWL_API_KEY   — Firecrawl API key
    MC_PERPLEXITY_API_KEY  — Perplexity API key (also used by hub)

Usage:
    from lib.web_search import search, extract

    results = await search("HIPAA compliance requirements 2026")
    # returns: [{"title": ..., "url": ..., "snippet": ..., "score": ...}, ...]

    content = await extract("https://example.com/article")
    # returns: {"url": ..., "title": ..., "content": ..., "markdown": ...}
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.error import URLError

logger = logging.getLogger(__name__)


def _get_provider() -> str:
    return os.getenv("MC_SEARCH_PROVIDER", "perplexity").lower()


def _api_key(provider: str) -> str:
    keys = {
        "exa": "MC_EXA_API_KEY",
        "tavily": "MC_TAVILY_API_KEY",
        "firecrawl": "MC_FIRECRAWL_API_KEY",
        "perplexity": "MC_PERPLEXITY_API_KEY",
    }
    env_var = keys.get(provider, "")
    return os.getenv(env_var, "")


async def search(
    query: str,
    provider: Optional[str] = None,
    num_results: int = 5,
    context: str = "general",
    block_signals: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Search the web using the configured provider.

    GOVERNANCE: Query is sanitized before sending to any external provider.
    If sanitization blocks the query, returns empty results.

    Returns list of results with: title, url, snippet, score
    """
    # Governance gate: sanitize before any external call
    from sanitizer.app import sanitize as _sanitize
    san_result = _sanitize(query, context=context, block_signals=block_signals or [])
    if san_result["blocked"]:
        return [{"error": f"Query blocked by governance: {san_result['reason']}"}]
    sanitized_query = san_result["text"]

    prov = provider or _get_provider()
    key = _api_key(prov)

    if not key:
        logger.warning("[Search] No API key for %s, falling back", prov)
        # Try providers in order until one works
        for fallback in ["perplexity", "exa", "tavily", "firecrawl"]:
            key = _api_key(fallback)
            if key:
                prov = fallback
                break
        if not key:
            return [{"error": "No search API key configured"}]

    if prov == "exa":
        return await _search_exa(sanitized_query, key, num_results)
    elif prov == "tavily":
        return await _search_tavily(sanitized_query, key, num_results)
    elif prov == "perplexity":
        return await _search_perplexity(sanitized_query, key, num_results)
    elif prov == "firecrawl":
        return await _search_firecrawl(sanitized_query, key, num_results)
    else:
        return [{"error": f"Unknown provider: {prov}"}]


async def extract(url: str, provider: Optional[str] = None) -> Dict[str, Any]:
    """Extract content from a URL."""
    prov = provider or _get_provider()
    key = _api_key(prov)

    if prov == "firecrawl" and key:
        return await _extract_firecrawl(url, key)
    elif prov == "exa" and key:
        return await _extract_exa(url, key)
    else:
        # Basic fallback: fetch raw
        return _fetch_raw(url)


# ─── Provider implementations ────────────────────────────────────────────────

async def _search_exa(query: str, key: str, n: int) -> List[Dict[str, Any]]:
    """Exa search (exa.ai)"""
    import asyncio
    def _do():
        req = Request(
            "https://api.exa.ai/search",
            data=json.dumps({
                "query": query,
                "num_results": n,
                "use_autoprompt": True,
            }).encode(),
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        )
        resp = urlopen(req, timeout=15)
        data = json.loads(resp.read())
        return [
            {"title": r.get("title", ""), "url": r.get("url", ""), "snippet": r.get("text", "")[:300], "score": r.get("score", 0)}
            for r in data.get("results", [])
        ]
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _do)


async def _search_tavily(query: str, key: str, n: int) -> List[Dict[str, Any]]:
    """Tavily search (tavily.com)"""
    import asyncio
    def _do():
        req = Request(
            "https://api.tavily.com/search",
            data=json.dumps({
                "api_key": key,
                "query": query,
                "max_results": n,
                "include_answer": True,
            }).encode(),
            headers={"Content-Type": "application/json"},
        )
        resp = urlopen(req, timeout=15)
        data = json.loads(resp.read())
        return [
            {"title": r.get("title", ""), "url": r.get("url", ""), "snippet": r.get("content", "")[:300], "score": r.get("score", 0)}
            for r in data.get("results", [])
        ]
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _do)


async def _search_perplexity(query: str, key: str, n: int) -> List[Dict[str, Any]]:
    """Perplexity search via chat completions API."""
    import asyncio
    def _do():
        req = Request(
            "https://api.perplexity.ai/chat/completions",
            data=json.dumps({
                "model": "sonar",
                "messages": [{"role": "user", "content": query}],
            }).encode(),
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        )
        resp = urlopen(req, timeout=20)
        data = json.loads(resp.read())
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        citations = data.get("citations", [])
        results = [{"title": query, "url": "", "snippet": content[:500], "score": 1.0}]
        for i, cite in enumerate(citations[:n]):
            results.append({"title": f"Source {i+1}", "url": cite, "snippet": "", "score": 0.8})
        return results
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _do)


async def _search_firecrawl(query: str, key: str, n: int) -> List[Dict[str, Any]]:
    """Firecrawl search (firecrawl.dev)"""
    import asyncio
    def _do():
        req = Request(
            "https://api.firecrawl.dev/v1/search",
            data=json.dumps({"query": query, "limit": n}).encode(),
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        )
        resp = urlopen(req, timeout=15)
        data = json.loads(resp.read())
        return [
            {"title": r.get("title", ""), "url": r.get("url", ""), "snippet": r.get("description", "")[:300], "score": r.get("score", 0)}
            for r in data.get("data", [])
        ]
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _do)


async def _extract_firecrawl(url: str, key: str) -> Dict[str, Any]:
    import asyncio
    def _do():
        req = Request(
            "https://api.firecrawl.dev/v1/scrape",
            data=json.dumps({"url": url, "formats": ["markdown"]}).encode(),
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        )
        resp = urlopen(req, timeout=20)
        data = json.loads(resp.read()).get("data", {})
        return {"url": url, "title": data.get("metadata", {}).get("title", ""), "content": data.get("markdown", ""), "markdown": data.get("markdown", "")}
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _do)


async def _extract_exa(url: str, key: str) -> Dict[str, Any]:
    import asyncio
    def _do():
        req = Request(
            "https://api.exa.ai/contents",
            data=json.dumps({"urls": [url], "text": True}).encode(),
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        )
        resp = urlopen(req, timeout=15)
        data = json.loads(resp.read())
        results = data.get("results", [{}])
        r = results[0] if results else {}
        return {"url": url, "title": r.get("title", ""), "content": r.get("text", ""), "markdown": r.get("text", "")}
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _do)


def _fetch_raw(url: str) -> Dict[str, Any]:
    """Basic URL fetch fallback."""
    try:
        req = Request(url, headers={"User-Agent": "MissionCanvas/1.0"})
        resp = urlopen(req, timeout=10)
        content = resp.read().decode(errors="replace")[:50000]
        return {"url": url, "title": "", "content": content, "markdown": content}
    except Exception as e:
        return {"url": url, "error": str(e)}
