"""
智联招聘岗位描述爬虫模块

从智联招聘搜索岗位招聘信息，获取职位描述、工作职责等。
使用 httpx + BeautifulSoup 直接爬取，失败时降级到 Tavily 搜索。
"""

from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from scraper.base import BaseCrawler


class ZhaopinCrawler(BaseCrawler):
    """智联招聘岗位描述异步爬虫。"""

    BASE_URL = "https://www.zhaopin.com"
    SITE_DOMAIN = "zhaopin.com"
    EXTRA_KEYWORDS = "招聘 岗位"

    @property
    def name(self) -> str:
        return "智联招聘"

    async def _search_direct(self, query: str, max_count: int = 10) -> list[dict]:
        search_url = f"{self.BASE_URL}/sou/?kw={quote_plus(query)}"
        try:
            resp = await self.client.get(search_url)
            resp.raise_for_status()
        except Exception:
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        results = []
        for item in soup.select(".search-result-item, .jobinfo, .positionlist-item"):
            link = item.select_one("a[href], .jobinfo__top a, h3 a")
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
            ".job-description",
            ".job-desc",
            ".detail-content",
            ".job-detail",
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
