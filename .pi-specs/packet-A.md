## Context

Repo: hcaptcha-challenger (a fork at /Users/will/Documents/Areas/Forks/malcomsonbrothers/hcaptcha-challenger, branch feat/openrouter-provider). It is a library that drives image-based visual reasoning for spatial tasks through Playwright. The tools layer has a ChatProvider protocol in src/hcaptcha_challenger/tools/internal/providers/protocol.py, a single implementation GeminiProvider in providers/gemini.py, and tool classes (image_classifier, spatial) in tools/ that construct providers internally. The protocol docstring says an OpenAI-compatible provider is planned but not implemented.

## Task

Implement OpenAICompatProvider as a new file src/hcaptcha_challenger/tools/internal/providers/openai.py. This is a drop-in backend implementing the same ChatProvider interface defined in protocol.py, for routing image+structured-output requests through any OpenAI-compatible chat completions endpoint (e.g. OpenRouter, or a local vLLM).

Requirements:
- Match the GeminiProvider contract exactly: same __init__ shape (base_url, api_key, model), same async method generate_with_images with the same parameters (images: list[Path], response_schema, user_prompt, description, **kwargs), same return type contract (parsed pydantic model), same tenacity retry policy with stop_after_attempt and wait_fixed, same extract_first_json_block-based JSON parsing
- Encode images as data-URL `image_url` content blocks (base64), not file uploads, since there is no Files API
- Support structured output via json_schema response format; pass response_schema.model_json_schema()
- Constructor accepts arbitrary base URL so the same code works with OpenRouter, Azure, or a local LLM server
- Do NOT modify upstream files: no changes to GeminiProvider, protocol.py, or any existing tool class. New file only.

## Acceptance

- New file `src/hcaptcha_challenger/tools/internal/providers/openai.py` exists
- File is importable without import cycles (from hcaptcha_challenger.tools.internal.providers import openai should work when installed)
- OpenAICompatProvider has generate_with_images matching the ChatProvider protocol signature exactly
- Images serialized as base64 data-URL image_url blocks, correctly encoded
- Structured output passed via response_format json_schema
- tenacity retry decorator with same stop/wait as GeminiProvider
- ruff/pyflakes-clean (uv.lock already defines lint; run `uvx ruff check`)

## Verification

- `uvx ruff check` on the new file
- `python3 -c "import hcaptcha_challenger.tools.internal.providers.openai"` (with PYTHONPATH=src) — confirm import success, no cycles

## Notes

- Do not commit.
- Do not add dependencies beyond httpx (already present): no new pypi packages. Use an async httpx client.
- Do not modify any existing file.
