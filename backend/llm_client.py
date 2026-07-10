"""
llm_client.py — NVIDIA NIM LLM Client
Uses the OpenAI-compatible NVIDIA API to chat with Llama 3.1 70B.
"""

import os
from openai import AsyncOpenAI
from dotenv import load_dotenv
from typing import AsyncGenerator

load_dotenv()


class NVIDIAClient:
    """Async wrapper around the NVIDIA NIM inference API."""

    def __init__(self):
        api_key = os.getenv("NVIDIA_API_KEY")
        if not api_key:
            api_key = "mock_key_not_configured"
        self.client = AsyncOpenAI(
            base_url="https://integrate.api.nvidia.com/v1",
            api_key=api_key,
        )
        self.model = os.getenv("MODEL", "meta/llama-3.1-70b-instruct")

    async def chat(self, messages: list, temperature: float = 0.7, max_tokens: int = 2048):
        """Single-shot completion (used by the MCP router for tool-selection)."""
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False,
        )
        return response

    async def stream_chat(
        self, messages: list, temperature: float = 0.7, max_tokens: int = 2048
    ) -> AsyncGenerator[str, None]:
        """Token-by-token streaming completion (used for the final answer)."""
        stream = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content
