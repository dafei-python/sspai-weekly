#!/usr/bin/env python3
"""生成只包含少数派「本周看什么」栏目的 RSS feed。

数据来源：少数派站点公开接口 https://sspai.com/api/v1/article/tag/page/get
筛选逻辑：标签为「本周看什么」且标题以「本周看什么」开头（排除同标签下的
「看什么·特别篇」等关联但不属于该栏目的文章）。

用法：
    python3 sspai_weekly_feed.py            # 输出 feed.xml
    python3 sspai_weekly_feed.py out.xml    # 指定输出文件
"""

import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.sax.saxutils import escape

CST = timezone(timedelta(hours=8))


def rfc822(ts: int) -> str:
    """按北京时间输出 RFC 822 时间（少数派原始 feed 同样是 +0800）。"""
    return datetime.fromtimestamp(int(ts), CST).strftime("%a, %d %b %Y %H:%M:%S +0800")


TAG = "本周看什么"
TITLE_PREFIX = "本周看什么"
API = "https://sspai.com/api/v1/article/tag/page/get"
SITE_FEED = "https://sspai.com/feed"
SITE = "https://sspai.com"
CDN = "https://cdnfile.sspai.com"
LIMIT = 30          # feed 中保留的最新条数
PAGE_SIZE = 50
MAX_PAGES = 3
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) sspai-weekly-feed/1.0"


def get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def fetch_tagged() -> list[dict]:
    articles: list[dict] = []
    tag = urllib.parse.quote(TAG)
    for page in range(MAX_PAGES):
        url = f"{API}?tag={tag}&limit={PAGE_SIZE}&offset={page * PAGE_SIZE}&created_at=0"
        payload = json.loads(get(url))
        batch = payload.get("data") or []
        articles.extend(batch)
        if not batch:
            break
        time.sleep(0.5)
    return articles


def fetch_site_feed() -> list[dict]:
    """整站 RSS 作为兜底：某些文章可能漏打标签，但标题仍能对上。"""
    raw = get(SITE_FEED).decode("utf-8", "replace")
    out = []
    for block in re.findall(r"<item>.*?</item>", raw, re.S):
        def field(name):
            m = re.search(rf"<{name}>(.*?)</{name}>", block, re.S)
            return m.group(1) if m else ""

        link = field("link").strip()
        title = field("title").strip()
        date = field("pubDate").strip()
        if not link or not title:
            continue
        # 少数派部分文章用 slug 而非数字 id（如 /post/xxx-macos-27-3），跳过这类
        m = re.search(r"/post/(\d+)", link)
        if not m:
            continue
        try:
            ts = int(time.mktime(time.strptime(date, "%a, %d %b %Y %H:%M:%S %z")))
        except (ValueError, OverflowError):
            ts = 0
        out.append({"id": int(m.group(1)), "title": title,
                    "released_time": ts, "summary": re.sub(r"<[^>]+>", "", field("description")),
                    "banner": ""})
    return out


def is_target(title: str) -> bool:
    return title.strip().startswith(TITLE_PREFIX)


def normalize(articles: list[dict]) -> list[dict]:
    seen: dict[int, dict] = {}
    for a in articles:
        if not a.get("id") or not a.get("title"):
            continue
        if not is_target(a["title"]):
            continue
        aid = int(a["id"])
        if aid in seen and seen[aid].get("summary"):
            continue
        seen[aid] = a
    return sorted(seen.values(), key=lambda x: int(x.get("released_time") or 0), reverse=True)[:LIMIT]


def build_rss(articles: list[dict], self_url: str = "") -> str:
    newest = int(articles[0].get("released_time") or time.time()) if articles else int(time.time())
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">',
        "<channel>",
        "<title>少数派 · 本周看什么</title>",
        f"<link>{SITE}</link>",
    ]
    if self_url:
        parts.append(f'<atom:link href="{escape(self_url)}" rel="self" type="application/rss+xml"/>')
    parts += [
        "<description>少数派「本周看什么」栏目更新（只包含该栏目，其余内容已过滤）</description>",
        "<language>zh-CN</language>",
        f"<lastBuildDate>{rfc822(newest)}</lastBuildDate>",
        "<ttl>60</ttl>",
    ]
    for a in articles:
        link = f"{SITE}/post/{a['id']}"
        summary = (a.get("summary") or "").strip()
        banner = (a.get("banner") or "").strip()
        html = f"<p>{escape(summary)}</p>"
        if banner:
            img = banner if banner.startswith("http") else f"{CDN}/{banner.lstrip('/')}"
            html = f'<p><img src="{escape(img)}" alt=""/></p>' + html
        parts += [
            "<item>",
            f"<title>{escape(a['title'])}</title>",
            f"<link>{escape(link)}</link>",
            f'<guid isPermaLink="true">{escape(link)}</guid>',
            f"<pubDate>{rfc822(a.get('released_time') or 0)}</pubDate>",
            f"<description>{escape(html)}</description>",
            "</item>",
        ]
    parts += ["</channel>", "</rss>", ""]
    return "\n".join(parts)


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "feed.xml")
    self_url = os.environ.get("FEED_URL", "").strip()
    try:
        articles = fetch_tagged()
    except Exception as exc:  # 主数据源失败时保留旧 feed，不覆盖
        print(f"抓取失败：{exc}", file=sys.stderr)
        return 1
    try:
        articles += fetch_site_feed()  # 兜底源，失败不影响主流程
    except Exception as exc:
        print(f"整站 feed 兜底失败，已忽略：{exc}", file=sys.stderr)
    articles = normalize(articles)
    if not articles:
        print("未匹配到任何条目，保留旧 feed", file=sys.stderr)
        return 2
    out.write_text(build_rss(articles, self_url), encoding="utf-8")
    print(f"已写入 {out}，共 {len(articles)} 条；最新：{articles[0]['title']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
