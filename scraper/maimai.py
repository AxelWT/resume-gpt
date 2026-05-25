"""
脉脉面经爬虫模块

从脉脉搜索面经相关的职言帖子。
由于脉脉搜索需要登录认证，无法直接用 httpx 抓取，
因此通过 Bing 搜索的 site: 语法间接获取脉脉面经链接，
再访问详情页提取内容。
"""

from bs4 import BeautifulSoup

from scraper.base import BaseCrawler


class MaimaiCrawler(BaseCrawler):
    """脉脉面经异步爬虫。"""

    BASE_URL = "https://maimai.cn"
    SITE_DOMAIN = "maimai.cn"

    @property
    def name(self) -> str:
        return "脉脉"

    async def search(self, query: str, max_count: int = 10) -> list[dict]:
        return await self._search_via_bing(
            query=query,
            site_domain=self.SITE_DOMAIN,
            max_count=max_count,
            extra_keywords="面经 面试",
        )

    async def fetch_content(self, url: str) -> dict:
        try:
            resp = await self.client.get(url)
            resp.raise_for_status()
        except Exception:
            return {"content": "", "tags": []}

        soup = BeautifulSoup(resp.text, "lxml")
        content = self._parse_content(soup)
        await self.sleep()
        return {"content": content, "tags": []}

    def _parse_content(self, soup: BeautifulSoup) -> str:
        for selector in [
            ".feed-content",
            ".rich-text",
            ".detail-content",
            "article",
        ]:
            el = soup.select_one(selector)
            if el:
                text = el.get_text("\n", strip=True)
                if len(text) > 20:
                    return text[:5000]

        body = soup.find("body")
        return body.get_text("\n", strip=True)[:5000] if body else ""
