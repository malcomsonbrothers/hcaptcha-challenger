## Context

Repo: hcaptcha-challenger fork on branch feat/openrouter-provider. The library has a runtime dependency that is imported but not declared in pyproject.toml: hcaptcha_challenger 0.19.0 imports yaml somewhere in the code, but PyYAML is not listed in [project].dependencies.

## Task

Declare PyYAML as a real dependency.

1. Find where yaml is imported: `grep -rn "^import yaml\|^from yaml" src/` — locate actual sites. If none in src/, check tools/internal/ and skills manager code (rules.yaml loading).
2. Add PyYAML to [project].dependencies in pyproject.toml: "PyYAML>=6.0"
3. Regenerate uv.lock: run `uv lock` in repo root. Do not manually edit uv.lock.
4. Verify lock contains pyyaml: `grep -n pyyaml uv.lock`

## Acceptance

- pyproject.toml lists PyYAML as declared dependency
- uv.lock contains pyyaml entry
- ONLY those two files changed — no source files, no tests, no unrelated dependency version bumps in lockfile beyond what adding pyyaml naturally requires
- `python3 -c "import yaml"` works after `uv sync`

## Verification

- `uv sync` succeeds
- `grep -n pyyaml uv.lock` finds entry
- `python3 -c "import yaml""` works

## Notes

- Do not commit.
- No other dependencies.
- ONLY pyproject.toml + uv.lock allowed.
