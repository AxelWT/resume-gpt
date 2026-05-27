"""
牛客网面经爬虫模块

负责从牛客网（nowcoder.com）搜索和抓取面试经验帖。
支持关键词搜索、分页获取、帖子详情和标签提取。
使用 BeautifulSoup 解析 HTML 页面内容。
"""

import logging

from bs4 import BeautifulSoup

from scraper.base import BaseCrawler

logger = logging.getLogger(__name__)


class NowCrawler(BaseCrawler):
    """
    牛客网面经异步爬虫。
    """

    BASE_URL = "https://www.nowcoder.com"
    SEARCH_URL = f"{BASE_URL}/search"
    SITE_DOMAIN = "nowcoder.com"
    EXTRA_KEYWORDS = "面经 面试"

    @property
    def name(self) -> str:
        return "牛客网"

    async def _search_direct(self, query: str, max_count: int = 10) -> list[dict]:
        results = []
        page = 1

        while len(results) < max_count:
            params = {
                "query": query,
                "type": "post",
                "subType": "interview",
                "page": page,
            }
            try:
                resp = await self.client.get(self.SEARCH_URL, params=params)
                resp.raise_for_status()
            except Exception:
                break

            soup = BeautifulSoup(resp.text, "lxml")
            items = self._parse_search_results(soup)
            if not items:
                break

            results.extend(items)
            page += 1
            await self.sleep()

        return results[:max_count]

    def _parse_search_results(self, soup: BeautifulSoup) -> list[dict]:
        items = []
        for link in soup.select("a[href*='/discuss/']"):
            href = link.get("href", "")
            title = link.get_text(strip=True)
            if not title or not href:
                continue
            if len(title) < 5:
                continue
            url = href if href.startswith("http") else f"{self.BASE_URL}{href}"
            items.append({"title": title, "url": url})
        return items

    def _parse_content(self, soup: BeautifulSoup) -> str:
        for selector in [
            ".discuss-detail .content",
            ".post-content",
            ".detail-content",
            "article",
            ".rich-content",
        ]:
            el = soup.select_one(selector)
            if el:
                text = el.get_text("\n", strip=True)
                if len(text) > 20:
                    return text

        body = soup.find("body")
        return body.get_text("\n", strip=True)[:5000] if body else ""

    def _parse_tags(self, soup: BeautifulSoup) -> list[str]:
        tags = []
        for el in soup.select(".tag-item, .tag-label, .discuss-tag"):
            tag = el.get_text(strip=True)
            if tag:
                tags.append(tag)
        return tags
