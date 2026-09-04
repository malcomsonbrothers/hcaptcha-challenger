## Context

Repo: hcaptcha-challenger fork on branch feat/openrouter-provider. The fork now contains: OpenAICompatProvider (`src/hcaptcha_challenger/tools/internal/providers/openai.py`, requires explicit `base_url` + `api_key` + `model`), tool-level `provider=` injection (Packet B), absorbed defensive layers (Packet D: `agent/validation.py` CoordinateBoundsValidator fail-closed before browser input, `agent/exceptions.py ChallengeViewportUnavailable` typed instead of None-deref AttributeErrors, DPI-aware coordinate grid), and a consistent pytest-style synthetic test suite (Packet E).

Background (verified in prior runs, documented externally): under a high-latency provider (p50 ≈ 90–150s per reasoning round, with HTTP 503 retries), the live challenge iframe at accounts.hcaptcha.com would detach before reasoning completed — observed as 3 of 6 runs dying with `AttributeError: NoneType .locator`. Packet D converted that crash into a typed, fail-closed signal. We have NOT yet run the agent end-to-end against the fork's own defensive layers, and we have NOT yet validated that an OpenRouter-fronted endpoint (expected p50 ≈ 5s) eliminates the viewport-lifetime race entirely.

This packet builds a **single-run latency probe** inside the fork: one headless attempt against hCaptcha's official accounts.hcaptcha.com demo page (SiteKey.user_easy), driven through the OpenAI-compatible provider pointed at an OpenAI-compatible endpoint chosen via environment variables. Its purpose is a **latency/detachment regression measurement**: prove the typed-exception path never fires as a crash and capture per-round latency so we can characterize the endpoint. NOT a quality benchmark — we do not count wins/losses as a metric; the terminal signal is recorded only for context.

## Task

### Unit 1: Probe script

Create `scripts/run_demo_latency_probe.py` in the fork with PEP 723 inline metadata (mirroring the shape of probe scripts used elsewhere), runnable via `uv run scripts/run_demo_latency_probe.py` from the fork root. PEP 723 dependencies: playwright only — the fork itself supplies hcaptcha-challenger via uv's project resolution (verify `uv run` resolves the working-tree package; if it does not, document the exact invocation needed).

Behavior, faithfully constrained:

1. **Hard-pinned target:** hCaptcha's official demo only — `SiteKey.as_site_link(SiteKey.user_easy)` from `hcaptcha_challenger.utils`. Assert the parsed host equals `accounts.hcaptcha.com` before navigating; refuse otherwise. NEVER accept a CLI arg or env var that changes the target URL or sitekey.
2. **Provider wiring from environment:**
   - `OPENAI_BASE_URL` (default `https://openrouter.ai/api/v1`), `OPENAI_API_KEY` (required; if absent, exit cleanly with code 2 and a message naming the missing var — never print the key), `OPENAI_MODEL` (default `gemini-3.1-pro-preview` — use the exact upstream model identifier format OpenRouter expects, e.g. `google/gemini-3.1-pro-preview`; verify and document in the run log which identifier form you used).
   - Construct one `OpenAICompatProvider(base_url, api_key, model)` and pass it via the `provider=` kwarg into every tool class used by the agent (ImageClassifier, ChallengeRouter, SpatialPointReasoner, SpatialPathReasoner, SpatialBboxReasoner). Wire these into AgentV however the fork's post-Packet-B architecture expects — inspect `agent/challenger.py` and the tool constructors to find the supported injection path. Do NOT modify production `src/` code to make injection work; if no clean injection path exists for AgentV, report that finding in the run log and stop (that would become a follow-up packet's finding).
3. **Agent config:** `AgentConfig` with `RETRY_ON_FAILURE=False`, `EXECUTION_TIMEOUT=300`, `RESPONSE_TIMEOUT=60`, `enable_challenger_debug=True`. Do NOT override model names via config (the provider carries the model). Headless Chromium via Playwright, `locale="en-US"`, viewport 1280×900.
4. **Flow:** goto demo → `click_checkbox()` → `wait_for_challenge()`. Exactly one attempt; no retry loop in the probe.
5. **Telemetry report** written to `fork/tmp/latency-probe/reports/run-<UTC-timestamp>.json` containing: UTC run id, wall-clock duration ms, per-reasoning-round model latency (timed around each provider call if a clean observation seam exists; otherwise from library debug logs), terminal signal (`challenge success` / `challenge failed` / typed exception name), whether `ChallengeViewportUnavailable` surfaced anywhere (typed-handled vs raw-AttributeError — a raw AttributeError is a REGRESSION to flag), bounds-validation decisions (in-bounds/out-of-bounds counts, whether any rejection fired), and sanitized config (redact key material — redact anything named key/token/req, recording `{redacted: true, length: n}` shapes). Print the JSON to stdout as well.
6. **Failure hygiene:** catch-all outer handler recording `{type, message, traceback}` into the report; exit code 1 on exception, 0 otherwise. Never leak `OPENAI_API_KEY` into the report, logs, or traceback summaries.

### Unit 2: One live verification run

Run the probe exactly once via `uv run scripts/run_demo_latency_probe.py` (Will will supply `OPENAI_API_KEY` in the environment; if it is absent when you try, exit 2 per above and note it — do not fabricate). Include the resulting report JSON (redacted) and a 5-line interpretation in your run log: per-round latencies observed, terminal signal, whether any defensive layer engaged, and whether the run completed without raw AttributeErrors.

If the run fails for environmental reasons (network, missing key, Playwright browser missing), record the failure verbatim and stop — do not iterate beyond ONE fix attempt for a harness bug (e.g., wrong import path); never mask a target-page behavior with a retry.

## Acceptance

1. `scripts/run_demo_latency_probe.py` exists, PEP 723 header, hard-pinned to accounts.hcaptcha.com demo, refuses alternate targets
2. Provider constructed from `OPENAI_BASE_URL`/`OPENAI_API_KEY`/`OPENAI_MODEL`; injected without touching `src/`
3. One live run executed (or a documented environmental blocker); report JSON captured with latency numbers, defensive-layer engagement flags, terminal signal, and zero raw AttributeErrors
4. No changes to `src/`, `tests/`, `pyproject.toml`, or `uv.lock` (probe-time deps are PEP-723 inline only)
5. `uvx ruff check scripts/run_demo_latency_probe.py` clean
6. Key material never printed or persisted
7. Do not commit

## Verification

- Run log contains: exact `uv run` invocation, the OpenAI model identifier used, report JSON path, per-round latency list, terminal signal, defensive-layer flags, and confirmation of no raw AttributeError / no key leakage
- `uvx ruff check` output pasted

## Notes

- Framing reminder: this is an infrastructure latency probe measuring whether the typed fail-closed paths from Packet D hold end-to-end and what the endpoint's response time looks like. Do not frame or adjust anything around improving pass rates; do not add retry logic; do not tune prompts.
- The demo page is Google's own official test page; this is normal library dogfooding, equivalent to running upstream's own examples.
- One packet, one reviewable diff. Do not commit.
- If any step reveals that wiring the provider into AgentV requires production-code changes, STOP and report — that becomes Packet G, not something to fix in-flight.
