"""
前程无忧岗位描述爬虫模块

从前程无忧搜索岗位招聘信息，获取职位描述、工作职责等。
使用 httpx + BeautifulSoup 直接爬取，失败时降级到 Tavily 搜索。
"""

from bs4 import BeautifulSoup

from scraper.base import BaseCrawler


class Job51Crawler(BaseCrawler):
    """前程无忧岗位描述异步爬虫。"""

    BASE_URL = "https://we.51job.com"
    SITE_DOMAIN = "51job.com"
    EXTRA_KEYWORDS = "招聘 岗位"

    @property
    def name(self) -> str:
        return "前程无忧"

    async def _search_direct(self, query: str, max_count: int = 10) -> list[dict]:
        search_url = f"{self.BASE_URL}/pc/search?keyword={query}&searchType=2"
        try:
            resp = await self.client.get(search_url)
            resp.raise_for_status()
        except Exception:
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        results = []
        for item in soup.select(".joblist, .job-card, .search-job-item"):
            link = item.select_one("a[href], .job-name a, .jname a, .title a")
            if not link:
                continue
            href = link.get("href", "")
            title = link.get_text(strip=True)
            if not href or not title or len(title) < 3:
                continue
            if href.startswith("/"):
                href = f"{self.BASE_URL}{href}"
            if self.SITE_DOMAIN not in href and not href.startswith("http"):
                href = f"{self.BASE_URL}{href}"
            results.append({"title": title, "url": href})
            if len(results) >= max_count:
                break
        return results

    def _parse_content(self, soup: BeautifulSoup) -> str:
        for selector in [
            ".job-detail",
            ".job-desc",
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
        for el in soup.select(".tag, .label, .job-label span, .cate a"):
            tag = el.get_text(strip=True)
            if tag and len(tag) < 20:
                tags.append(tag)
        return tags[:5]
