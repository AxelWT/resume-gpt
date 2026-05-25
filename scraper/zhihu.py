"""
知乎面经爬虫模块

从知乎搜索面经相关的问答内容，提取问题和回答作为面经数据。
由于知乎搜索页为 JS 渲染，无法直接用 httpx 抓取，
因此通过 Bing 搜索的 site: 语法间接获取知乎面经链接，
再访问知乎详情页提取内容。
"""

from bs4 import BeautifulSoup

from scraper.base import BaseCrawler


class ZhihuCrawler(BaseCrawler):
    """知乎面经异步爬虫。"""

    BASE_URL = "https://www.zhihu.com"
    SITE_DOMAIN = "zhihu.com"

    @property
    def name(self) -> str:
        return "知乎"

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
            ".RichContent-inner",
            ".Post-RichTextContainer",
            ".QuestionAnswers-answers .RichContent",
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
        for el in soup.select(".TopicLink, .Tag-content"):
            tag = el.get_text(strip=True)
            if tag:
                tags.append(tag)
        return tags
