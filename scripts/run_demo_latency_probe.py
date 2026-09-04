# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "playwright",
# ]
# ///
"""Run one latency/detachment probe against hCaptcha's official demo."""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from loguru import logger
from playwright.async_api import async_playwright

from hcaptcha_challenger import AgentConfig, AgentV
from hcaptcha_challenger.agent.exceptions import ChallengeViewportUnavailable
from hcaptcha_challenger.agent.validation import (
    BoundsValidationError,
    CoordinateBoundsValidator,
)
from hcaptcha_challenger.models import ChallengeSignal
from hcaptcha_challenger.tools import (
    ChallengeRouter,
    ImageClassifier,
    SpatialBboxReasoner,
    SpatialPathReasoner,
    SpatialPointReasoner,
)
from hcaptcha_challenger.tools.internal.providers.openai import OpenAICompatProvider
from hcaptcha_challenger.utils import SiteKey

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "google/gemini-3.1-pro-preview"
REDACTED_NAME = re.compile(r"key|token|req", re.IGNORECASE)
REPO_ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = REPO_ROOT / "tmp" / "latency-probe" / "reports"


class TimedOpenAICompatProvider(OpenAICompatProvider):
    """OpenAI-compatible provider that records whole-call model latency."""

    def __init__(self, base_url: str, api_key: str, model: str) -> None:
        super().__init__(base_url, api_key, model)
        self.rounds: list[dict[str, Any]] = []

    async def generate_with_images(self, **kwargs: Any) -> Any:
        started = time.perf_counter()
        round_data: dict[str, Any] = {
            "round": len(self.rounds) + 1,
            "response_schema": getattr(kwargs.get("response_schema"), "__name__", "unknown"),
        }
        try:
            result = await super().generate_with_images(**kwargs)
        except Exception as error:
            round_data.update(
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
                outcome="exception",
                exception_type=type(error).__name__,
            )
            self.rounds.append(round_data)
            raise
        round_data.update(
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
            outcome="response",
        )
        self.rounds.append(round_data)
        return result


def sanitize(value: Any, secret: str, field_name: str = "") -> Any:
    """Recursively redact credential-shaped fields and the known API key."""
    if REDACTED_NAME.search(field_name):
        length = len(value) if isinstance(value, str) else 0
        return {"redacted": True, "length": length}
    if isinstance(value, dict):
        return {str(key): sanitize(item, secret, str(key)) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize(item, secret) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, str) and secret:
        return value.replace(secret, "<redacted>")
    return value


def write_report(report: dict[str, Any], report_path: Path, secret: str) -> None:
    """Persist and print exactly the same sanitized JSON document."""
    sanitized = sanitize(report, secret)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(sanitized, indent=2, ensure_ascii=False)
    report_path.write_text(f"{rendered}\n", encoding="utf-8")
    print(rendered)


def install_bounds_telemetry(
    telemetry: dict[str, Any],
) -> tuple[Any, Any]:
    """Instrument the validator's existing fail-closed seams for this process."""
    original_points = CoordinateBoundsValidator.__dict__["require_points"]
    original_paths = CoordinateBoundsValidator.__dict__["require_paths"]

    def require_points(cls: type[CoordinateBoundsValidator], points: Any, bounds: Any) -> None:
        items = list(points)
        violations = cls.validate_points(items, bounds)
        telemetry["in_bounds_count"] += len(items) - len(violations)
        telemetry["out_of_bounds_count"] += len(violations)
        if violations:
            telemetry["rejection_fired"] = True
            raise BoundsValidationError(violations)

    def require_paths(cls: type[CoordinateBoundsValidator], paths: Any, bounds: Any) -> None:
        items = list(paths)
        violations = cls.validate_paths(items, bounds)
        telemetry["in_bounds_count"] += (2 * len(items)) - len(violations)
        telemetry["out_of_bounds_count"] += len(violations)
        if violations:
            telemetry["rejection_fired"] = True
            raise BoundsValidationError(violations)

    CoordinateBoundsValidator.require_points = classmethod(require_points)
    CoordinateBoundsValidator.require_paths = classmethod(require_paths)
    return original_points, original_paths


def wire_provider(agent: AgentV, provider: TimedOpenAICompatProvider) -> None:
    """Replace AgentV's tool instances using Packet B's provider injection seam."""
    tool_key = "provider-injected"
    arm = agent.robotic_arm
    arm._image_classifier = ImageClassifier(tool_key, provider=provider)
    arm._challenge_router = ChallengeRouter(tool_key, provider=provider)
    arm._spatial_point_reasoner = SpatialPointReasoner(tool_key, provider=provider)
    arm._spatial_path_reasoner = SpatialPathReasoner(tool_key, provider=provider)
    arm._spatial_bbox_reasoner = SpatialBboxReasoner(tool_key, provider=provider)


