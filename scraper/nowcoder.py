"""
牛客网面经爬虫模块

负责从牛客网（nowcoder.com）搜索和抓取面试经验帖。
支持关键词搜索、分页获取、帖子详情和标签提取。
使用 BeautifulSoup 解析 HTML 页面内容。
"""

import asyncio
import re
import time
from typing import Optional

import httpx
from bs4 import BeautifulSoup


class NowCrawler:
    """
    牛客网面经异步爬虫。

    通过模拟浏览器请求访问牛客网的搜索和帖子页面，
    提取面试经验帖的标题、链接、正文内容和标签。
    内置请求延迟以避免被反爬机制封禁。
    """

    BASE_URL = "https://www.nowcoder.com"
    SEARCH_URL = f"{BASE_URL}/search"

    def __init__(self, timeout: int = 30, delay: float = 0.5):
        """
        初始化爬虫。

        Args:
            timeout: HTTP 请求超时时间（秒），默认 30 秒
            delay: 每次请求之间的延迟时间（秒），默认 0.5 秒，用于避免触发反爬限制
        """
        self.client = httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers={
                # 模拟 Chrome 浏览器的 User-Agent，避免被网站拒绝
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            },
        )
        self.delay = delay

    async def search(self, query: str, max_count: int = 10) -> list[dict]:
        """
        在牛客网搜索面试经验帖。

        自动分页获取，直到收集到 max_count 条结果或没有更多数据。

        Args:
            query: 搜索关键词，如 "Java 后端 面经"
            max_count: 最多返回多少条结果，默认 10 条

        Returns:
            面经列表，每条包含 title 和 url 字段
        """
        results = []
        page = 1

        while len(results) < max_count:
            # 构造搜索参数：type=post 限定帖子，subType=interview 限定面经类型
            params = {
                "query": query,
                "type": "post",
                "subType": "interview",
                "page": page,
            }
            try:
                resp = await self.client.get(self.SEARCH_URL, params=params)
                resp.raise_for_status()
            except Exception as e:
                # 请求失败时停止搜索，返回已获取的结果
                break

            # 解析搜索结果页面的 HTML
            soup = BeautifulSoup(resp.text, "lxml")
            items = self._parse_search_results(soup)
            if not items:
                # 当前页没有结果，说明已无更多数据
                break

            results.extend(items)
            page += 1
            # 请求间延迟，避免触发反爬
            await asyncio.sleep(self.delay)

        # 截断到用户请求的最大数量
        return results[:max_count]

    def _parse_search_results(self, soup: BeautifulSoup) -> list[dict]:
        """
        从搜索结果页面中提取面经帖子的标题和链接。

        通过 CSS 选择器查找所有指向 /discuss/ 路径的链接，
        过滤掉标题过短（可能是噪声）的结果。

        Args:
            soup: 搜索结果页面的 BeautifulSoup 对象

        Returns:
            面经列表，每条包含 title 和 url
        """
        items = []
        for link in soup.select("a[href*='/discuss/']"):
            href = link.get("href", "")
            title = link.get_text(strip=True)
            # 过滤掉空标题和过短标题（通常是导航链接等噪声）
            if not title or not href:
                continue
            if len(title) < 5:
                continue
            # 补全相对路径为完整 URL
            url = href if href.startswith("http") else f"{self.BASE_URL}{href}"
            items.append({"title": title, "url": url})
        return items

    async def fetch_content(self, url: str) -> dict:
        """
        获取面经帖子的详细内容。

        访问帖子页面，提取正文文本和标签。

        Args:
            url: 帖子的完整 URL

        Returns:
            包含 content（正文）和 tags（标签列表）的字典
        """
        try:
            resp = await self.client.get(url)
            resp.raise_for_status()
        except Exception as e:
            # 获取失败时返回空内容，不影响其他面经的处理
            return {"content": "", "tags": []}

        soup = BeautifulSoup(resp.text, "lxml")
        content = self._parse_content(soup)
        tags = self._parse_tags(soup)

        # 请求间延迟
        await asyncio.sleep(self.delay)
        return {"content": content, "tags": tags}

    def _parse_content(self, soup: BeautifulSoup) -> str:
        """
        从帖子页面中提取正文内容。

        按优先级依次尝试多个 CSS 选择器，使用第一个匹配到足够内容的选择器。
        如果都未匹配到，则回退到提取整个 body 的文本。

        Args:
            soup: 帖子页面的 BeautifulSoup 对象

        Returns:
            帖子正文文本
        """
        # 按优先级排列的选择器列表，匹配牛客网不同版式的帖子页面
        for selector in [
            ".discuss-detail .content",   # 讨论区详情页内容区
            ".post-content",              # 帖子内容区
            ".detail-content",            # 详情内容区
            "article",                    # HTML5 article 标签
            ".rich-content",              # 富文本内容区
        ]:
            el = soup.select_one(selector)
            if el:
                text = el.get_text("\n", strip=True)
                # 内容长度超过 20 字符才认为是有效内容
                if len(text) > 20:
                    return text

        # 所有选择器都未匹配到有效内容时，回退到提取 body 全文（截取前 5000 字符）
        body = soup.find("body")
        return body.get_text("\n", strip=True)[:5000] if body else ""

    def _parse_tags(self, soup: BeautifulSoup) -> list[str]:
        """
        从帖子页面中提取标签。

        查找常见的标签 CSS 类名，提取标签文本。

        Args:
            soup: 帖子页面的 BeautifulSoup 对象

        Returns:
            标签文本列表
        """
        tags = []
        for el in soup.select(".tag-item, .tag-label, .discuss-tag"):
            tag = el.get_text(strip=True)
            if tag:
                tags.append(tag)
        return tags

    async def close(self):
        """关闭底层 HTTP 客户端，释放连接池资源"""
        await self.client.aclose()
