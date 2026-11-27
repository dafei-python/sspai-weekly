# sspai-weekly

自用的多个 RSS 订阅源。GitHub Actions 每天北京时间 08:30 / 20:30 生成并提交，经 GitHub Pages 发布，jsDelivr 作为备用线路。

| 订阅源 | 主地址（Pages） | 备用（jsDelivr） |
| --- | --- | --- |
| 少数派 · 本周看什么 | https://dafei-python.github.io/sspai-weekly/feed.xml | https://fastly.jsdelivr.net/gh/dafei-python/sspai-weekly@main/feed.xml |
| 喷嚏图卦 | https://dafei-python.github.io/sspai-weekly/dapenti-tugua.xml | https://fastly.jsdelivr.net/gh/dafei-python/sspai-weekly@main/dapenti-tugua.xml |
| iDaily · 每日环球视野 | https://dafei-python.github.io/sspai-weekly/idaily.xml | https://fastly.jsdelivr.net/gh/dafei-python/sspai-weekly@main/idaily.xml |

## 数据来源

- 少数派：标签接口 `sspai.com/api/v1/article/tag/page/get` + 整站 feed 兜底，按标题前缀过滤。
- 喷嚏图卦：`dapenti.com/blog/member-search/api.asp?channel=tugua` 列表 + 文章页正文。
- iDaily：`idaily-cdn.idailycdn.com/api/list/v3/iphone/zh-hans`；图床对非浏览器 UA 防盗链，默认经 wsrv.nl 输出 1600px 图片。

## 本地生成

```bash
python3 sspai_weekly_feed.py feed.xml
python3 dapenti_tugua_feed.py dapenti-tugua.xml
python3 idaily_feed.py idaily.xml
```

单个源失败时脚本返回非零且不覆盖旧文件，工作流里两个新增源也设了 `continue-on-error`，互不影响。