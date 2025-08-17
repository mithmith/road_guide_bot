"""OpenAI client integration utilities.

This module provides a small wrapper around the official ``openai``
client so the rest of the project can interact with the Responses API
without dealing with low level configuration details.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from openai import OpenAI

from app.config import MODEL_NAME, OPENAI_API_KEY, OUT_PATH, PROMPT_PATH


class OpenAIClient:
    """Convenience wrapper for the OpenAI Responses API."""

    def __init__(
        self,
        api_key: str = OPENAI_API_KEY,
        model_name: str = MODEL_NAME,
    ) -> None:
        self.model_name = model_name
        # ``OpenAI`` reads the key from the environment if ``api_key`` is ``None``.
        # Passing it explicitly keeps the behaviour predictable.
        self._client = OpenAI(api_key=api_key)

    def create(self, input_data: Any):
        """Send ``input_data`` to the Responses API.

        Parameters
        ----------
        input_data:
            Either a plain string prompt or a list of messages compatible with
            the Responses API.
        """

        return self._client.responses.create(
            model=self.model_name,
            input=input_data,
        )

    def run_prompt_file(
        self,
        prompt_path: Path = PROMPT_PATH,
        out_path: Path = OUT_PATH,
    ) -> str:
        """Execute a prompt stored in ``prompt_path`` and save the result.

        The text response is returned and written to ``out_path``.
        """

        prompt = prompt_path.read_text(encoding="utf-8")
        resp = self.create(prompt)
        text = resp.output_text
        out_path.write_text(text, encoding="utf-8")
        return text
