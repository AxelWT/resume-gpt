"""
爬虫注册表

集中管理所有可用的面经爬虫，提供统一的注册和查询接口。
"""

from scraper.base import BaseCrawler
from scraper.nowcoder import NowCrawler
from scraper.job51 import Job51Crawler
from scraper.zhaopin import ZhaopinCrawler
from scraper.liepin import LiepinCrawler

# 爬虫注册表：key 为来源标识，value 为名称和爬虫类
CRAWLERS: dict[str, dict] = {
    "nowcoder": {"name": "牛客网", "class": NowCrawler},
    "job51": {"name": "前程无忧", "class": Job51Crawler},
    "zhaopin": {"name": "智联招聘", "class": ZhaopinCrawler},
    "liepin": {"name": "猎聘", "class": LiepinCrawler},
}


def get_crawler(source: str) -> BaseCrawler:
    """根据来源标识创建爬虫实例"""
    entry = CRAWLERS.get(source)
    if not entry:
        raise ValueError(f"未知来源: {source}")
    return entry["class"]()


def get_sources() -> list[dict]:
    """返回所有可用来源列表"""
    return [{"key": k, "name": v["name"]} for k, v in CRAWLERS.items()]