async def run_probe(api_key: str, base_url: str, model: str) -> int:
    """Execute one browser attempt and always emit a report."""
    started = time.perf_counter()
    run_id = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    file_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    report_path = REPORT_DIR / f"run-{file_stamp}.json"
    bounds = {
        "in_bounds_count": 0,
        "out_of_bounds_count": 0,
        "rejection_fired": False,
    }
    defensive = {
        "challenge_viewport_unavailable_surfaced": False,
        "challenge_viewport_unavailable_typed_handled": False,
        "raw_attribute_error": False,
    }
    report: dict[str, Any] = {
        "run_id": run_id,
        "target": None,
        "wall_clock_duration_ms": None,
        "model_latency_ms": [],
        "reasoning_rounds": [],
        "terminal_signal": None,
        "challenge_signal": None,
        "defensive_layers": defensive,
        "bounds_validation": bounds,
        "sanitized_config": {
            "OPENAI_BASE_URL": base_url,
            "OPENAI_API_KEY": api_key,
            "OPENAI_MODEL": model,
            "agent": {
                "RETRY_ON_FAILURE": False,
                "EXECUTION_TIMEOUT": 300,
                "RESPONSE_TIMEOUT": 60,
                "enable_challenger_debug": True,
            },
            "browser": {"headless": True, "locale": "en-US", "viewport": [1280, 900]},
        },
        "exception": None,
        "report_path": str(report_path.relative_to(REPO_ROOT)),
    }
    provider = TimedOpenAICompatProvider(base_url, api_key, model)
    original_points, original_paths = install_bounds_telemetry(bounds)

    def observe_log(message: Any) -> None:
        record = message.record
        text = record["message"]
        exception = record["exception"]
        exception_type = exception.type if exception else None
        if "ChallengeViewportUnavailable" in text or exception_type is ChallengeViewportUnavailable:
            defensive["challenge_viewport_unavailable_surfaced"] = True
        if "AttributeError" in text or exception_type is AttributeError:
            defensive["raw_attribute_error"] = True

    sink_id = logger.add(observe_log, level="DEBUG")
    exit_code = 0
    try:
        target = SiteKey.as_site_link(SiteKey.user_easy)
        parsed = urlparse(target)
        assert parsed.hostname == "accounts.hcaptcha.com", "Refusing non-official probe target"
        report["target"] = target

        config = AgentConfig(
            GEMINI_API_KEY="provider-injected",
            RETRY_ON_FAILURE=False,
            EXECUTION_TIMEOUT=300,
            RESPONSE_TIMEOUT=60,
            enable_challenger_debug=True,
        )
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            try:
                context = await browser.new_context(
                    locale="en-US", viewport={"width": 1280, "height": 900}
                )
                page = await context.new_page()
                agent = AgentV(page=page, agent_config=config)
                wire_provider(agent, provider)
                await page.goto(target)
                await agent.robotic_arm.click_checkbox()
                signal = await agent.wait_for_challenge()
                report["challenge_signal"] = signal.value
                report["terminal_signal"] = (
                    "challenge success" if signal is ChallengeSignal.SUCCESS else "challenge failed"
                )
            finally:
                await browser.close()
    except Exception as error:  # noqa: BLE001
        exit_code = 1
        if isinstance(error, ChallengeViewportUnavailable):
            defensive["challenge_viewport_unavailable_surfaced"] = True
            defensive["challenge_viewport_unavailable_typed_handled"] = True
        if isinstance(error, AttributeError):
            defensive["raw_attribute_error"] = True
        report["terminal_signal"] = type(error).__name__
        report["exception"] = {
            "type": type(error).__name__,
            "message": str(error),
            "traceback": traceback.format_exc(),
        }
    finally:
        logger.remove(sink_id)
        CoordinateBoundsValidator.require_points = original_points
        CoordinateBoundsValidator.require_paths = original_paths
        report["wall_clock_duration_ms"] = round((time.perf_counter() - started) * 1000, 2)
        report["reasoning_rounds"] = provider.rounds
        report["model_latency_ms"] = [item["latency_ms"] for item in provider.rounds]
        write_report(report, report_path, api_key)

    return exit_code


def main() -> int:
    """Validate environment configuration and launch the async probe."""
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        print("OPENAI_API_KEY is required", file=sys.stderr)
        return 2
    base_url = os.environ.get("OPENAI_BASE_URL", DEFAULT_BASE_URL)
    model = os.environ.get("OPENAI_MODEL", DEFAULT_MODEL)
    return asyncio.run(run_probe(api_key, base_url, model))


if __name__ == "__main__":
    raise SystemExit(main())
