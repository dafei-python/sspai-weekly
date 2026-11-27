#!/usr/bin/env python3
"""生成「iDaily · 每日环球视野」RSS feed。

数据来源：iDaily 官方公开接口
    https://idaily-cdn.idailycdn.com/api/list/v3/iphone/zh-hans
图片：iDaily 图床（yupoo）对非浏览器 UA 有防盗链，默认经 wsrv.nl 代理输出
    1600px JPEG；设置 IDAILY_ORIGINAL_IMG=1 可改用原图地址。

用法：
    python3 idaily_feed.py            # 输出 idaily.xml
    python3 idaily_feed.py out.xml    # 指定输出文件
"""

from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.sax.saxutils import escape

CST = timezone(timedelta(hours=8))
API = "https://idaily-cdn.idailycdn.com/api/list/v3/iphone/zh-hans"
SITE = "https://idai.ly"
LIMIT = 30
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
USE_PROXY = os.environ.get("IDAILY_ORIGINAL_IMG", "") != "1"
PROXY = "https://wsrv.nl/?url={}&w=1600&output=jpg"


def rfc822(dt: datetime) -> str:
    return dt.strftime("%a, %d %b %Y %H:%M:%S +0800")


def get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read()


def image_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    if url.startswith("http://"):
        url = "https://" + url[7:]
    if not USE_PROXY:
        return url
    bare = url.split("://", 1)[-1]
    return PROXY.format(urllib.parse.quote(bare, safe=""))


def build_rss(items: list[dict], self_url: str = "") -> str:
    newest = items[0]["date"] if items else datetime.now(CST)
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">',
        "<channel>",
        "<title>iDaily · 每日环球视野</title>",
        f"<link>{SITE}</link>",
    ]
    if self_url:
        parts.append(f'<atom:link href="{escape(self_url)}" rel="self" type="application/rss+xml"/>')
    parts += [
        "<description>iDaily · 每日环球视野（每日更新）</description>",
        "<language>zh-CN</language>",
        f"<lastBuildDate>{rfc822(newest)}</lastBuildDate>",
        "<ttl>60</ttl>",
    ]
    for item in items:
        parts.append("<item>")
        parts.append(f"<title>{escape(item['title'])}</title>")
        parts.append(f"<link>{escape(item['link'])}</link>")
        parts.append(f"<guid isPermaLink=\"false\">{escape(item['guid'])}</guid>")
        parts.append(f"<pubDate>{rfc822(item['date'])}</pubDate>")
        for tag in item.get("tags") or []:
            parts.append(f"<category>{escape(tag)}</category>")
        parts.append(f"<description>{escape(item['html'])}</description>")
        parts.append("</item>")
    parts += ["</channel>", "</rss>", ""]
    return "\n".join(parts)


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "idaily.xml")
    self_url = os.environ.get("FEED_URL", "").strip()
    try:
        payload = json.loads(get(API))
    except Exception as exc:
        print(f"接口抓取失败：{exc}", file=sys.stderr)
        return 1

    raw = payload if isinstance(payload, list) else payload.get("data") or []
    items = []
    for entry in raw:
        ui = entry.get("ui_sets") or {}
        title = str(ui.get("caption_subtitle") or "").strip()
        link = str(entry.get("link_share") or entry.get("link_wechat") or "").strip()
        if not title or not link:
            continue
        try:
            ts = int(entry.get("pubdate_timestamp") or 0)
        except (TypeError, ValueError):
            ts = 0
        if not ts:
            continue
        img = image_url(
            ui.get("cover_landscape_hd_4k")
            or entry.get("cover_landscape_hd")
            or entry.get("cover_landscape")
            or ""
        )
        body = str(entry.get("content") or "").strip()
        html_parts = []
        if img:
            html_parts.append(f'<figure><img src="{escape(img)}" alt="{escape(title)}"/></figure>')
        if body:
            html_parts.append(f"<p>{escape(body)}</p>")
        html_parts.append(f'<p><a href="{escape(link)}">查看原文</a></p>')
        items.append(
            {
                "title": title,
                "link": link,
                "guid": f"idaily-{entry.get('guid') or ts}",
                "date": datetime.fromtimestamp(ts, CST),
                "html": "".join(html_parts),
                "tags": [t.get("name") for t in entry.get("tags") or [] if t.get("name")],
                "_ts": ts,
            }
        )

    if not items:
        print("接口未返回可用条目，保留旧 feed", file=sys.stderr)
        return 2
    items.sort(key=lambda x: x["_ts"], reverse=True)
    items = items[:LIMIT]
    for item in items:
        item.pop("_ts", None)

    out.write_text(build_rss(items, self_url), encoding="utf-8")
    print(f"已写入 {out}，共 {len(items)} 条；最新：{items[0]['title']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())