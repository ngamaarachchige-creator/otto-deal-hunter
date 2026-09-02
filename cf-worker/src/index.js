// Thin authenticated proxy in front of D1's Workers Binding API.
//
// D1 doesn't give external clients (our Python/FastAPI backend on Vercel) a
// normal connection string — the only way to reach a D1 database with real
// query throughput is a Worker binding, and Cloudflare's own docs say the raw
// admin REST API (reachable from anywhere) isn't meant for live app traffic
// since it shares the account-wide Cloudflare API rate limit. So this Worker
// exists purely to be that binding, exposing a minimal HTTP API our backend
// calls instead.
//
// Auth is a single shared-secret bearer token (set via `wrangler secret put
// AUTH_TOKEN`) — this Worker is not meant to be reachable by anyone but our
// own backend.

function unauthorized() {
  return new Response(JSON.stringify({ error: "unauthorized" }), {
    status: 401,
    headers: { "content-type": "application/json" },
  });
}

function checkAuth(request, env) {
  const header = request.headers.get("authorization") || "";
  const token = header.startsWith("Bearer ") ? header.slice(7) : "";
  return token && token === env.AUTH_TOKEN;
}

async function handleExecute(request, env) {
  const { sql, params } = await request.json();
  if (typeof sql !== "string") {
    return new Response(JSON.stringify({ error: "sql must be a string" }), { status: 400 });
  }
  const stmt = env.DB.prepare(sql);
  const bound = Array.isArray(params) && params.length ? stmt.bind(...params) : stmt;
  const result = await bound.all();
  return new Response(JSON.stringify({
    rows: result.results,
    meta: result.meta,
  }), { headers: { "content-type": "application/json" } });
}

async function handleBatch(request, env) {
  const { statements } = await request.json();
  if (!Array.isArray(statements)) {
    return new Response(JSON.stringify({ error: "statements must be an array" }), { status: 400 });
  }
  const stmts = statements.map(({ sql, params }) => {
    const stmt = env.DB.prepare(sql);
    return Array.isArray(params) && params.length ? stmt.bind(...params) : stmt;
  });
  const results = await env.DB.batch(stmts);
  return new Response(JSON.stringify({
    results: results.map((r) => ({ rows: r.results, meta: r.meta })),
  }), { headers: { "content-type": "application/json" } });
}

const SCRAPE_DISPATCH_URL =
  "https://api.github.com/repos/ngamaarachchige-creator/otto-deal-hunter/actions/workflows/scrape.yml/dispatches";

// GitHub Actions' own `schedule:` cron trigger runs on shared, lowest-priority
// queue infrastructure and is documented by GitHub as best-effort: it can be
// delayed by an hour or more, or silently skipped entirely, under platform
// load — confirmed in practice (some 3-hour slots never fired, others fired
// ~1.5h late). Cloudflare Workers' Cron Triggers run on Cloudflare's own edge
// infra, independent of GitHub Actions' queue and independent of any of our
// own devices being powered on, so this is the actually-reliable scheduler:
// it just calls GitHub's workflow_dispatch REST API directly on a fixed cron.
async function triggerScrape(env) {
  const resp = await fetch(SCRAPE_DISPATCH_URL, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.GH_DISPATCH_TOKEN}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "otto-d1-proxy-cron",
    },
    body: JSON.stringify({ ref: "main" }),
  });
  if (resp.status !== 204) {
    const text = await resp.text().catch(() => "");
    throw new Error(`dispatch failed: ${resp.status} ${text}`);
  }
  console.log(`triggerScrape: dispatched OK (status ${resp.status})`);
}

export default {
  async scheduled(event, env, ctx) {
    // Previously this ran bare inside ctx.waitUntil() with nothing catching
    // or logging failure -- combined with observability being off by
    // default for this Worker, a failed dispatch (bad token, GitHub API
    // hiccup, etc.) would fail completely silently with zero trace anywhere.
    // Explicit try/catch + console.log/error here, plus observability now
    // enabled in wrangler.jsonc, means a failure is actually visible instead
    // of just "no new GitHub Actions run showed up, cause unknown."
    console.log(`scheduled: firing at ${new Date(event.scheduledTime).toISOString()} (cron ${event.cron})`);
    ctx.waitUntil(
      triggerScrape(env).catch((err) => {
        console.error(`scheduled: triggerScrape failed: ${err && err.message || err}`);
      })
    );
  },

  async fetch(request, env) {
    if (!checkAuth(request, env)) return unauthorized();

    const url = new URL(request.url);
    try {
      if (request.method === "POST" && url.pathname === "/execute") {
        return await handleExecute(request, env);
      }
      if (request.method === "POST" && url.pathname === "/batch") {
        return await handleBatch(request, env);
      }
      if (request.method === "GET" && url.pathname === "/health") {
        return new Response(JSON.stringify({ status: "ok" }), { headers: { "content-type": "application/json" } });
      }
      return new Response(JSON.stringify({ error: "not found" }), { status: 404 });
    } catch (err) {
      return new Response(JSON.stringify({ error: String(err && err.message || err) }), {
        status: 500,
        headers: { "content-type": "application/json" },
      });
    }
  },
};
