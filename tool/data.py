"""Dagcandles ophalen via de publieke Bitvavo-API (geen account nodig)."""
import time
import requests

from .config import DAY_MS

API = "https://api.bitvavo.com/v2"
HEADERS = {"User-Agent": "crypto-alerts/1.0"}


def _get(url, params, tries=4):
    for k in range(tries):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=30)
            if r.status_code == 200:
                return r.json()
            err = f"HTTP {r.status_code}: {r.text[:200]}"
        except requests.RequestException as e:
            err = str(e)
        time.sleep(3 * (k + 1))
    raise RuntimeError(f"Bitvavo-API onbereikbaar ({url}): {err}")


def fetch_daily(market, since_ms, now_ms=None):
    """Alle dagcandles vanaf since_ms. Geeft (afgesloten candles, lopende candle of None)."""
    now_ms = now_ms or int(time.time() * 1000)
    rows, end = {}, now_ms
    while True:
        batch = _get(f"{API}/{market}/candles", {"interval": "1d", "limit": 1440, "end": end})
        if not batch:
            break
        for k in batch:
            rows[int(k[0])] = k
        oldest = min(int(k[0]) for k in batch)
        if oldest <= since_ms or len(batch) < 1440:
            break
        end = oldest - 1
    candles = [
        {"t": t, "h": float(k[2]), "l": float(k[3]), "c": float(k[4]),
         "v": float(k[5]) * float(k[4])}  # volume in EUR
        for t, k in sorted(rows.items()) if t >= since_ms
    ]
    closed = [x for x in candles if x["t"] + DAY_MS <= now_ms]
    live = candles[-1] if candles and candles[-1]["t"] + DAY_MS > now_ms else None
    return closed, live
