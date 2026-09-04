# Packet F run log

## Invocation

The probe was run exactly once. The credential was loaded directly from the named 1Password item and was not written to the command line or repository:

```bash
OPENAI_API_KEY="$(op item get lqdvpkoqlshkwj2hq2wzt6cjva --fields credential --reveal)" uv run --with-editable . scripts/run_demo_latency_probe.py
```

Exit code: `0`

PEP 723 resolution check: with this installed `uv` version, plain `uv run scripts/run_demo_latency_probe.py` creates an isolated script environment containing only the declared `playwright` dependency and cannot import the working-tree package. The exact working-tree invocation is therefore `uv run --with-editable . scripts/run_demo_latency_probe.py` as used above.

OpenAI/OpenRouter model identifier: `google/gemini-3.1-pro-preview` (OpenRouter's provider-qualified identifier form).

Report path: `tmp/latency-probe/reports/run-20260904T104449.988148Z.json`

## Redacted report JSON

```json
{
  "run_id": "2026-09-04T10:44:49.987+00:00",
  "target": "https://accounts.hcaptcha.com/demo?sitekey=c86d730b-300a-444c-a8c5-5312e7a93628",
  "wall_clock_duration_ms": 34182.61,
  "model_latency_ms": [
    9561.32,
    14494.96
  ],
  "reasoning_rounds": [
    {
      "round": 1,
      "response_schema": "ImageAreaSelectChallenge",
      "latency_ms": 9561.32,
      "outcome": "response"
    },
    {
      "round": 2,
      "response_schema": "ImageAreaSelectChallenge",
      "latency_ms": 14494.96,
      "outcome": "response"
    }
  ],
  "terminal_signal": "challenge success",
  "challenge_signal": "success",
  "defensive_layers": {
    "challenge_viewport_unavailable_surfaced": false,
    "challenge_viewport_unavailable_typed_handled": false,
    "raw_attribute_error": false
  },
  "bounds_validation": {
    "in_bounds_count": 4,
    "out_of_bounds_count": 0,
    "rejection_fired": false
  },
  "sanitized_config": {
    "OPENAI_BASE_URL": "https://openrouter.ai/api/v1",
    "OPENAI_API_KEY": {
      "redacted": true,
      "length": 73
    },
    "OPENAI_MODEL": "google/gemini-3.1-pro-preview",
    "agent": {
      "RETRY_ON_FAILURE": false,
      "EXECUTION_TIMEOUT": 300,
      "RESPONSE_TIMEOUT": 60,
      "enable_challenger_debug": true
    },
    "browser": {
      "headless": true,
      "locale": "en-US",
      "viewport": [
        1280,
        900
      ]
    }
  },
  "exception": null,
  "report_path": "tmp/latency-probe/reports/run-20260904T104449.988148Z.json"
}
```

## Five-line interpretation

1. Two reasoning rounds completed in `9561.32 ms` and `14494.96 ms`.
2. Total wall-clock duration was `34182.61 ms`; the terminal signal was `challenge success` (context only, not a quality metric).
3. Bounds validation examined four generated points: four in bounds, zero out of bounds, and no rejection fired.
4. `ChallengeViewportUnavailable` did not surface, so its typed handler was not engaged during this run.
5. The run completed without any raw `AttributeError`; the repository leakage check found no persisted API-key value.

## Ruff

```text
$ uvx ruff check scripts/run_demo_latency_probe.py
All checks passed!
```

Additional hygiene check:

```text
API key leakage check: passed (no matching file content)
```
