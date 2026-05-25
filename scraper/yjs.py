"""
应届生求职网面经爬虫模块

从应届生求职网搜索校招面经内容。
由于应届生求职网的站内搜索需要验证码，
因此通过 Bing 搜索的 site: 语法间接获取面经链接，
再访问详情页提取内容。
"""

from bs4 import BeautifulSoup

from scraper.base import BaseCrawler


class YjsCrawler(BaseCrawler):
    """应届生求职网面经异步爬虫。"""

    BASE_URL = "https://www.yingjiesheng.com"
    SITE_DOMAIN = "yingjiesheng.com"

    @property
    def name(self) -> str:
        return "应届生求职网"

    async def search(self, query: str, max_count: int = 10) -> list[dict]:
        return await self._search_via_bing(
            query=query,
            site_domain=self.SITE_DOMAIN,
            max_count=max_count,
            extra_keywords="面经 面试 笔试",
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
            ".post-content",
            ".article-content",
            ".bbs-content",
            ".t_f",
            "article",
            "#postlist",
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
        for el in soup.select(".tag, .label, .crumb a"):
            tag = el.get_text(strip=True)
            if tag and len(tag) < 20:
                tags.append(tag)
        return tags[:5]
