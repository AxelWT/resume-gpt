"""
面经爬虫基类模块

定义所有面经爬虫的统一接口，提供公共的 HTTP 客户端、
请求延迟、User-Agent 等基础能力，子类只需实现搜索和解析逻辑。

ScraplingBaseCrawler 在 BaseCrawler 基础上集成了 Scrapling 的
StealthyFetcher，支持 JS 渲染页面的抓取和反检测绕过，
并提供 Tavily 搜索降级机制。
"""

import asyncio
import logging
import os
from abc import ABC, abstractmethod
from urllib.parse import quote_plus

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class BaseCrawler(ABC):
    """
    面经爬虫抽象基类。

    提供通用的异步 HTTP 客户端和请求间延迟机制，
    子类需实现 name、search、fetch_content 三个核心方法。
    """

    DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }

    def __init__(self, timeout: int = 30, delay: float = 0.5):
        self.client = httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers=self.DEFAULT_HEADERS,
        )
        self.delay = delay

    @property
    @abstractmethod
    def name(self) -> str:
        """爬虫对应的站点名称，如 '牛客网'"""

    @abstractmethod
    async def search(self, query: str, max_count: int = 10) -> list[dict]:
        """
        搜索面经，返回结果列表。

        Returns:
            [{"title": str, "url": str}, ...]
        """

    @abstractmethod
    async def fetch_content(self, url: str) -> dict:
        """
        获取面经详情页内容。

        Returns:
            {"content": str, "tags": [str, ...]}
        """

    async def sleep(self):
        """请求间延迟，避免触发反爬"""
        await asyncio.sleep(self.delay)

    async def _search_via_tavily(
        self,
        query: str,
        site_domain: str,
        max_count: int = 10,
        extra_keywords: str = "",
    ) -> list[dict]:
        """
        通过 Tavily 搜索间接获取目标站点的面经链接。

        使用 Tavily 的 include_domains 参数限定搜索范围到目标域名，
        搜索结果自带 content 摘要，可直接用于分析而无需再抓取详情页。

        Args:
            query: 搜索关键词（如 "字节跳动 后端"）
            site_domain: 目标站点域名（如 "51job.com"）
            max_count: 最多返回多少条结果
            extra_keywords: 追加到搜索词中的额外关键词（如 "招聘 岗位"）

        Returns:
            [{"title": str, "url": str, "content": str}, ...]
        """
        api_key = os.getenv("TAVILY_API_KEY", "").strip()
        if not api_key:
            logger.warning(
                "[%s] TAVILY_API_KEY 未配置，跳过 Tavily 搜索降级", self.name
            )
            return []

        full_query = f"{extra_keywords} {query}".strip()
        try:
            from tavily import TavilyClient

            client = TavilyClient(api_key=api_key)
            response = await asyncio.to_thread(
                client.search,
                query=full_query,
                max_results=max_count,
                include_domains=[site_domain],
            )

            results = []
            for item in response.get("results", []):
                title = item.get("title", "").strip()
                url = item.get("url", "").strip()
                content = item.get("content", "").strip()
                if not title or not url:
                    continue
                result = {"title": title, "url": url}
                if content:
                    result["content"] = content[:5000]
                results.append(result)

            logger.info("[%s] Tavily 搜索返回 %d 条结果", self.name, len(results))
            return results
        except Exception as e:
            logger.warning("[%s] Tavily 搜索失败(%s)", self.name, e)
            return []

    async def close(self):
        """关闭 HTTP 客户端"""
        await self.client.aclose()


