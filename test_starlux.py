# test_starlux.py
from curl_cffi import requests as curl_requests
import re

resp = curl_requests.get(
    "https://www.starlux-airlines.com/zh-TW",
    headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Referer": "https://www.google.com/",
        "Accept-Language": "zh-TW,zh;q=0.9",
    },
    impersonate="chrome120",
    timeout=15
)

html = resp.text
blocks = html.split('Headline:"')[1:]

# 過濾用的黑名單
skip_domains = ["facebook", "instagram", "twitter", "youtube", "apple", "google", "starluxcargo", "apps.apple"]
skip_titles = ["相關網站", "追蹤", "我們的手機服務", "星宇推薦"]

for block in blocks:
    title_match = re.match(r'^([^"]*)"', block)
    title = title_match.group(1) if title_match else ""

    link_match = re.search(r'Url:"(https:\\u002F\\u002F[^"]*)"', block[:1000])
    link = link_match.group(1).replace("\\u002F", "/") if link_match else ""

    img_match = re.search(r'Url:"(\\u002Fzh-TW\\u002FImages\\u002F[^"]*)"', block[:1000])
    image = "https://webassets2.starlux-airlines.com" + img_match.group(1).replace("\\u002F", "/") if img_match else ""

    # 過濾條件
    if not title or not link or not image:
        continue
    if title in skip_titles:
        continue
    if any(d in link for d in skip_domains):
        continue
    if len(title) < 5:
        continue

    print("─" * 50)
    print("標題:", title)
    print("連結:", link)
    print("圖片:", image)