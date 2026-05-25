"""
猎聘面经爬虫模块

从猎聘搜索面试经验相关内容。
由于猎聘的站内面经搜索为 JS 渲染，
因此通过 Bing 搜索的 site: 语法间接获取面经链接，
再访问详情页提取内容。
"""

from bs4 import BeautifulSoup

from scraper.base import BaseCrawler


class LiepinCrawler(BaseCrawler):
    """猎聘面经异步爬虫。"""

    BASE_URL = "https://www.liepin.com"
    SITE_DOMAIN = "liepin.com"

    @property
    def name(self) -> str:
        return "猎聘"

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
            ".interview-detail",
            ".detail-content",
            ".job-desc",
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
        for el in soup.select(".tag, .label, .breadcrumb a"):
            tag = el.get_text(strip=True)
            if tag and len(tag) < 20:
                tags.append(tag)
        return tags[:5]
