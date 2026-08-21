# Connecting an AI coding agent to this project's Ollama instance

OTTO's AI Inspect feature runs on a local LLM, not a paid API. This file is
the reference for how that connection works, so any agent picking up this
project doesn't have to rediscover it.

## The hardware

- Machine: Windows PC, hostname `TUFGAMING-0001`, GPU: RTX 5060 Ti (16GB VRAM), 16GB system RAM.
- Reachable on the LAN at `192.168.1.23`.
- SSH: `ssh "vinuka gamaarachchig@192.168.1.23" "<command>"` (key already trusted, passwordless).
  Default remote shell is `cmd.exe`, not PowerShell — for PowerShell, wrap with
  `powershell -NoProfile -Command "..."`.
  **Gotcha:** if the PowerShell command contains `$_` (e.g. `Where-Object { $_.Name ... }`),
  bash will try to expand `$_` before ssh ever sees it. Wrap the whole ssh argument in
  **single** quotes, or escape as `\$_`, or just avoid `$_`-based one-liners over ssh —
  they're finicky enough to not be worth it for a quick check.
- Ollama version installed: 0.32.x, plain user process (not a Windows service — after a
  reboot it may need to be relaunched manually; check with `ollama --version` over SSH).

## Ollama itself

- Listens on `http://192.168.1.23:11434` (plain HTTP, no auth — it's LAN-only).
- Check what's installed: `curl -s http://192.168.1.23:11434/api/tags`
- Pull a model: `ssh "vinuka gamaarachchig@192.168.1.23" "ollama pull <model>"` — this can
  take a while; run it with `run_in_background: true` and poll the output file, don't block
  on it in the foreground.
- Remove a model: `ssh "vinuka gamaarachchig@192.168.1.23" "ollama rm <model>"`
- Current model: `qwen3-vl:8b` (6.1GB, Q4_K_M, 262K context, vision+completion+tools+thinking).
  Picked because it's the largest vision model that comfortably fits 16GB VRAM with headroom
  (verified against Ollama's actual registry, not blog claims — `qwen3-vl:30b` is 20GB and
  would spill out of VRAM on this card).

## How the app talks to it

- `backend/ai_assistant.py` is the only file that calls Ollama. It POSTs to
  `{OLLAMA_HOST}/api/chat` with `{"model": ..., "messages": [...], "stream": false}`.
- Env vars (see `.env.example`): `OLLAMA_HOST` (default `http://192.168.1.23:11434`),
  `OLLAMA_MODEL` (default `qwen3-vl:8b`). Change these once the app runs on the same
  machine as Ollama (point `OLLAMA_HOST` at `127.0.0.1:11434`) instead of over LAN.
- Images: fetched from the listing's `image_url`, base64-encoded, and passed as
  `messages[].images: [b64string]` — that's the Ollama vision API convention, not
  OpenAI-style `image_url` objects.
- Test the whole pipeline directly, bypassing the frontend entirely:
  `curl -s -X POST http://localhost:8000/api/ai/inspect/<car_id>` — if this returns a
  real analysis, the model connection is fine and any "it's not working" report is a
  frontend bug, not a model/network problem. Check this FIRST before assuming Ollama
  is broken.

## Known model quirks (already worked around in ai_assistant.py)

- Cold start: first call after the model's been idle takes ~45–65s (loading into VRAM).
  Subsequent calls are faster. This is normal, not a hang.
- The model doesn't reliably follow "don't do X" formatting instructions (e.g. "no
  markdown", "no word count"). Don't trust prompt compliance alone for output formatting —
  strip it server-side with regex as a safety net (see the `re.sub` calls in
  `inspect_car()`).

## Remote access (not yet set up)

Home Wi-Fi already reaches the PC directly. For access away from home, the plan was
Tailscale on the PC + phone (free tier) — this was **paused**, not completed. If picking
this up: user needs to create a Tailscale account and generate a reusable auth key
themselves (requires their login), then `tailscale up --authkey=<key>` can be run
headlessly over SSH.
