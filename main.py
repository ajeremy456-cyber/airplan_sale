# main.py
import logging
from datetime import datetime
from typing import List
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from scrapers import (
    get_peach_promotions,
    get_tigerair_promotions,
    get_china_airlines,  # 新增
    get_starlux_promotions,
    get_tway_promotions,
    Promotion,
    ScrapingError,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("promo_scraper")

app = FastAPI(title="促銷機票彙總 API", version="1.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/promotions")
def list_promotions():
    all_promotions = []

    # ── 樂桃航空 ──
    try:
        all_promotions.extend(get_peach_promotions())
    except ScrapingError as e:
        logger.error(f"[{e.source}] 發生錯誤: {e}")

    # ── 台灣虎航 ──
    try:
        all_promotions.extend(get_tigerair_promotions())
    except ScrapingError as e:
        logger.error(f"[{e.source}] 發生錯誤: {e}")

    # ── 中華航空 ──
    try:
        all_promotions.extend(get_china_airlines())
    except Exception as e:
        logger.error(f"[ChinaAir] 發生錯誤: {e}", exc_info=True)
     # ── 星宇航空 ──
    try:
        all_promotions.extend(get_starlux_promotions())
    except Exception as e:
        logger.error(f"[ChinaAir] 發生錯誤: {e}", exc_info=True)
     # ── 德威航空 ──
    try:
        all_promotions.extend(get_tway_promotions())
    except Exception as e:
        logger.error(f"[ChinaAir] 發生錯誤: {e}", exc_info=True)
    # ── 關鍵字篩選 ──
    allowed_keywords = ["促銷", "販售", "優惠", "特價", "限時", "台北", "高雄", "→", "起","早鳥"]
    filtered_promotions = [
        p for p in all_promotions
        if any(kw in p.title for kw in allowed_keywords)
    ]

    if not filtered_promotions:
        return JSONResponse(
            status_code=502,
            content={"error": "無促銷資料", "message": "目前沒有任何符合關鍵字的促銷活動。"}
        )

    return filtered_promotions

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)