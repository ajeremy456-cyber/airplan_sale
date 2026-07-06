# scrapers.py
import logging
from datetime import datetime
from typing import List, Optional
from curl_cffi import requests as curl_requests
from bs4 import BeautifulSoup
from pydantic import BaseModel
import requests
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
#華航新增的套件
import re
from typing import List                                 


logger = logging.getLogger("promo_scraper")

# ─── 資料結構與設定 ─────────────────────────────────────────
class Promotion(BaseModel):
    airline: str
    title: str
    image_url: Optional[str] = None
    origin: str
    destination: str
    price: Optional[int] = None
    currency: str = "TWD"
    travel_period: str = "不明"
    booking_period: str = "不明"
    url: str
    updated_at: str

class ScrapingError(RuntimeError):
    def __init__(self, message: str, source: str):
        super().__init__(message)
        self.source = source

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
    "Cookie": "language=zh-TW; country=TW;"
}

# ─── 樂桃航空爬蟲 (完整強化版) ──────────────────────────────
def get_peach_promotions() -> List[Promotion]:
    try:
        resp = requests.get("https://www.flypeach.com/tw/", headers=DEFAULT_HEADERS, timeout=30)
        resp.raise_for_status()
        
        soup = BeautifulSoup(resp.text, "html.parser")
        now = datetime.now().isoformat(timespec="seconds")
        results: List[Promotion] = []

        # 完整的多層防護選取器
        cards = soup.select("a[id*='banner'], a[class*='banner'], ul.promo-list li a, .campaign-list a, .promotion-list a")
        if not cards:
            cards = [a for a in soup.find_all("a", href=True) if "promotions" in a["href"] or "/lm/st/" in a["href"]]

        seen_urls = set()
        
        for a in cards[:20]:
            href = a.get("href", "")
            if not href or href in seen_urls: continue
            seen_urls.add(href)

            # 網址補全
            full_url = "https://www.flypeach.com" + href if href.startswith("/") else ("https://www.flypeach.com/" + href if not href.startswith("http") else href)

            title = a.get_text(strip=True)
            image_url = None
            img_tag = a.find("img")
            
            # 圖片與無文字標題處理
            if img_tag:
                if not title and img_tag.get("alt"): 
                    title = img_tag.get("alt").strip()
                
                raw_src = img_tag.get("src")
                if raw_src:
                    image_url = "https://www.flypeach.com" + raw_src if raw_src.startswith("/") else ("https://www.flypeach.com/" + raw_src if not raw_src.startswith("http") else raw_src)

            # 過濾無意義公告與過短標題
            title_lower = (title or "").lower()
            if any(bad in title_lower for bad in ["brand", "renewal", "品牌"]):
                continue

            if not title or len(title) < 5: 
                continue

            results.append(Promotion(
                airline="樂桃航空", title=title, image_url=image_url,
                origin="台北 (TPE)", destination="請至官網確認",
                url=full_url, updated_at=now
            ))
            
        logger.info(f"[Peach] 解析出 {len(results)} 筆潛在資料")
        return results
    except Exception as e:
        raise ScrapingError(f"樂桃航空爬取失敗: {str(e)}", source="Peach Aviation")

#虎航抓banner標題
def fetch_page_title(url: str, headers: dict) -> str:
    """從活動頁面抓 og:title 或 <title>"""
    try:
        resp = curl_requests.get(url, headers=headers, impersonate="chrome", timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")

        # 優先抓 og:title
        og = soup.find("meta", property="og:title")
        if og and og.get("content"):
            return og["content"].strip()

        # fallback 抓 <title>
        if soup.title and soup.title.string:
            return soup.title.string.strip()

    except Exception as e:
        logger.warning(f"⚠️ 抓標題失敗 {url}: {e}")

    return ""
#虎航爬蟲
def get_tigerair_promotions() -> List[Promotion]:
    """台灣虎航爬蟲 - Banner 大圖 + 並行抓標題"""
    try:
        logger.info("🚀 [Tigerair] 抓取首頁 Banner！")

        banner_api = (
            "https://api-cms.tigerairtw.com/api/home-banners"
            "?language=zh-TW&perPage=100"
        )
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            "Referer": "https://www.tigerairtw.com/",
            "Origin": "https://www.tigerairtw.com",
            "Accept": "application/json",
        }

        resp = curl_requests.get(banner_api, headers=headers, impersonate="chrome", timeout=15)
        logger.info(f"🌐 [Tigerair] API 狀態碼: {resp.status_code}")
        resp.raise_for_status()

        root = resp.json()
        banners = root.get("data", {}).get("homeBanners", {}).get("data", [])
        now = datetime.now().isoformat(timespec="seconds")

        # ── 先整理每個 banner 的基本資料 ──
        items = []
        for item in banners:
            attr = item.get("attributes", {})
            link = (
                attr.get("linkTo", {}).get("url")
                or "https://www.tigerairtw.com/zh-TW"
            )
            image_url = ""
            try:
                image_url = attr["banner"]["desktop"]["data"]["attributes"]["url"]
            except (KeyError, TypeError):
                pass
            if not image_url:
                try:
                    image_url = attr["banner"]["mobile"]["data"]["attributes"]["url"]
                except (KeyError, TypeError):
                    pass
            if not image_url:
                continue

            items.append({"link": link, "image_url": image_url})

        # ── 並行抓所有標題 ──
        def fetch_title(item):
            link = item["link"]
            title = ""
            if "static.tigerairtw.com" in link:
                title = fetch_page_title(link, headers)
            #if not title:
            #   title = "台灣虎航限時優惠"
            return {**item, "title": title}

        results = []
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(fetch_title, item): item for item in items}
            for future in as_completed(futures):
                try:
                    data = future.result()
                    results.append(Promotion(
                        airline="台灣虎航",
                        title=data["title"],
                        image_url=data["image_url"],
                        origin="台北 (TPE) / 高雄 (KHH)",
                        destination="請至官網確認",
                        url=data["link"],
                        updated_at=now,
                    ))
                except Exception as e:
                    logger.warning(f"⚠️ 處理 banner 失敗: {e}")

        logger.info(f"🎉 [Tigerair] 成功抓取 {len(results)} 筆 Banner！")
        return results

    except Exception as e:
        logger.error(f"❌ [Tigerair] API 抓取失敗: {e}", exc_info=True)
        return []
