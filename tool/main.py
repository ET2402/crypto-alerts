"""Hoofdrun: 4x per dag via GitHub Actions.

- Beslissingen (KOPEN/VERKOPEN) alleen op afgesloten dagcandles (dagafsluiting 00:00 UTC).
- Tussendoor: waarschuwingen op basis van de lopende koers (geen beslissing).
"""
import datetime as dt
import json
import os
import time
from pathlib import Path

from . import config as C
from . import dashboard, telegram
from .data import fetch_daily
from .strategy import simulate

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "state" / "state.json"
DOCS = ROOT / "docs" / "index.html"

REASONS = {
    "trend": "trend: slotkoers {dir} 200-dagengemiddelde {pm}3%",
    "UTAD": "UTAD: valse uitbraak boven de range op hoog volume",
    "SOW": "Sign of Weakness: breuk onder de range op hoog volume",
    "Spring": "Spring: valse breuk onder de range, herstel boven steun",
    "LPS": "LPS: geslaagde terugtest na uitbraak",
}


def eur(x):
    if x >= 100:
        s = f"{x:,.2f}"
    elif x >= 1:
        s = f"{x:.3f}"
    else:
        s = f"{x:.5f}"
    return "€" + s.replace(",", " ").replace(".", ",")


def day(t):
    return dt.datetime.fromtimestamp(t / 1000, dt.timezone.utc).strftime("%d/%m/%Y")


def reason_text(tr):
    r = tr["reason"]
    if r == "trend":
        return REASONS[r].format(dir="boven" if tr["side"] == "BUY" else "onder",
                                 pm="+" if tr["side"] == "BUY" else "-")
    return REASONS[r]


def dash_url():
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if "/" in repo:
        owner, name = repo.split("/", 1)
        return f"https://{owner.lower()}.github.io/{name}/"
    return "(dashboard-link volgt na publicatie)"


def load_state():
    if STATE.exists() and STATE.read_text().strip():
        return json.loads(STATE.read_text())
    return {}


def save_state(state):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, indent=1, sort_keys=True))


def run(now_ms=None, fetch=fetch_daily):
    state = load_state()
    state.setdefault("alerted", [])
    state.setdefault("warn", {})
    now_ms = now_ms or int(time.time() * 1000)
    year_ago = now_ms - 365 * C.DAY_MS
    since = min(state.get("paper_start", now_ms), year_ago) - 320 * C.DAY_MS
    url = dash_url()
    msgs, coins = [], {}

    for m in C.COINS:
        closed, live = fetch(m, since, now_ms)
        if "paper_start" not in state:
            state["paper_start"] = closed[-1]["t"]
        sim = simulate(closed, state["paper_start"])
        hist = simulate(closed, year_ago)
        st = sim["state"]
        coin = m.split("-")[0]

        # 1. Nieuwe KOPEN/VERKOPEN-signalen
        for tr in sim["trades"]:
            key = f"{m}|{tr['t']}|{tr['side']}"
            if key in state["alerted"]:
                continue
            state["alerted"].append(key)
            lines = [
                f"{'KOPEN' if tr['side'] == 'BUY' else 'VERKOPEN'} – {coin}",
                f"Reden: {reason_text(tr)}",
                f"Slotkoers {day(tr['t'])}: {eur(tr['price'])} | 200d-gem.: {eur(st['sma'])}",
            ]
            if tr["side"] == "SELL":
                lines.append(f"Resultaat positie: {tr['pnl'] * 100:+.1f}%".replace(".", ","))
            lines.append(f"Dashboard: {url}")
            msgs.append("\n".join(lines))

        # 2. Waarschuwingen (ook tussen de dagafsluitingen door)
        price = live["c"] if live else st["close"]
        code, text = None, None
        if not st["in_position"] and not st["blocked"]:
            if live and price > st["buy_line"]:
                code = "live_boven_kooplijn"
                text = f"staat nu {eur(price)}, boven de kooplijn {eur(st['buy_line'])}. Beslissing bij dagafsluiting (01:00/02:00)."
            elif st["buy_line"] * (1 - C.WARN_ZONE) <= price <= st["buy_line"]:
                code = "nadert_kooplijn"
                text = f"nadert de kooplijn: {eur(price)} vs {eur(st['buy_line'])}."
        elif st["in_position"]:
            if live and price < st["sell_line"]:
                code = "live_onder_verkooplijn"
                text = f"staat nu {eur(price)}, onder de verkooplijn {eur(st['sell_line'])}. Beslissing bij dagafsluiting (01:00/02:00)."
            elif st["sell_line"] <= price <= st["sell_line"] * (1 + C.WARN_ZONE):
                code = "nadert_verkooplijn"
                text = f"nadert de verkooplijn: {eur(price)} vs {eur(st['sell_line'])}."
        if code != state["warn"].get(m):
            sent = state.setdefault("warn_sent", {}).setdefault(m, {})
            # zelfde waarschuwing max. 1x per 7 dagen (tegen heen-en-weer rond een lijn)
            if code and now_ms - sent.get(code, 0) >= 7 * C.DAY_MS:
                msgs.append(f"WAARSCHUWING – {coin}\n{coin} {text}\nNog geen actie nodig.")
                sent[code] = now_ms
            state["warn"][m] = code

        last_event = next((e for e in reversed(sim["events"] + hist["events"])
                           if e["t"] >= now_ms - 90 * C.DAY_MS), None)
        coins[m] = {"closed": closed, "live": live, "sim": sim, "hist": hist, "last_event": last_event}

    # 3. Eerste run: bevestiging
    if not state.get("started"):
        state["started"] = True
        lines = [f"Crypto-alerttool gestart. Paper trading vanaf {day(state['paper_start'])}, €{C.BUDGET:.0f} per munt."]
        for m, c in coins.items():
            st = c["sim"]["state"]
            lijn = f"verkooplijn {eur(st['sell_line'])}" if st["in_position"] else f"kooplijn {eur(st['buy_line'])}"
            lines.append(f"{m.split('-')[0]}: {'in positie' if st['in_position'] else 'cash'} | slot {eur(st['close'])} | {lijn}")
        lines.append(f"Dashboard: {url}")
        msgs.insert(0, "\n".join(lines))

    # 4. Weekoverzicht: zondagavond
    now = dt.datetime.fromtimestamp(now_ms / 1000, dt.timezone.utc)
    today = now.strftime("%Y-%m-%d")
    if now.weekday() == 6 and now.hour >= 17 and state.get("last_weekly") != today:
        state["last_weekly"] = today
        pf = dashboard.portfolio(coins, state["paper_start"])
        lines = ["WEEKOVERZICHT"]
        for m, c in coins.items():
            st = c["sim"]["state"]
            lines.append(f"{m.split('-')[0]}: {'in positie' if st['in_position'] else 'cash'} | {eur(st['close'])} | {(st['close'] / st['sma'] - 1) * 100:+.1f}% vs 200d".replace(".", ","))
        lines.append(f"Paper: {eur(pf['value'])} | vasthouden: {eur(pf['hold'])} (start {eur(pf['start'])})")
        lines.append(f"Dashboard: {url}")
        msgs.append("\n".join(lines))

    dashboard.build(DOCS, coins, state, now_ms)
    for msg in msgs:
        telegram.send(state, msg)
    save_state(state)
    return msgs


def main():
    try:
        run()
    except Exception as e:
        state = load_state()
        try:
            telegram.send(state, f"FOUT in crypto-alerttool\n{type(e).__name__}: {e}\nDe volgende run probeert opnieuw.")
        finally:
            save_state(state)
        raise


if __name__ == "__main__":
    main()
