"""
Redis Hot Memory Adapter

Redis stores the hot state: recent sessions, active paths, current agent state.
TTL: 24 hours for session state, 30 days for path records.

Why Redis and not SQLite or Turso:
- Sub-millisecond reads for active session state
- TTL-based expiry for hot/cold boundary
- Pub/sub for multi-agent coordination
- Sorted sets for path record ranking

Redis is the hot layer. NDJSON is the cold layer. Together they form
the memory store that avoids semantic interference entirely.

Falls back gracefully to in-memory dict when Redis is not available.
"""

from __future__ import annotations

import json
import time
from typing import Optional

from .schema import PathRecord, SessionRecord


# TTL constants
SESSION_TTL = 86400        # 24 hours
PATH_RECORD_TTL = 2592000  # 30 days
AGENT_STATE_TTL = 3600     # 1 hour


class RedisAdapter:
    """
    Hot memory backed by Redis. Falls back to in-memory dict.
    """

    def __init__(self, redis_url: str = "redis://localhost:6379", db: int = 0):
        self._redis = None
        self._fallback: dict[str, dict] = {}
        self._using_fallback = False

        try:
            import redis
            self._redis = redis.from_url(redis_url, db=db, decode_responses=True)
            self._redis.ping()
        except Exception:
            self._using_fallback = True

    @property
    def is_connected(self) -> bool:
        if self._using_fallback:
            return False
        try:
            self._redis.ping()
            return True
        except Exception:
            return False

    # --- Session State ---

    def set_session(self, session: SessionRecord) -> None:
        key = f"mc:session:{session.session_id}"
        data = json.dumps(session.to_dict())
        if self._using_fallback:
            self._fallback[key] = {"data": data, "expires": time.time() + SESSION_TTL}
        else:
            self._redis.set(key, data, ex=SESSION_TTL)

    def get_session(self, session_id: str) -> Optional[SessionRecord]:
        key = f"mc:session:{session_id}"
        if self._using_fallback:
            entry = self._fallback.get(key)
            if entry and entry["expires"] > time.time():
                return SessionRecord.from_dict(json.loads(entry["data"]))
            return None
        data = self._redis.get(key)
        if data:
            return SessionRecord.from_dict(json.loads(data))
        return None

    # --- Path Records (hot) ---

    def store_path(self, record: PathRecord) -> None:
        """Store a path record in hot memory with TTL."""
        key = f"mc:path:{record.session_id}:{record.query_hash}"
        data = json.dumps(record.to_dict())
        if self._using_fallback:
            self._fallback[key] = {"data": data, "expires": time.time() + PATH_RECORD_TTL}
            # Also add to the sorted set index
            idx_key = f"mc:paths_by_node:{record.entry_node}"
            if idx_key not in self._fallback:
                self._fallback[idx_key] = {"members": []}
            self._fallback[idx_key]["members"].append({
                "key": key,
                "score": record.timestamp,
            })
        else:
            self._redis.set(key, data, ex=PATH_RECORD_TTL)
            # Index by entry node for fast lookup
            idx_key = f"mc:paths_by_node:{record.entry_node}"
            self._redis.zadd(idx_key, {key: record.timestamp})
            self._redis.expire(idx_key, PATH_RECORD_TTL)

    def find_recent_paths(
        self,
        entry_node: str,
        limit: int = 5,
    ) -> list[PathRecord]:
        """Find recent paths by entry node from hot memory."""
        idx_key = f"mc:paths_by_node:{entry_node}"
        if self._using_fallback:
            idx = self._fallback.get(idx_key, {}).get("members", [])
            idx.sort(key=lambda x: x["score"], reverse=True)
            results = []
            for member in idx[:limit]:
                entry = self._fallback.get(member["key"])
                if entry and entry["expires"] > time.time():
                    results.append(PathRecord.from_dict(json.loads(entry["data"])))
            return results

        # Get most recent keys from sorted set
        keys = self._redis.zrevrange(idx_key, 0, limit - 1)
        results = []
        for key in keys:
            data = self._redis.get(key)
            if data:
                results.append(PathRecord.from_dict(json.loads(data)))
        return results

    # --- Agent State ---

    def set_agent_state(self, agent_id: str, state: dict) -> None:
        key = f"mc:agent:{agent_id}"
        data = json.dumps(state)
        if self._using_fallback:
            self._fallback[key] = {"data": data, "expires": time.time() + AGENT_STATE_TTL}
        else:
            self._redis.set(key, data, ex=AGENT_STATE_TTL)

    def get_agent_state(self, agent_id: str) -> Optional[dict]:
        key = f"mc:agent:{agent_id}"
        if self._using_fallback:
            entry = self._fallback.get(key)
            if entry and entry["expires"] > time.time():
                return json.loads(entry["data"])
            return None
        data = self._redis.get(key)
        if data:
            return json.loads(data)
        return None

    # --- Generic key-value ---

    def set(self, key: str, value: str, ttl: int = SESSION_TTL) -> None:
        full_key = f"mc:{key}"
        if self._using_fallback:
            self._fallback[full_key] = {"data": value, "expires": time.time() + ttl}
        else:
            self._redis.set(full_key, value, ex=ttl)

    def get(self, key: str) -> Optional[str]:
        full_key = f"mc:{key}"
        if self._using_fallback:
            entry = self._fallback.get(full_key)
            if entry and entry["expires"] > time.time():
                return entry["data"]
            return None
        return self._redis.get(full_key)

    # --- Stats ---

    def flush_expired(self) -> int:
        """Flush expired entries from fallback store."""
        if not self._using_fallback:
            return 0
        now = time.time()
        expired_keys = [k for k, v in self._fallback.items()
                       if isinstance(v, dict) and "expires" in v and v["expires"] < now]
        for k in expired_keys:
            del self._fallback[k]
        return len(expired_keys)