#中華航空爬蟲
def get_china_airlines() -> List[Promotion]:
    """中華航空爬蟲 - 首頁 Banner 圖片 + 標題 + 連結"""
    try:
        logger.info("🚀 [ChinaAir] 抓取首頁 Banner！")
        now = datetime.now().isoformat(timespec="seconds")
        #scraper是掛proxy才不會被鎖
        SCRAPER_API_KEY = "7f2117c29185e08934e7e9a77c0facd1"  # ← 填入重新產生的 Key
        resp = curl_requests.get(
            "https://api.scraperapi.com/",
        params={
            "api_key": SCRAPER_API_KEY,
            "url": "https://www.china-airlines.com/tw/zh",
            "country_code": "tw",
        },
        timeout=60  # ScraperAPI 比較慢，timeout 要拉長
    )
        resp.raise_for_status()
        html = resp.text

        # 用跳脫過的 linkedData 區塊分隔
        blocks = html.split('linkedData\\":{\\"$type\\":\\"Fields\\",\\"title\\":\\"')[1:]

        results: List[Promotion] = []
        seen: set = set()

        for block in blocks:
            title_match = re.match(r'^([^\\]*)\\\"', block)
            title = title_match.group(1) if title_match else ""

            # 排除非促銷區塊（網站地圖、服務項目等）
            if not title or title in seen:
                continue

            img_match = re.search(r'\\"url\\":\\"([^\\]*?\.(?:png|jpg|jpeg|webp))\\"', block[:3000])
            image = img_match.group(1) if img_match else ""

            link_match = re.search(r'\\"externalLink\\":\\"([^\\]*)\\"', block[:3000])
            link = link_match.group(1) if link_match else ""

            # 沒有圖片就跳過（代表不是真正的 banner）
            if not image:
                continue

            seen.add(title)

            # 補齊圖片網址
            image_url = image.replace("%20", " ")
            if image_url.startswith("/"):
                image_url = "https://prd-api.china-airlines.com" + image_url
            image_url = image_url.replace(" ", "%20")

            # 沒有外部連結就用首頁
            if not link:
                link = "https://www.china-airlines.com/tw/zh"

            results.append(Promotion(
                airline="中華航空",
                title=title,
                image_url=image_url,
                origin="台北 (TPE)",
                destination="請至官網確認",
                url=link,
                updated_at=now,
            ))

        logger.info(f"🎉 [ChinaAir] 成功抓取 {len(results)} 筆 Banner！")
        return results

    except Exception as e:
        logger.error(f"❌ [ChinaAir] 抓取失敗: {e}", exc_info=True)
        return []

def get_starlux_promotions() -> List[Promotion]:
    """星宇航空爬蟲 - 首頁促銷"""
    try:
        logger.info("🚀 [Starlux] 抓取首頁促銷！")

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
        resp.raise_for_status()
        html = resp.text

        blocks = html.split('Headline:"')[1:]
        now = datetime.now().isoformat(timespec="seconds")
        results: List[Promotion] = []
        seen: set = set()

        skip_domains = ["facebook", "instagram", "twitter", "youtube", "apple", "google", "starluxcargo", "apps.apple"]
        skip_titles = ["相關網站", "追蹤", "我們的手機服務", "星宇推薦"]

        for block in blocks:
            title_match = re.match(r'^([^"]*)"', block)
            title = title_match.group(1) if title_match else ""

            link_match = re.search(r'Url:"(https:\\u002F\\u002F[^"]*)"', block[:1000])
            link = link_match.group(1).replace("\\u002F", "/") if link_match else ""

            img_match = re.search(r'Url:"(\\u002Fzh-TW\\u002FImages\\u002F[^"]*)"', block[:1000])
            image = "https://webassets2.starlux-airlines.com" + img_match.group(1).replace("\\u002F", "/") if img_match else ""

            if not title or not link or not image:
                continue
            if title in skip_titles:
                continue
            if any(d in link for d in skip_domains):
                continue
            if len(title) < 5:
                continue
            if title in seen:
                continue
            seen.add(title)

            results.append(Promotion(
                airline="星宇航空",
                title=title,
                image_url=image,
                origin="台北 (TPE)",
                destination="請至官網確認",
                url=link,
                updated_at=now,
            ))

        logger.info(f"🎉 [Starlux] 成功抓取 {len(results)} 筆促銷！")
        return results

    except Exception as e:
        logger.error(f"❌ [Starlux] 抓取失敗: {e}", exc_info=True)
        return []