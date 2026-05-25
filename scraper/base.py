"""
面经爬虫基类模块

定义所有面经爬虫的统一接口，提供公共的 HTTP 客户端、
请求延迟、User-Agent 等基础能力，子类只需实现搜索和解析逻辑。
还提供通过 Bing 搜索间接获取目标站点面经链接的辅助方法，
用于解决部分站点搜索页 JS 渲染或需要认证而无法直接爬取的问题。
"""

import asyncio
from abc import ABC, abstractmethod
from urllib.parse import quote_plus

import httpx
from bs4 import BeautifulSoup


class BaseCrawler(ABC):
    """
    面经爬虫抽象基类。

    提供通用的异步 HTTP 客户端和请求间延迟机制，
    子类需实现 name、search、fetch_content 三个核心方法。
    对于搜索页无法直接爬取的站点，可使用 _search_via_bing 辅助方法。
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

    BING_URL = "https://www.bing.com/search"

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

    async def close(self):
        """关闭 HTTP 客户端"""
        await self.client.aclose()

    async def _search_via_bing(
        self,
        query: str,
        site_domain: str,
        max_count: int = 10,
        extra_keywords: str = "",
    ) -> list[dict]:
        """
        通过 Bing 搜索间接获取目标站点的面经链接。

        适用于目标站点搜索页 JS 渲染或需要认证而无法直接爬取的场景。
        使用 Bing 的 site: 语法限定搜索范围到目标域名。

        Args:
            query: 搜索关键词（如 "字节跳动 后端"）
            site_domain: 目标站点域名（如 "zhihu.com"）
            max_count: 最多返回多少条结果
            extra_keywords: 追加到搜索词中的额外关键词（如 "面经 面试"）

        Returns:
            [{"title": str, "url": str}, ...]
        """
        results = []
        full_query = f"site:{site_domain} {extra_keywords} {query}".strip()
        page = 1

        while len(results) < max_count:
            params = {"q": full_query, "first": (page - 1) * 10 + 1}
            try:
                resp = await self.client.get(self.BING_URL, params=params)
                resp.raise_for_status()
            except Exception:
                break

            soup = BeautifulSoup(resp.text, "lxml")
            items = self._parse_bing_results(soup, site_domain)
            if not items:
                break

            results.extend(items)
            page += 1
            await self.sleep()

        return results[:max_count]

    def _parse_bing_results(self, soup: BeautifulSoup, site_domain: str) -> list[dict]:
        """解析 Bing 搜索结果页，提取指定域名的链接。"""
        items = []
        for li in soup.select("li.b_algo"):
            link = li.select_one("h2 a")
            if not link:
                continue
            href = link.get("href", "")
            title = link.get_text(strip=True)
            if not href or not title:
                continue
            if site_domain not in href:
                continue
            items.append({"title": title, "url": href})
        return items
