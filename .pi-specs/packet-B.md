## Context

Repo: hcaptcha-challenger fork on branch feat/openrouter-provider. Packet A just landed: src/hcaptcha_challenger/tools/internal/providers/openai.py implements OpenAICompatProvider for any OpenAI-compatible endpoint (base_url, api_key, model). It is functionally a sibling to GeminiProvider but is currently unreachable from the library.

## Task

Wire OpenAICompatProvider into the tool classes so it can serve as a drop-in backend when a caller wants OpenAI-compatible routing instead of the hardcoded Gemini path. Do this in the smallest coherent change satisfying all points:

1. In src/hcaptcha_challenger/tools/internal/base.py (or wherever SharedBase lives), make the provider constructor selectable: add an optional `provider` kwarg that, when given, is used directly instead of constructing a GeminiProvider. Preserve backward compatibility so all existing call sites (ImageClassifier, SpatialPathReasoner, etc.) keep working unchanged when `provider` is not supplied.
2. In each tool class that constructs a provider internally (image_classifier.py, spatial/__init__.py, spatial/point.py, spatial/path.py, spatial/bbox.py, and any others), propagate the new `provider` kwarg through — also as an optional parameter that defaults to existing behavior.
3. Do not touch GeminiProvider, protocol.py, or the reasoner classes themselves.
4. Keep the code the user owns clean: this is a config seam, not a rewrite. Only the constructor signatures change.

## Acceptance

- Constructor of each listed tool class accepts a new optional `provider` kwarg
- When supplied, the provider is used directly; when absent, current Gemini construction path runs unchanged (no behavioral change for existing callers)
- Tests proving both paths: ruff passes, SYNTHETIC tests show provider injection produces the right class (mock the base/provider and assert wiring, not network calls)
- `git diff` shows ONLY the tool-class files changed + any test file; no other surfaces touched

## Verification

- `uvx ruff check` on all changed files
- `python3 -c "from hcaptcha_challenger.tools.image_classifier import ImageClassifier; ic = ImageClassifier('key', 'gemini-2.5-flash'); print(type(ic._provider))"` — confirms the Gemini path still works by default when provider is not supplied

## Notes

- Do not commit.
- Do not add new dependencies (httpx, google.genai are already present).
- If a tool class constructs the provider lazily (only when first used), preserve that laziness.
- Do not modify any existing file besides the ones listed. No changes to models.py, challenger.py.
