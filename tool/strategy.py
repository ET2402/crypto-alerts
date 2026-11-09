"""Strategie C + marge: trendregel (200-dagengemiddelde +/-3%) met Wyckoff-exits.

Exacte port van de JS-backtest. Elke run herberekent alles vanaf de startdatum,
zodat gemiste runs automatisch worden ingehaald en er geen drift kan ontstaan.
"""
import math

from . import config as C


def indicators(d):
    n = len(d)
    nan = float("nan")
    atr, va, sma = [nan] * n, [nan] * n, [nan] * n
    tr = [d[0]["h"] - d[0]["l"]] + [
        max(d[i]["h"] - d[i]["l"], abs(d[i]["h"] - d[i - 1]["c"]), abs(d[i]["l"] - d[i - 1]["c"]))
        for i in range(1, n)
    ]
    for i in range(20, n):
        a = 0.0
        for j in range(i - 14, i):
            a += tr[j]
        atr[i] = a / 14
        b = 0.0
        for j in range(i - 20, i):
            b += d[j]["v"]
        va[i] = b / 20
    N = C.SMA_DAYS
    for i in range(N - 1, n):
        s = 0.0
        for j in range(i - N + 1, i + 1):
            s += d[j]["c"]
        sma[i] = s / N
    return atr, va, sma


def simulate(d, start_ms, buf=C.BUFFER, L=C.RANGE_DAYS, K=C.RANGE_MAX_ATR, fee=C.FEE, budget=C.BUDGET):
    """d: afgesloten dagcandles (oplopend). Simuleert vanaf de eerste candle >= start_ms."""
    atr, va, sma = indicators(d)
    s = next((i for i, x in enumerate(d) if x["t"] >= start_ms), None)
    if s is None:
        raise ValueError("geen candles na startdatum")
    if s < C.SMA_DAYS:
        raise ValueError(f"te weinig historiek voor startdatum ({s} dagen)")
    cash, units, pos, pend, blocked = budget, 0.0, False, None, False
    entry = None
    trades, events, days = [], [], []
    for i in range(s, len(d)):
        x = d[i]
        hi = max(d[j]["h"] for j in range(i - L, i))
        lo = min(d[j]["l"] for j in range(i - L, i))
        A, V = atr[i], va[i]
        sp = x["h"] - x["l"]
        cp = (x["c"] - x["l"]) / sp if sp > 0 else 0.5
        up = x["c"] > sma[i] * (1 + buf)
        down = x["c"] < sma[i] * (1 - buf)
        above = x["c"] > sma[i]
        valid = (hi - lo) <= K * A and abs(d[i - 1]["c"] - d[i - L]["c"]) <= 0.5 * (hi - lo)
        utad = valid and x["h"] > hi and x["c"] < hi and x["v"] > 1.2 * V and cp <= 0.5
        sow = valid and x["c"] < lo and x["v"] > 1.5 * V and sp > A and cp <= 0.4
        spring = valid and x["l"] < lo and x["l"] > lo - 1.5 * A and x["c"] > lo and cp >= 0.5
        lps = False
        if pend:
            if i - pend["i"] > 15 or x["c"] > pend["hi"] * 1.25 or x["c"] < pend["hi"] - 1.5 * pend["A"]:
                pend = None
            elif i > pend["i"] and x["l"] <= pend["hi"] * 1.03 and x["c"] > pend["hi"] * 0.98 and x["v"] < V:
                lps = True
        for name, hit in (("UTAD", utad), ("SOW", sow), ("Spring", spring), ("LPS", lps)):
            if hit:
                events.append({"t": x["t"], "type": name})

        if pos:
            why = None
            if down:
                why = "trend"
            elif utad or sow:
                why = "UTAD" if utad else "SOW"
                blocked = True
            if why:
                cash += units * x["c"] * (1 - fee)
                pnl = x["c"] * (1 - fee) ** 2 / entry["price"] - 1
                trades.append({"t": x["t"], "side": "SELL", "reason": why, "price": x["c"], "pnl": pnl})
                units, pos, entry = 0.0, False, None
        else:
            if down:
                blocked = False
            elif up and not blocked:
                units, cash, pos = cash * (1 - fee) / x["c"], 0.0, True
                entry = {"t": x["t"], "price": x["c"]}
                trades.append({"t": x["t"], "side": "BUY", "reason": "trend", "price": x["c"]})
            elif blocked and (spring or lps) and above:
                units, cash, pos, blocked = cash * (1 - fee) / x["c"], 0.0, True, False
                entry = {"t": x["t"], "price": x["c"]}
                trades.append({"t": x["t"], "side": "BUY", "reason": "Spring" if spring else "LPS", "price": x["c"]})
        if lps:
            pend = None
        if not lps and valid and x["c"] > hi and x["v"] > 1.5 * V and sp > A and cp >= 0.6:
            pend = {"i": i, "hi": hi, "A": A}
            events.append({"t": x["t"], "type": "SOS"})
        days.append({"t": x["t"], "c": x["c"], "sma": sma[i], "eq": cash + units * x["c"]})

    last = d[-1]
    state = {
        "in_position": pos, "blocked": blocked, "entry": entry,
        "value": cash + units * last["c"], "close": last["c"], "sma": sma[-1],
        "buy_line": sma[-1] * (1 + buf), "sell_line": sma[-1] * (1 - buf),
    }
    return {"trades": trades, "events": events, "days": days, "state": state}


def series(d):
    """Koers en gemiddelde voor de grafieken."""
    _, _, sma = indicators(d)
    return [{"t": x["t"], "c": x["c"], "sma": None if math.isnan(m) else m} for x, m in zip(d, sma)]
