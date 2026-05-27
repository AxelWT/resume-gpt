"""
前程无忧岗位描述爬虫模块

从前程无忧搜索岗位招聘信息，获取职位描述、工作职责等。
优先使用 Scrapling StealthyFetcher 直接爬取搜索页（JS渲染），
失败时降级到 Bing 搜索中转，详情页同样支持 StealthyFetcher + httpx 降级。
"""

from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from scraper.base import ScraplingBaseCrawler


class Job51Crawler(ScraplingBaseCrawler):
    """前程无忧岗位描述异步爬虫，基于 Scrapling StealthyFetcher。"""

    BASE_URL = "https://we.51job.com"
    SITE_DOMAIN = "51job.com"
    EXTRA_KEYWORDS = "招聘 岗位"

    @property
    def name(self) -> str:
        return "前程无忧"

    async def _search_direct(self, query: str, max_count: int = 10) -> list[dict]:
        search_url = f"{self.BASE_URL}/pc/search?keyword={query}&searchType=2"
        page = await self._fetch_stealthy(search_url)

        results = []
        for item in page.css(".joblist, .job-card, .search-job-item"):
            link = item.css("a[href], .job-name a, .jname a, .title a").first
            if not link:
                continue
            href = link.attrib.get("href", "")
            title = link.text.strip()
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

    def _parse_content_from_page(self, page) -> str:
        for selector in [
            ".job-detail",
            ".job-desc",
            ".detail-content",
            ".content",
            "article",
        ]:
            el = page.css(selector).first
            if el:
                text = el.text.strip()
                if len(text) > 20:
                    return text[:5000]
        body = page.css("body").first
        return body.text.strip()[:5000] if body else ""

    def _parse_tags_from_page(self, page) -> list[str]:
        tags = []
        for el in page.css(".tag, .label, .job-label span, .cate a"):
            tag = el.text.strip()
            if tag and len(tag) < 20:
                tags.append(tag)
        return tags[:5]

    def _parse_content_fallback(self, soup: BeautifulSoup) -> str:
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

    def _parse_tags_fallback(self, soup: BeautifulSoup) -> list[str]:
        tags = []
        for el in soup.select(".tag, .label, .job-label span, .cate a"):
            tag = el.get_text(strip=True)
            if tag and len(tag) < 20:
                tags.append(tag)
        return tags[:5]
