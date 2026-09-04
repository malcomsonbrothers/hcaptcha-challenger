## Context

Repo: hcaptcha-challenger fork on branch feat/openrouter-provider. Packets A–D have landed an OpenAI-compatible provider, tool-level provider pluggability, PyYAML declaration, and absorbed defensive boundary protections (DPI-aware grid, coordinate bounds validation, typed viewport-unavailability), guarded by synthetic tests in `tests/`.

Consistency problem: `tests/` is now stylistically mixed. Packet B's `test_tools_provider_injection.py` uses plain pytest functions with `@pytest.mark.parametrize`. Packet D's `test_agent_defensive_boundaries.py` uses `unittest.IsolatedAsyncioTestCase` classes with `setUp` and assert-methods. pyproject.toml already configures `pytest-asyncio >= 1.1.0` with `asyncio_mode = "auto"`, so plain async pytest test functions run natively with no extra setup. Upstream's own tests are already pytest-style.

Goal: converge the two fork-added mixed-style test files on the project's primary style — plain pytest functions, native `async def test_*`, module-level fixtures/parametrize — so future packets have exactly one test idiom to copy. This is a pure style/reorganization change: zero behavior change, zero production code touched, same test COUNT and same code paths exercised.

## Task

### Unit 1: Port test_tools_provider_injection.py
It is already pytest-style. Leave it alone except to remove any needless `unittest`-flavored constructs (verify there are none; if a class wrapper exists, flatten to module-level functions using `@pytest.mark.parametrize`).

### Unit 2: Port test_agent_defensive_boundaries.py to pytest idiom
Current shape: several `unittest.IsolatedAsyncioTestCase` subclasses (`TestCoordinateGridDpi`, `TestBoundsValidation`, framing classes around viewport unavailability) with `setUp` methods, `self.assert*` assertions, and shared-state via `self`.

Port to:
- Module-level `async def test_*` functions (functions are auto-detected by `asyncio_mode = "auto"`; no decorators needed)
- `unittest.mock` objects (AsyncMock/Mock) constructed per-test or via `@pytest.fixture`
- Plain `assert` statements instead of `self.assertEqual` / `self.assertRaises` (use `pytest.raises` for exception assertions)
- Shared setup (e.g. `ViewportBounds(x=10, y=20, width=100, height=80)`) extracted to a fixture or a module-level factory function
- Keep the `matplotlib.use("Agg", force=True)` at module import time, BEFORE any numpy/mpl submodule import — this ordering matters and must be preserved exactly
- Keep every existing test scenario, case name (snake_case the class/method names, e.g. `TestCoordinateGridDpi::test_physical_buffer_is_downsampled_to_logical_dimensions` → `test_physical_buffer_is_downsampled_to_logical_dimensions`)
- Do NOT reduce the assertion count. If an `assertRaises` context manager wraps multiple lines, preserve that shape with `pytest.raises`

### Unit 3: Sweep check
Run a final consistency sweep over the full `tests/` directory: list any remaining files importing `unittest` beyond legit use of `unittest.mock`. Only `test_agent_defensive_boundaries.py` should need changes; report any others you find in the run log, do not change them unless they're pure tests added by our packets (i.e. not upstream-controlled files). Upstream's own test files stay untouched.

## Acceptance

1. `tests/test_agent_defensive_boundaries.py` contains NO `unittest.TestCase` / `IsolatedAsyncioTestCase` / `self.assert*` constructs; uses plain pytest functions, `async def`, and `pytest.raises` where needed
2. `tests/test_tools_provider_injection.py` unchanged (or trivially flattened if a class wrapper exists)
3. `python3 -m pytest tests/ -v` runs the ported suite and every ported test passes at the SAME pass/fail status as before the port (currently: all passing)
4. `uvx ruff check` on changed files is clean
5. pyproject.toml and uv.lock UNTOUCHED — pytest, pytest-asyncio already declared
6. No production-code (`src/`) changes
7. Do not commit

## Verification

- Before: run `python3 -m pytest tests/test_agent_defensive_boundaries.py -v` and record the baseline pass list
- After: run again, confirm identical test-name list (minus class prefixes) and identical pass count
- Run full `python3 -m pytest tests/ -v --timeout=300 -k "not gemini and not webm"` (skip network/live-flavored tests) and confirm synthetic tests all green
- `uvx ruff check tests/`

## Notes

- If you hit a test that *cannot* be ported and must remain unittest-style for a specific technical reason (e.g. relies on IsolatedAsyncioTestCase's loop lifecycle in a way asyncio_mode=auto doesn't replicate), STOP and report it in the log — do not force-port through semantic drift.
- The framing is purely code-consistency, not quality-scoring: "one test idiom across the fork's synthetic suite."
- One packet, one reviewable diff. Do not commit.
