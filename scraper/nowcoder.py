import asyncio
import re
import time
from typing import Optional

import httpx
from bs4 import BeautifulSoup


class NowCrawler:
    BASE_URL = "https://www.nowcoder.com"
    SEARCH_URL = f"{BASE_URL}/search"

    def __init__(self, timeout: int = 30, delay: float = 0.5):
        self.client = httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            },
        )
        self.delay = delay

    async def search(self, query: str, max_count: int = 10) -> list[dict]:
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
            except Exception as e:
                break

            soup = BeautifulSoup(resp.text, "lxml")
            items = self._parse_search_results(soup)
            if not items:
                break

            results.extend(items)
            page += 1
            await asyncio.sleep(self.delay)

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

    async def fetch_content(self, url: str) -> dict:
        try:
            resp = await self.client.get(url)
            resp.raise_for_status()
        except Exception as e:
            return {"content": "", "tags": []}

        soup = BeautifulSoup(resp.text, "lxml")
        content = self._parse_content(soup)
        tags = self._parse_tags(soup)

        await asyncio.sleep(self.delay)
        return {"content": content, "tags": tags}

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

    async def close(self):
        await self.client.aclose()
