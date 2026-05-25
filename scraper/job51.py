"""
前程无忧面经爬虫模块

从前程无忧搜索面试经验相关内容。
由于前程无忧的站内搜索为 JS 渲染且主要面向职位搜索，
因此通过 Bing 搜索的 site: 语法间接获取面经链接，
再访问详情页提取内容。
"""

from bs4 import BeautifulSoup

from scraper.base import BaseCrawler


class Job51Crawler(BaseCrawler):
    """前程无忧面经异步爬虫。"""

    BASE_URL = "https://www.51job.com"
    SITE_DOMAIN = "51job.com"

    @property
    def name(self) -> str:
        return "前程无忧"

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
        tags = self._parse_tags(soup)
        await self.sleep()
        return {"content": content, "tags": tags}

    def _parse_content(self, soup: BeautifulSoup) -> str:
        for selector in [
            ".job-detail",
            ".detail-content",
            ".content",
            "article",
        ]:
            el = soup.select_one(selector)
            if el:
                text = el.get_text("\n", strip=True)
                if len(text) > 20:
                    return text[:5000]

        body = soup.find("body")
        return body.get_text("\n", strip=True)[:5000] if body else ""

    def _parse_tags(self, soup: BeautifulSoup) -> list[str]:
        tags = []
        for el in soup.select(".tag, .label, .cate a"):
            tag = el.get_text(strip=True)
            if tag and len(tag) < 20:
                tags.append(tag)
        return tags[:5]
