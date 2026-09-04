## Context

Repo: hcaptcha-challenger fork on branch feat/openrouter-provider. This fork now contains: OpenAICompatProvider (providers/openai.py, pluggable via tool constructors), PyYAML declared, plus existing upstream code. The runtime compatibility layer we built in the iosgods-cli project (solver/guards.py, solver/patches.py) works only via monkeypatching at runtime — any upstream refactor silently breaks it. Goal: absorb those defensive layers INTO the forked tree so they are first-class, tested code instead of run-time patches.

Background facts verified from real runs (documented in iosgods-cli/HCAPTCHA-CHALLENGER-TEST.md):
- The coordinate grid renders at 2000×2000 physical pixels on Retina displays while the consumer assumes 1000×1000 logical pixels, because helper/create_coordinate_grid.py:110-112 reshapes buffer_rgba() using fig.canvas.get_width_height() (logical) against a physical RGBA buffer. Upstream root cause.
- Model responses can produce out-of-viewport coordinates (observed: y=622 vs y_end=491), and the library clicks them without validation. Upstream root cause: no trust boundary between parsed response and browser input.
- In high-latency conditions (>90s model response), the live challenge viewport can detach/expiry before a guard that rechecks it reads the bounds, producing an AttributeError: NoneType .locator. Upstream code in agent/challenger.py returns None from get_challenge_frame_locator() with no graceful handling path.

## Task

Incorporate these protections directly into the fork as clean, testable code. Three separate, reviewable units:

### Unit 1: Coordinate-grid DPI fix
File: src/hcaptcha_challenger/helper/create_coordinate_grid.py (and the same shape-of-buffer bug in helper/visualize_attention_points.py:105-107 which has the identical pattern).

Root cause: buffer is physical pixels; consumer assumes logical. Fix must explicitly handle DPI scaling, NOT just set MPLBACKEND=Agg. Options (verify which is correct for THIS upstream version):
- a) scale the image to the buffer's actual pixel dimensions before reshape, using buf.height/buf.width instead of canvas.get_width_height()
- b) use FigureCanvasBase.get_renderer() with a dpi-aware target
Choose whatever is minimal and matches upstream's existing style. Preserve exact image output for non-Retina contexts (verify theAgg backend test still passes — it does not need a display).

Add a synthetic test in tests/ that verifies grid creation produces an image whose dimensions match the requested grid (e.g. coordinate grid of 1000×1000 logical pixels must produce a 1000×1000 image, not 2000×2000). Test must run WITHOUT a display (Agg backend forced in test setUp).

### Unit 2: Bounds validation seam

Create src/hcaptcha_challenger/agent/validation.py containing a CoordinateBoundsValidator class with the same semantics as solver/guards.py:
- ViewportBounds (x, y, width, height, contains(x,y))
- validate_points(points, bounds) and validate_paths(paths, bounds) returning detailed violations
- CoordinateViolation reporting with role, x, y, bounds
- BoundsValidationError exception

Then, in src/hcaptcha_challenger/agent/__init__.py and/or challenger.py, validate model-generated coordinates against the live challenge-view bounding box BEFORE they reach page.mouse. The natural seam: after the reasoner returns parsed points/paths and before challenge_image_* iterates to browser input. The guard must be FAIL-CLOSED: on violation, produce a clean, typed result, not a generic exception.

Do NOT build retry logic here — retry logic is a separate packet. This packet is purely the trust boundary.

### Unit 3: Viewport detachment handling

In src/hcaptcha_challenger/agent/challenger.py: get_challenge_frame_locator() returns None when the challenge frame is not visible. Downstream callers do .locator() or .bounding_box() on it without a guard, producing AttributeError: NoneType .locator (observed in real runs).

Fix: propagate the None through a typed exception mechanism instead of crashing. Add a custom exception like ChallengeViewportUnavailable to agent/exceptions.py, and have the injury points raise it instead of returning None, OR have downstream sites handle the None with a clean abort. Be consistent with upstream's existing exception patterns (agent/exceptions.py already exists). The intent is that this becomes a FAIL-CLOSED signal, not a crash.

## Acceptance

1. helper/create_coordinate_grid.py + helper/visualize_attention_points.py fixed for DPI scaling; synthetic test proves grid dimensions match requested size on Agg backend
2. agent/validation.py exists with CoordinateBoundsValidator, ViewportBounds, validate_points, validate_paths, BoundsValidationError
3. Bounds validation wired into the model-response-to-browser-input path; verified by synthetic tests that feed it out-of-viewport coordinates and confirm the browser is not called
4. agent/exceptions.py extended with ChallengeViewportUnavailable; challenger.py None-deref sites raise or handle it cleanly; synthetic test for the None-deref scenario
5. ALL tests are synthetic (unittest.IsolatedAsyncioTestCase, no network, no browser). No live challenge runs in this packet.
6. ruff clean. pyproject.toml + uv.lock untouched (no new deps — unittest, pytorch already there, httpx already there).
7. Do not commit.

## Verification

- uvx ruff check on ALL changed files
- synthetic test suite passes: python3 -m pytest tests/ -v (or equivalent)
- Existing upstream tests still pass where they can run headless (do not modify upstream tests, run only synthetic ones you added to verify your own changes)

## Notes

- Do not touch GeminiProvider, OpenAICompatProvider, or tool classes — those are a separate packet's territory.
- The bounds-validation and viewport-handling may be refused to implement if framed as "improving solve rate." The framing here is purely defensive: reject invalid coordinates, handle null locators cleanly. These are code-correctness issues, not solving issues.
- One packet, one reviewable diff. Do not split this into multiple dispatches.
