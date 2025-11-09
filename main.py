import os
from datetime import datetime, timezone
from typing import List

import requests
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Stocks API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

POPULAR_SYMBOLS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "NFLX", "AMD", "INTC",
    "BRK-B", "V", "JPM", "UNH", "PG", "XOM", "KO", "PEP", "ADBE", "CRM"
]

YF_QUOTE_URL = "https://query1.finance.yahoo.com/v7/finance/quote"
YF_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"


def _iso_from_epoch(sec: float) -> str:
    dt = datetime.fromtimestamp(sec, tz=timezone.utc)
    return dt.isoformat()


@app.get("/")
def read_root():
    return {"message": "Stocks API is running"}


@app.get("/api/stocks/popular")
def get_popular() -> List[str]:
    return POPULAR_SYMBOLS


@app.get("/api/stocks/quote")
def get_quote(symbol: str = Query(..., description="Ticker symbol, e.g. AAPL")):
    sym = symbol.upper().strip()
    try:
        r = requests.get(YF_QUOTE_URL, params={"symbols": sym}, timeout=10)
        if r.status_code != 200:
            raise HTTPException(status_code=502, detail="Upstream quote service error")
        data = r.json()
        res = (data or {}).get("quoteResponse", {}).get("result", [])
        if not res:
            raise HTTPException(status_code=404, detail="Symbol not found")
        q = res[0]
        price = q.get("regularMarketPrice")
        change = q.get("regularMarketChange")
        change_percent = q.get("regularMarketChangePercent")
        open_price = q.get("regularMarketOpen")
        day_high = q.get("regularMarketDayHigh")
        day_low = q.get("regularMarketDayLow")
        ts = q.get("regularMarketTime")
        currency = q.get("currency")
        exchange = q.get("fullExchangeName") or q.get("exchange")
        name = q.get("shortName") or q.get("longName") or sym
        return {
            "symbol": sym,
            "price": price,
            "change": change,
            "change_percent": change_percent,
            "open": open_price,
            "high": day_high,
            "low": day_low,
            "as_of": _iso_from_epoch(ts) if ts else None,
            "currency": currency,
            "exchange": exchange,
            "name": name,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:200])


@app.get("/api/stocks/intraday")
def intraday(
    symbol: str = Query(...),
    interval: str = Query("5m", pattern="^(1m|2m|5m|15m|30m|60m|90m)$")
):
    sym = symbol.upper().strip()
    try:
        params = {"range": "1d", "interval": interval, "includePrePost": "true"}
        r = requests.get(YF_CHART_URL.format(symbol=sym), params=params, timeout=10)
        if r.status_code != 200:
            raise HTTPException(status_code=502, detail="Upstream chart service error")
        data = r.json()
        result = (data or {}).get("chart", {}).get("result", [])
        if not result:
            raise HTTPException(status_code=404, detail="No intraday data found")
        series = result[0]
        timestamps = series.get("timestamp", []) or []
        indicators = series.get("indicators", {})
        quotes = (indicators.get("quote", []) or [{}])[0]
        opens = quotes.get("open", [])
        highs = quotes.get("high", [])
        lows = quotes.get("low", [])
        closes = quotes.get("close", [])
        volumes = quotes.get("volume", [])
        points = []
        for i, t in enumerate(timestamps):
            # some entries can be None during pre/post market; skip invalids
            try:
                o = opens[i]
                h = highs[i]
                l = lows[i]
                c = closes[i]
                v = volumes[i] if i < len(volumes) else 0
                if None in (o, h, l, c):
                    continue
                points.append({
                    "t": _iso_from_epoch(t),
                    "o": float(o),
                    "h": float(h),
                    "l": float(l),
                    "c": float(c),
                    "v": float(v or 0),
                })
            except Exception:
                continue
        return {"symbol": sym, "interval": interval, "points": points}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:200])


@app.get("/api/hello")
def hello():
    return {"message": "Hello from the backend API!"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Used",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }

    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"

    return response


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
