"""
BOSS直聘面经爬虫模块

从BOSS直聘搜索公司面试评价和面经内容。
由于BOSS直聘面经搜索页为 JS 渲染，无法直接用 httpx 抓取，
因此通过 Bing 搜索的 site: 语法间接获取面经链接，
再访问详情页提取内容。
"""

from bs4 import BeautifulSoup

from scraper.base import BaseCrawler


class BossCrawler(BaseCrawler):
    """BOSS直聘面经异步爬虫。"""

    BASE_URL = "https://www.zhipin.com"
    SITE_DOMAIN = "zhipin.com"

    @property
    def name(self) -> str:
        return "BOSS直聘"

    async def search(self, query: str, max_count: int = 10) -> list[dict]:
        return await self._search_via_bing(
            query=query,
            site_domain=self.SITE_DOMAIN,
            max_count=max_count,
            extra_keywords="面经 面试",
        )

    async def fetch_content(self, url: str) -> dict:
        if not url or url == self.BASE_URL:
            return {"content": "", "tags": []}
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
