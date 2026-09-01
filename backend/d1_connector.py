"""A sqlite3.Connection/Cursor-shaped shim over the D1 proxy Worker's HTTP API.

D1 doesn't offer a normal DB connection string — the only way to reach it with
real query throughput is a Cloudflare Worker binding (see cf-worker/), so this
module exists to let the rest of the codebase keep using the exact same
sqlite3-flavored code it already had (named `:param` placeholders, dict-like
row access, `cursor.execute`/`executemany`/`fetchall`/`fetchone`, `conn.commit`/
`close`) without a rewrite — get_db_connection() in database.py just returns
one of these instead of a real sqlite3.Connection when D1 is configured.
"""
import os
import re
import requests
from typing import Any, Dict, List, Optional, Union


class D1Row(dict):
    """Behaves like sqlite3.Row: supports both row["col"] and row[0]-style
    positional access, since a couple of call sites use the latter."""

    def __init__(self, data: Dict[str, Any]):
        super().__init__(data)
        self._keys = list(data.keys())

    def __getitem__(self, key):
        if isinstance(key, int):
            return super().__getitem__(self._keys[key])
        return super().__getitem__(key)


_NAMED_PARAM_RE = re.compile(r":(\w+)")


def _translate(sql: str, params: Optional[Union[Dict[str, Any], List[Any], tuple]]):
    """Converts sqlite3-style `:name` placeholders + a params dict into D1's
    positional `?` placeholders + an ordered args list. Passes through
    already-positional params (list/tuple) unchanged."""
    if not params:
        return sql, []
    if isinstance(params, (list, tuple)):
        return sql, list(params)

    positional: List[Any] = []

    def repl(m):
        positional.append(params[m.group(1)])
        return "?"

    new_sql = _NAMED_PARAM_RE.sub(repl, sql)
    return new_sql, positional


class D1Cursor:
    def __init__(self, conn: "D1Connection"):
        self.conn = conn
        self._rows: List[D1Row] = []
        self._idx = 0
        self.rowcount = -1
        self.lastrowid = None

    def execute(self, sql: str, params: Optional[Union[Dict, List, tuple]] = None) -> "D1Cursor":
        new_sql, pos_params = _translate(sql, params)
        resp = self.conn._post("/execute", {"sql": new_sql, "params": pos_params})
        self._rows = [D1Row(r) for r in resp.get("rows", [])]
        self._idx = 0
        meta = resp.get("meta", {}) or {}
        self.rowcount = meta.get("changes", -1)
        self.lastrowid = meta.get("last_row_id")
        return self

    def executemany(self, sql: str, params_list: List[Union[Dict, List, tuple]]) -> "D1Cursor":
        statements = []
        for params in params_list:
            new_sql, pos_params = _translate(sql, params)
            statements.append({"sql": new_sql, "params": pos_params})
        # D1's batch() runs every statement in one round trip; each still gets
        # its own params, same translated SQL text — this is our executemany.
        total_changes = 0
        last_id = None
        for i in range(0, len(statements), 100):  # keep batches a sane size
            chunk = statements[i:i + 100]
            resp = self.conn._post("/batch", {"statements": chunk})
            for r in resp.get("results", []):
                meta = r.get("meta", {}) or {}
                total_changes += meta.get("changes", 0) or 0
                if meta.get("last_row_id"):
                    last_id = meta["last_row_id"]
        self.rowcount = total_changes
        self.lastrowid = last_id
        self._rows = []
        self._idx = 0
        return self

    def fetchall(self) -> List[D1Row]:
        rows = self._rows[self._idx:]
        self._idx = len(self._rows)
        return rows

    def fetchone(self) -> Optional[D1Row]:
        if self._idx >= len(self._rows):
            return None
        row = self._rows[self._idx]
        self._idx += 1
        return row

    def __iter__(self):
        return iter(self.fetchall())


class D1Connection:
    def __init__(self, base_url: str, auth_token: str, timeout: int = 20):
        self.base_url = base_url.rstrip("/")
        self.auth_token = auth_token
        self.timeout = timeout

    def _post(self, path: str, body: dict) -> dict:
        resp = requests.post(
            f"{self.base_url}{path}",
            json=body,
            headers={"Authorization": f"Bearer {self.auth_token}"},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            raise RuntimeError(f"D1 proxy error: {data['error']}")
        return data

    def cursor(self) -> D1Cursor:
        return D1Cursor(self)

    def execute(self, sql: str, params=None) -> D1Cursor:
        return self.cursor().execute(sql, params)

    def commit(self):
        # D1 commits per statement/batch server-side — nothing to flush.
        pass

    def close(self):
        # Stateless HTTP client, nothing to release.
        pass


def is_d1_configured() -> bool:
    return bool(os.environ.get("D1_PROXY_URL") and os.environ.get("D1_PROXY_AUTH_TOKEN"))


def get_d1_connection() -> D1Connection:
    return D1Connection(
        base_url=os.environ["D1_PROXY_URL"],
        auth_token=os.environ["D1_PROXY_AUTH_TOKEN"],
    )
