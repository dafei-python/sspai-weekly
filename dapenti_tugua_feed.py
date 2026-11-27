#!/usr/bin/env python3
"""生成「喷嚏图卦」RSS feed。

列表：喷嚏网频道检索接口
    https://www.dapenti.com/blog/member-search/api.asp?channel=tugua
正文：逐条抓取 more-new-v5.asp 文章页（gb2312 编码），提取
    <article id="article-content">，并去掉正文前的免责声明。

用法：
    python3 dapenti_tugua_feed.py                 # 输出 dapenti-tugua.xml
    python3 dapenti_tugua_feed.py out.xml         # 指定输出文件
"""

from __future__ import annotations

import html
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
SITE = "https://www.dapenti.com"

API = f"{SITE}/blog/member-search/api.asp?channel=tugua&sort=newest&cursor=0&limit=30"
LIST_FALLBACK = f"{SITE}/blog/blog-responsive-new.asp?name=xilei&subjectid=70"
CHANNEL_LINK = f"{SITE}/blog/member-channel.asp?channel=tugua"

LIMIT = 20
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
}


def rfc822(dt: datetime) -> str:
    return dt.strftime("%a, %d %b %Y %H:%M:%S +0800")


def parse_cst(text: str) -> datetime | None:
    m = re.search(r"(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}:\d{2})", text or "")
    if not m:
        return None
    try:
        return datetime.strptime(f"{m.group(1)} {m.group(2)}", "%Y-%m-%d %H:%M:%S").replace(tzinfo=CST)
    except ValueError:
        return None


def get(url: str, timeout: int = 40) -> bytes:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def fetch_list() -> list[dict]:
    try:
        payload = json.loads(get(API))
        hits = payload.get("hits") or []
        items = []
        for hit in hits:
            link = str(hit.get("source_url") or "")
            if not link:
                continue
            items.append(
                {
                    "id": int(hit.get("id") or 0),
                    "title": html.unescape(str(hit.get("topic") or "")).strip(),
                    "link": urllib.parse.urljoin(SITE + "/", link.lstrip("/")),
                    "date": parse_cst(str(hit.get("addtime") or "")),
                    "snippet": str(hit.get("snippet") or "").strip(),
                }
            )
        if items:
            return items
    except Exception as exc:
        print(f"检索接口失败，改用列表页：{exc}", file=sys.stderr)

    page = get(LIST_FALLBACK).decode("gb18030", "replace")
    items, seen = [], set()
    for m in re.finditer(
        r'<a\s+href=["\']?more-new-v5\.asp\?name=xilei&(?:amp;)?id=(\d+)[^>]*>(.*?)</a>',
        page,
        re.S | re.I,
    ):
        aid = int(m.group(1))
        if aid in seen:
            continue
        seen.add(aid)
        title = html.unescape(re.sub(r"<[^>]+>", "", m.group(2))).strip()
        if not title:
            continue
        items.append(
            {
                "id": aid,
                "title": title,
                "link": f"{SITE}/blog/more-new-v5.asp?name=xilei&id={aid}",
                "date": None,
                "snippet": "",
            }
        )
    return items[:40]


def extract_article(page: str) -> tuple[str, datetime | None]:
    published = None
    m = re.search(r"发布于\s*(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", page)
    if m:
        published = parse_cst(m.group(1))

    body = re.search(r'<article id="article-content"[^>]*>(.*?)</article>', page, re.S)
    if not body:
        return "", published
    content = body.group(1)
    content = re.sub(r"<script\b.*?</script>", "", content, flags=re.S | re.I)
    content = re.sub(r"<ins\b.*?</ins>", "", content, flags=re.S | re.I)

    # 去掉正文前的免责声明，从「每天一图卦」所在段落开始
    marker = content.find("每天一图卦")
    if marker > 0:
        start = content.rfind("<p", 0, marker)
        if start > 0:
            content = content[start:]

    content = re.sub(r'(href|src)="/(?!/)', rf'\1="{SITE}/', content)
    return content.strip(), published


def fetch_article(item: dict) -> tuple[str, datetime | None]:
    try:
        page = get(item["link"]).decode("gb18030", "replace")
        return extract_article(page)
    except Exception as exc:
        print(f"正文抓取失败 {item['link']}：{exc}", file=sys.stderr)
        return "", None


def build_rss(items: list[dict], self_url: str = "") -> str:
    newest = items[0]["date"] if items and items[0].get("date") else datetime.now(CST)
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">',
        "<channel>",
        "<title>喷嚏图卦</title>",
        f"<link>{CHANNEL_LINK}</link>",
    ]
    if self_url:
        parts.append(f'<atom:link href="{escape(self_url)}" rel="self" type="application/rss+xml"/>')
    parts += [
        "<description>喷嚏网「喷嚏图卦」每日更新</description>",
        "<language>zh-CN</language>",
        f"<lastBuildDate>{rfc822(newest)}</lastBuildDate>",
        "<ttl>60</ttl>",
    ]
    for item in items:
        title = item.get("title") or "喷嚏图卦"
        link = item["link"]
        content = item.get("html") or ""
        if not content:
            snippet = item.get("snippet") or ""
            content = f"<p>{escape(snippet)}</p>" if snippet else ""
        pub = item.get("date")
        parts.append("<item>")
        parts.append(f"<title>{escape(title)}</title>")
        parts.append(f"<link>{escape(link)}</link>")
        parts.append(f'<guid isPermaLink="true">{escape(link)}</guid>')
        if pub:
            parts.append(f"<pubDate>{rfc822(pub)}</pubDate>")
        if content:
            parts.append(f"<description>{escape(content)}</description>")
        parts.append("</item>")
    parts += ["</channel>", "</rss>", ""]
    return "\n".join(parts)


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "dapenti-tugua.xml")
    self_url = os.environ.get("FEED_URL", "").strip()
    try:
        items = fetch_list()
    except Exception as exc:
        print(f"列表抓取失败：{exc}", file=sys.stderr)
        return 1
    if not items:
        print("未找到任何条目，保留旧 feed", file=sys.stderr)
        return 2

    items = items[:LIMIT]
    for item in items:
        content, published = fetch_article(item)
        item["html"] = content
        if published and not item.get("date"):
            item["date"] = published
        time.sleep(0.4)

    dated = [i for i in items if i.get("date")]
    if dated and len(dated) == len(items):
        items.sort(key=lambda x: x["date"], reverse=True)

    out.write_text(build_rss(items, self_url), encoding="utf-8")
    latest = items[0]["title"]
    print(f"已写入 {out}，共 {len(items)} 条；最新：{latest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())