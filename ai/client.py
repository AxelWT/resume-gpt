"""
AI 客户端模块

封装了对 OpenAI 兼容 API 的调用，支持任意兼容 OpenAI 接口的模型服务商
（如 OpenAI、DeepSeek、Moonshot、本地部署的 Ollama 等）。
提供文本聊天和 JSON 格式响应两种调用方式。
"""

import json
from typing import AsyncGenerator, Optional

import httpx


class AIClient:
    """
    OpenAI 兼容 API 的异步客户端。

    使用 httpx.AsyncClient 发起 HTTP 请求，支持：
    - test(): 测试连接和认证是否正常
    - chat(): 发送消息并获取文本回复
    - chat_json(): 发送消息并获取 JSON 格式的回复（自动解析）
    """

    def __init__(self, base_url: str, api_key: str, model_name: str):
        """
        初始化 AI 客户端。

        Args:
            base_url: API 基础地址，如 "https://api.openai.com/v1"
            api_key: API 密钥，用于 Bearer Token 认证
            model_name: 模型名称，如 "gpt-4o"、"deepseek-chat"
        """
        # 去除末尾的斜杠，防止拼接 URL 时出现双斜杠
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model_name = model_name
        # 拼接聊天补全接口的完整 URL
        self.chat_url = f"{self.base_url}/chat/completions"
        # 创建异步 HTTP 客户端，设置 120 秒超时（AI 响应可能较慢）并自动跟随重定向
        self._client = httpx.AsyncClient(timeout=120, follow_redirects=True)

    def _headers(self) -> dict:
        """构造请求头，包含 JSON 内容类型和 Bearer Token 认证"""
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

    async def test(self) -> bool:
        """
        测试 API 配置是否可用。
        发送一条简短消息来验证 API Key 和模型名是否正确。

        Returns:
            True 表示连接成功

        Raises:
            ValueError: API Key 无效（401）或模型不可用（404）
            httpx.HTTPStatusError: 其他 HTTP 错误
        """
        resp = await self._client.post(
            self.chat_url,
            headers=self._headers(),
            json={
                "model": self.model_name,
                "messages": [{"role": "user", "content": "Hi"}],
                "max_tokens": 10,  # 只请求少量 token，节省费用
            },
        )
        # 针对常见错误码给出友好的中文提示
        if resp.status_code == 401:
            raise ValueError("API Key 认证失败，请检查")
        if resp.status_code == 404:
            raise ValueError(f"模型 '{self.model_name}' 不可用，请检查")
        resp.raise_for_status()
        return True

    async def chat(self, messages: list[dict], **kwargs) -> str:
        """
        发送聊天消息并获取 AI 的文本回复。

        Args:
            messages: OpenAI 格式的消息列表，如 [{"role": "user", "content": "..."}]
            **kwargs: 额外的请求参数，如 temperature、max_tokens 等

        Returns:
            AI 回复的文本内容
        """
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
        # 处理常见错误状态码
        if resp.status_code == 401:
            raise ValueError("API Key 认证失败，请检查")
        if resp.status_code == 429:
            raise ValueError("请求过于频繁，请稍后重试")
        resp.raise_for_status()
        # 从 OpenAI 兼容的响应格式中提取回复文本
        data = resp.json()
        return data["choices"][0]["message"]["content"]

    async def chat_json(self, messages: list[dict], **kwargs) -> dict:
        """
        发送聊天消息并获取 JSON 格式的回复。
        AI 模型有时会在 JSON 外包裹 ```json ... ``` 的 markdown 代码块，
        此方法会自动剥离这些包裹并解析 JSON。

        Args:
            messages: OpenAI 格式的消息列表
            **kwargs: 额外的请求参数

        Returns:
            解析后的 Python 字典

        Raises:
            json.JSONDecodeError: AI 返回的内容无法解析为 JSON
        """
        text = await self.chat(messages, **kwargs)
        text = text.strip()
        # 如果 AI 返回了 markdown 代码块包裹的 JSON，剥掉外层
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]       # 去掉 ```json 行
            text = text.rsplit("```", 1)[0]      # 去掉末尾的 ```
        return json.loads(text)

    async def close(self):
        """关闭底层 HTTP 客户端，释放连接池资源"""
        await self._client.aclose()