class ScraplingBaseCrawler(BaseCrawler):
    """
    基于 Scrapling 的面经爬虫基类。

    在 BaseCrawler 基础上集成 StealthyFetcher，支持：
    - JS 渲染页面的直接抓取（无需搜索引擎中转）
    - 反检测指纹伪装绕过
    - 自动降级：直接搜索失败时回退到 Tavily 搜索

    子类需实现：
    - _search_direct(): 直接爬取目标站点搜索页
    - _parse_content_from_page(): 从 Scrapling 页面对象解析正文
    - _parse_tags_from_page(): 从 Scrapling 页面对象解析标签（可选）
    """

    EXTRA_KEYWORDS = "面经 面试"

    async def _fetch_stealthy(self, url: str, **kwargs):
        """
        使用 StealthyFetcher 异步获取页面。

        StealthyFetcher.fetch() 是同步阻塞方法，
        通过 asyncio.to_thread() 包装以避免阻塞事件循环。

        Args:
            url: 目标页面 URL
            **kwargs: 传递给 StealthyFetcher.fetch() 的额外参数

        Returns:
            Scrapling Adaptor 页面对象
        """
        from scrapling import StealthyFetcher

        return await asyncio.to_thread(
            StealthyFetcher.fetch,
            url,
            headless=True,
            disable_resources=True,
            timeout=30000,
            wait=2000,
            **kwargs,
        )

    @abstractmethod
    async def _search_direct(self, query: str, max_count: int = 10) -> list[dict]:
        """
        直接爬取目标站点搜索页，子类实现。

        使用 StealthyFetcher 渲染 JS 搜索页并提取结果链接。
        返回空列表表示直接搜索失败，将自动降级到 Tavily 搜索。

        Returns:
            [{"title": str, "url": str}, ...]
        """

    async def search(self, query: str, max_count: int = 10) -> list[dict]:
        """
        搜索面经，优先直接搜索，失败时降级到 Tavily。

        降级策略：
        1. 先尝试直接爬取目标站点的搜索页（StealthyFetcher）
        2. 如果直接搜索失败或结果为空，回退到 Tavily 搜索
        """
        try:
            results = await self._search_direct(query, max_count)
            if results:
                return results
            logger.info("[%s] 直接搜索无结果，降级到 Tavily", self.name)
        except Exception as e:
            logger.warning("[%s] 直接搜索失败(%s)，降级到 Tavily", self.name, e)

        return await self._search_via_tavily(
            query, self.SITE_DOMAIN, max_count, self.EXTRA_KEYWORDS
        )

    async def fetch_content(self, url: str) -> dict:
        """
        获取面经详情页内容，使用 StealthyFetcher 渲染 JS 页面。

        降级策略：StealthyFetcher 失败时，回退到 httpx + BeautifulSoup。
        """
        if not url:
            return {"content": "", "tags": []}

        try:
            page = await self._fetch_stealthy(url)
            content = self._parse_content_from_page(page)
            tags = self._parse_tags_from_page(page)
            await self.sleep()
            return {"content": content, "tags": tags}
        except Exception as e:
            logger.warning(
                "[%s] StealthyFetcher 获取详情失败(%s)，降级到 httpx", self.name, e
            )

        try:
            resp = await self.client.get(url)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")
            content = self._parse_content_fallback(soup)
            tags = self._parse_tags_fallback(soup)
            await self.sleep()
            return {"content": content, "tags": tags}
        except Exception:
            return {"content": "", "tags": []}

    @abstractmethod
    def _parse_content_from_page(self, page) -> str:
        """从 Scrapling Adaptor 页面对象解析正文，子类实现。"""

    def _parse_tags_from_page(self, page) -> list[str]:
        """从 Scrapling Adaptor 页面对象解析标签，子类可覆盖。"""
        return []

    def _parse_content_fallback(self, soup: BeautifulSoup) -> str:
        """
        httpx+BeautifulSoup 降级解析正文。

        子类可覆盖此方法以提供站点特定的降级选择器。
        默认实现按通用选择器顺序尝试。
        """
        for selector in ["article", ".content", ".detail-content"]:
            el = soup.select_one(selector)
            if el:
                text = el.get_text("\n", strip=True)
                if len(text) > 20:
                    return text[:5000]
        body = soup.find("body")
        return body.get_text("\n", strip=True)[:5000] if body else ""

    def _parse_tags_fallback(self, soup: BeautifulSoup) -> list[str]:
        """httpx+BeautifulSoup 降级解析标签，子类可覆盖。"""
        tags = []
        for el in soup.select(".tag, .label"):
            tag = el.get_text(strip=True)
            if tag and len(tag) < 20:
                tags.append(tag)
        return tags[:5]
