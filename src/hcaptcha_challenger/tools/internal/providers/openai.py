"""OpenAI-compatible chat completions provider."""

import base64
import mimetypes
from pathlib import Path
from typing import TypeVar, cast

import httpx
from loguru import logger
from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_fixed

from hcaptcha_challenger.tools.internal.providers.gemini import extract_first_json_block

ResponseT = TypeVar("ResponseT", bound=BaseModel)


class OpenAICompatProvider:
    """Image chat provider for OpenAI-compatible chat completions APIs."""

    def __init__(self, base_url: str, api_key: str, model: str):
        """Initialize the provider with an endpoint root, API key, and model."""
        self._base_url = base_url
        self._api_key = api_key
        self._model = model
        self._response: httpx.Response | None = None

    @property
    def last_response(self) -> httpx.Response | None:
        """Get the last HTTP response for debugging purposes."""
        return self._response

    @property
    def _chat_completions_url(self) -> str:
        """Build the chat completions URL while preserving any query string."""
        url = httpx.URL(self._base_url)
        if url.path.rstrip("/").endswith("/chat/completions"):
            return str(url)
        path = f"{url.path.rstrip('/')}/chat/completions"
        return str(url.copy_with(path=path))

    def _headers(self) -> dict[str, str]:
        """Build authentication headers for OpenAI-compatible and Azure APIs."""
        headers = {"Content-Type": "application/json"}
        host = httpx.URL(self._base_url).host
        if host.endswith((".openai.azure.com", ".services.ai.azure.com")):
            headers["api-key"] = self._api_key
        else:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    @staticmethod
    def _image_content(image: Path) -> dict[str, object]:
        """Encode an image as an OpenAI data-URL content block."""
        mime_type = mimetypes.guess_type(image.name)[0] or "application/octet-stream"
        encoded = base64.b64encode(image.read_bytes()).decode("ascii")
        return {
            "type": "image_url",
            "image_url": {"url": f"data:{mime_type};base64,{encoded}"},
        }

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_fixed(3),
        before_sleep=lambda retry_state: logger.warning(
            f"Retry request ({retry_state.attempt_number}/3) - "
            f"Wait 3 seconds - Exception: {retry_state.outcome.exception()}"
        ),
    )
    async def generate_with_images(
        self,
        *,
        images: list[Path],
        response_schema: type[ResponseT],
        user_prompt: str | None = None,
        description: str | None = None,
        **kwargs,
    ) -> ResponseT:
        """Generate and parse a structured response from image inputs."""
        content = [
            self._image_content(Path(image))
            for image in images
            if image and Path(image).exists()
        ]
        if user_prompt and isinstance(user_prompt, str):
            content.append({"type": "text", "text": user_prompt})

        messages: list[dict[str, object]] = []
        if description:
            messages.append({"role": "system", "content": description})
        messages.append({"role": "user", "content": content})

        payload = {
            **kwargs,
            "model": self._model,
            "messages": messages,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": response_schema.__name__,
                    "strict": True,
                    "schema": response_schema.model_json_schema(),
                },
            },
        }

        async with httpx.AsyncClient() as client:
            self._response = await client.post(
                self._chat_completions_url,
                headers=self._headers(),
                json=payload,
            )
        self._response.raise_for_status()

        response_data = self._response.json()
        message = response_data["choices"][0]["message"]
        parsed = message.get("parsed")
        if isinstance(parsed, BaseModel):
            return response_schema(**parsed.model_dump())
        if isinstance(parsed, dict):
            return response_schema(**cast(dict[str, object], parsed))

        response_text = message.get("content")
        if isinstance(response_text, str):
            try:
                return response_schema.model_validate_json(response_text)
            except ValueError:
                json_data = extract_first_json_block(response_text)
                if json_data:
                    return response_schema(**json_data)

        raise ValueError(f"Failed to parse response: {response_text}")
