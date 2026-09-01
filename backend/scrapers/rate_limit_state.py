"""Shared, persistent rate-limit cooldown tracking, per source host.

Tonight's deep scrape exposed a real bug: when Riyasewana started 429-ing
detail-page requests, that only aborted the *current* batch — the very next
page's scrape started a fresh detail-fetch pass with no memory of the block,
immediately got 429'd again, and repeated that ~60 times across the run. Worse,
each of those code paths (detail_fetch, the listing-page scrapers, the liveness
checker) has its own local state that dies with the process, so nothing was
shared even within a single run, let alone across the manual "Fetch Ads"
button, Copilot-triggered scrapes, and the liveness sweep, all of which can hit
the same host independently.

This persists a simple "don't hit this host again until <timestamp>" cooldown
to a small JSON file on disk, so it survives across processes and across the
different scrape entry points. Cooldown escalates on repeated hits (10min ->
20min -> ... capped at 2h) rather than resetting, since a second 429 shortly
after the first means the first cooldown wasn't long enough yet.
"""
import json
import os
import time
from typing import Optional

_STATE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "rate_limit_state.json"
)

_INITIAL_COOLDOWN_SECONDS = 10 * 60
_MAX_COOLDOWN_SECONDS = 2 * 60 * 60

# Which environment this process is running in, for the durable event log —
# local dev/CI both hit the shared D1 DB independently, so knowing which one
# recorded a given hit matters for reading the pattern later.
_SOURCE_ENV = "github_actions" if os.environ.get("GITHUB_ACTIONS") else "local"


def _log_event_to_db(host: str, cooldown_seconds: float, status_code: Optional[int]) -> None:
    """Best-effort durable record of this hit, so rate_limit_report.py can show
    real patterns over time instead of just "currently blocked or not". Never
    lets a DB hiccup break the actual scraping/cooldown logic — this is purely
    observability on top of it."""
    try:
        from ..database import get_db_connection
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO rate_limit_events (host, cooldown_seconds, source_env, status_code) "
            "VALUES (:host, :cooldown_seconds, :source_env, :status_code)",
            {
                "host": host,
                "cooldown_seconds": int(cooldown_seconds),
                "source_env": _SOURCE_ENV,
                "status_code": status_code,
            },
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def _check_db_for_active_cooldown(host: str) -> Optional[float]:
    """Cross-environment fallback: if this process has no local memory of a
    cooldown for `host`, check the shared DB for a recent hit from *another*
    environment (e.g. a GitHub Actions run blocking Riyasewana, checked from
    the local Mac) and derive whether that cooldown would still be active.
    Best-effort — returns None (not "clear") on any failure, so this never
    makes local checks slower/riskier than before if D1 is unreachable."""
    try:
        from ..database import get_db_connection
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT hit_at, cooldown_seconds FROM rate_limit_events "
            "WHERE host = :host ORDER BY hit_at DESC LIMIT 1",
            {"host": host},
        )
        row = cursor.fetchone()
        conn.close()
        if not row:
            return None
        import datetime
        hit_at = row["hit_at"]
        if isinstance(hit_at, str):
            hit_at = hit_at.replace("Z", "").split(".")[0]
            hit_dt = datetime.datetime.fromisoformat(hit_at)
        else:
            return None
        elapsed = (datetime.datetime.utcnow() - hit_dt).total_seconds()
        remaining = (row["cooldown_seconds"] or 0) - elapsed
        return remaining if remaining > 0 else None
    except Exception:
        return None


def _load() -> dict:
    try:
        with open(_STATE_PATH, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save(state: dict) -> None:
    os.makedirs(os.path.dirname(_STATE_PATH), exist_ok=True)
    tmp_path = _STATE_PATH + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(state, f)
    os.replace(tmp_path, _STATE_PATH)


def is_cooling_down(host: str) -> Optional[float]:
    """Returns seconds remaining in the cooldown for `host`, or None if clear.

    Checks local process/file memory first (fast, no network); only falls
    back to a DB lookup when this process has no local record for the host
    at all, so a cooldown set by a *different* environment (e.g. a GitHub
    Actions run) is still respected here — the result is cached locally so
    that fallback only costs one DB round trip per process, not per request.
    """
    state = _load()
    entry = state.get(host)
    if entry:
        remaining = entry["until"] - time.time()
        return remaining if remaining > 0 else None

    # No local record at all for this host in this process — check the
    # shared DB once in case another environment recorded a hit recently.
    remaining = _check_db_for_active_cooldown(host)
    now = time.time()
    if remaining:
        state[host] = {"until": now + remaining, "length": remaining, "last_hit": now}
    else:
        # Cache the "clear" result too (as a zero-length, already-expired
        # entry) so a busy loop doesn't re-hit the DB on every call.
        state[host] = {"until": now - 1, "length": 0, "last_hit": 0}
    _save(state)
    return remaining


_MIN_SECONDS_BETWEEN_ESCALATIONS = 5.0


def record_rate_limit(host: str, status_code: Optional[int] = None) -> float:
    """Records a 429/403 from `host`, escalating the cooldown if one was already
    active or recently expired. Returns the new cooldown length in seconds.

    A batch of concurrent worker threads can each independently hit the block
    within milliseconds of each other — that's one real-world incident, not
    several, so calls within _MIN_SECONDS_BETWEEN_ESCALATIONS of the last
    recorded hit just refresh the existing cooldown rather than re-escalating it."""
    state = _load()
    entry = state.get(host)
    now = time.time()
    if entry and (now - entry.get("last_hit", 0)) < _MIN_SECONDS_BETWEEN_ESCALATIONS:
        return entry["length"]
    if entry and (now - entry.get("last_hit", 0)) < _MAX_COOLDOWN_SECONDS:
        # Still within memory of the last hit — this cooldown wasn't long enough.
        new_length = min(entry["length"] * 2, _MAX_COOLDOWN_SECONDS)
    else:
        new_length = _INITIAL_COOLDOWN_SECONDS
    state[host] = {"until": now + new_length, "length": new_length, "last_hit": now}
    _save(state)
    _log_event_to_db(host, new_length, status_code)
    return new_length
