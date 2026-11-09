"""Zelftest: herhaalt de backtest en vergelijkt met de referentie uit de analyse.

Referentie (Bitvavo EUR, 6/11/2023 t.e.m. 5/11/2026, €20 per munt):
BTC 59,48 · ETH 36,68 · SOL 57,40 · ADA 39,02 · totaal 192,58
"""
import datetime as dt

from . import config as C, telegram
from .data import fetch_daily
from .main import load_state, save_state
from .strategy import simulate

REF = {"BTC-EUR": 59.48, "ETH-EUR": 36.68, "SOL-EUR": 57.40, "ADA-EUR": 39.02}
START = int(dt.datetime(2023, 11, 6, tzinfo=dt.timezone.utc).timestamp() * 1000)
END = int(dt.datetime(2026, 11, 5, tzinfo=dt.timezone.utc).timestamp() * 1000)


def main():
    lines, ok, tot = ["ZELFTEST backtest (6/11/2023 – 5/11/2026)"], True, 0.0
    for m in C.COINS:
        closed, _ = fetch_daily(m, START - 400 * C.DAY_MS)
        closed = [x for x in closed if x["t"] <= END]
        v = simulate(closed, START)["days"][-1]["eq"]
        tot += v
        good = abs(v - REF[m]) < 0.05
        ok &= good
        lines.append(f"{m.split('-')[0]}: €{v:.2f} (verwacht €{REF[m]:.2f}) {'OK' if good else 'AFWIJKING'}")
    lines.append(f"Totaal: €{tot:.2f} (verwacht €192.58) → {'ALLES OK' if ok else 'CONTROLEREN'}")
    print("\n".join(lines))
    state = load_state()
    telegram.send(state, "\n".join(lines))
    save_state(state)


if __name__ == "__main__":
    main()
