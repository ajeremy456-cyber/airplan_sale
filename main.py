# main.py
import logging
from datetime import datetime
from typing import List
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# ✨ 關鍵：從我們剛建好的 scrapers 模組匯入爬蟲函數與資料 Model
from scrapers import get_peach_promotions, get_tigerair_promotions, Promotion, ScrapingError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("promo_scraper")

app = FastAPI(title="促銷機票彙總 API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/promotions")
def list_promotions(demo: bool = Query(False)):
    if demo:
        return _get_mock_promotions()

    all_promotions = []

    # 1. 分別呼叫不同航空公司的爬蟲模組，互不干擾
    try:
        all_promotions.extend(get_peach_promotions())
    except ScrapingError as e:
        logger.error(f"[{e.source}] 發生錯誤: {e}")

    try:
        all_promotions.extend(get_tigerair_promotions())
    except ScrapingError as e:
        logger.error(f"[{e.source}] 發生錯誤: {e}")

    # 2. 在 API 出貨前，進行統一的後端關鍵字篩選
    allowed_keywords = ["促銷", "販售", "優惠", "特價", "限時","台北","高雄"] 
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

def _get_mock_promotions() -> List[Promotion]:
    return [
        Promotion(
            airline="樂桃航空", title="🎉 台北–東京 冬季優惠", 
            image_url="https://www.flypeach.com/application/files/dummy_image.png", 
            origin="台北 (TPE)", destination="東京 (NRT)", 
            url="https://www.flypeach.com/tw/", updated_at=datetime.now().isoformat()
        )
    ]

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)