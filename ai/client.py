import json
from typing import AsyncGenerator, Optional

import httpx


class AIClient:
    def __init__(self, base_url: str, api_key: str, model_name: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model_name = model_name
        self.chat_url = f"{self.base_url}/chat/completions"
        self._client = httpx.AsyncClient(timeout=120, follow_redirects=True)

    async def test(self) -> bool:
        resp = await self._client.post(
            self.chat_url,
            headers=self._headers(),
            json={
                "model": self.model_name,
                "messages": [{"role": "user", "content": "Hi"}],
                "max_tokens": 10,
            },
        )
        if resp.status_code == 401:
            raise ValueError("API Key 认证失败，请检查")
        if resp.status_code == 404:
            raise ValueError(f"模型 '{self.model_name}' 不可用，请检查")
        resp.raise_for_status()
        return True

    async def chat(self, messages: list[dict], **kwargs) -> str:
        body = {
            "model": self.model_name,
            "messages": messages,
            **kwargs,
        }
        resp = await self._client.post(
            self.chat_url,
            headers=self._headers(),
            json=body,
        )
        if resp.status_code == 401:
            raise ValueError("API Key 认证失败，请检查")
        if resp.status_code == 429:
            raise ValueError("请求过于频繁，请稍后重试")
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]

    async def chat_json(self, messages: list[dict], **kwargs) -> dict:
        text = await self.chat(messages, **kwargs)
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
            text = text.rsplit("```", 1)[0]
        return json.loads(text)

    def _headers(self) -> dict:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

    async def close(self):
        await self._client.aclose()
