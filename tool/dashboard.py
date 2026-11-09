"""Genereert docs/index.html (GitHub Pages). Eén sobere pagina, leesbaar op gsm."""
import datetime as dt
import json

from . import config as C

CHART_JS = "https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"
NAMES = {"trend": "Trend", "UTAD": "UTAD", "SOW": "SOW", "Spring": "Spring", "LPS": "LPS"}


def d(t, fmt="%d/%m/%Y"):
    return dt.datetime.fromtimestamp(t / 1000, dt.timezone.utc).strftime(fmt)


def num(x, dec=2):
    return f"{x:,.{dec}f}".replace(",", " ").replace(".", ",")


def pct(x):
    return f"{x * 100:+.1f}%".replace(".", ",")


def pdec(x):
    return 2 if x >= 100 else (3 if x >= 1 else 5)


def portfolio(coins, start):
    curves, start_v, value, hold = {}, 0.0, 0.0, 0.0
    for c in coins.values():
        days = c["sim"]["days"]
        c0 = days[0]["c"]
        units = C.BUDGET * (1 - C.FEE) / c0
        start_v += C.BUDGET
        value += days[-1]["eq"]
        hold += units * days[-1]["c"]
        for x in days:
            p = curves.setdefault(x["t"], [0.0, 0.0])
            p[0] += x["eq"]
            p[1] += units * x["c"]
    pts = sorted(curves.items())
    return {"start": start_v, "value": value, "hold": hold,
            "labels": [d(t, "%d/%m") for t, _ in pts],
            "eq": [round(v[0], 2) for _, v in pts], "bh": [round(v[1], 2) for _, v in pts]}


def build(path, coins, state, now_ms):
    pf = portfolio(coins, state["paper_start"])
    cards, charts, rows, data = [], [], [], {}
    n_trades = 0
    for m, c in coins.items():
        coin = m.split("-")[0]
        st = c["sim"]["state"]
        dec = pdec(st["close"])
        if st["in_position"]:
            status, cls = "In positie", "pos"
            line = f"Verkooplijn {num(st['sell_line'], dec)} ({pct(st['close'] / st['sell_line'] - 1)})"
        elif st["blocked"]:
            status, cls = "Cash – wacht op Spring/LPS", "wait"
            line = f"Kooplijn {num(st['buy_line'], dec)}"
        else:
            status, cls = "Cash", "cash"
            line = f"Kooplijn {num(st['buy_line'], dec)} ({pct(st['close'] / st['buy_line'] - 1)})"
        ev = c["last_event"]
        evtxt = f"{ev['type']} op {d(ev['t'])}" if ev else "geen (90 dagen)"
        cards.append(f"""<div class="card"><div class="k">{coin}</div>
<div class="st {cls}">{status}</div>
<div>Slot: €{num(st['close'], dec)} · {pct(st['close'] / st['sma'] - 1)} vs 200d</div>
<div>{line}</div><div class="muted">Laatste Wyckoff-event: {evtxt}</div></div>""")

        days = c["hist"]["days"]
        tset = {x["t"]: i for i, x in enumerate(days)}
        buys, sells = [None] * len(days), [None] * len(days)
        for tr in c["hist"]["trades"]:
            i = tset.get(tr["t"])
            if i is not None:
                (buys if tr["side"] == "BUY" else sells)[i] = tr["price"]
        data[coin] = {
            "labels": [d(x["t"], "%d/%m/%y") for x in days],
            "c": [x["c"] for x in days], "sma": [round(x["sma"], 8) for x in days],
            "buy": [round(x["sma"] * (1 + C.BUFFER), 8) for x in days],
            "sell": [round(x["sma"] * (1 - C.BUFFER), 8) for x in days],
            "b": buys, "s": sells,
        }
        charts.append(f'<h3>{coin}</h3><div class="cw"><canvas id="c_{coin}"></canvas></div>')
        for tr in c["sim"]["trades"]:
            n_trades += 1
            res = pct(tr['pnl']) if tr["side"] == "SELL" else ""
            rows.append((tr["t"], f"<tr><td>{d(tr['t'])}</td><td>{coin}</td><td>{'Kopen' if tr['side'] == 'BUY' else 'Verkopen'}</td>"
                                  f"<td>{NAMES[tr['reason']]}</td><td>€{num(tr['price'], pdec(tr['price']))}</td><td>{res}</td></tr>"))
    rows.sort(key=lambda r: r[0], reverse=True)
    months = max((now_ms - state["paper_start"]) / C.DAY_MS / 30.4, 0.0)
    expected = months * C.EXPECTED_TRADES_PER_MONTH
    data["_pf"] = {"labels": pf["labels"], "eq": pf["eq"], "bh": pf["bh"]}
    table = "".join(r[1] for r in rows) or '<tr><td colspan="6" class="muted">Nog geen signalen sinds de start.</td></tr>'

    page = f"""<!doctype html><html lang="nl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Crypto-alerts</title>
<style>
:root{{--bg:#fafaf9;--fg:#1c1917;--mut:#78716c;--card:#fff;--bd:#e7e5e4;--pos:#15803d;--wait:#b45309;--cash:#57534e}}
@media (prefers-color-scheme:dark){{:root{{--bg:#1c1917;--fg:#f5f5f4;--mut:#a8a29e;--card:#292524;--bd:#44403c;--pos:#4ade80;--wait:#fbbf24;--cash:#d6d3d1}}}}
body{{margin:0;background:var(--bg);color:var(--fg);font:15px/1.45 system-ui,sans-serif}}
main{{max-width:960px;margin:auto;padding:16px}} h1{{font-size:22px;margin:0 0 4px}} h2{{font-size:18px;margin:28px 0 8px}} h3{{font-size:15px;margin:16px 0 4px}}
.muted{{color:var(--mut);font-size:13px}} .grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:10px}}
.card{{background:var(--card);border:1px solid var(--bd);border-radius:10px;padding:12px}} .k{{font-weight:700;font-size:17px}}
.st{{font-weight:600;margin:2px 0 6px}} .pos{{color:var(--pos)}} .wait{{color:var(--wait)}} .cash{{color:var(--cash)}}
.cw{{position:relative;height:240px}} table{{width:100%;border-collapse:collapse;font-size:13px}} td,th{{text-align:left;padding:6px 4px;border-bottom:1px solid var(--bd)}}
.tw{{overflow-x:auto}} .kp{{grid-template-columns:repeat(auto-fit,minmax(140px,1fr));margin-bottom:10px}} .kpi{{font-size:20px;font-weight:700}}
</style></head><body><main>
<h1>Crypto-alerts – paper trading</h1>
<div class="muted">Bijgewerkt {d(now_ms, '%d/%m/%Y %H:%M')} UTC · start {d(state['paper_start'])} · regels: 200-dagengemiddelde ±{C.BUFFER * 100:.0f}% + Wyckoff-exits · geen beleggingsadvies</div>
<h2>Status</h2><div class="grid">{''.join(cards)}</div>
<h2>Paper-portefeuille</h2>
<div class="grid kp"><div class="card"><div class="muted">Paper</div><div class="kpi">€{num(pf['value'])}</div></div>
<div class="card"><div class="muted">Vasthouden</div><div class="kpi">€{num(pf['hold'])}</div></div>
<div class="card"><div class="muted">Start</div><div class="kpi">€{num(pf['start'])}</div></div>
<div class="card"><div class="muted">Signalen live vs verwacht</div><div class="kpi">{n_trades} / ±{expected:.0f}</div></div></div>
<div class="cw"><canvas id="c_pf"></canvas></div>
<h2>Koers, 12 maanden</h2><div class="muted">Groen = kooplijn (+{C.BUFFER * 100:.0f}%), rood = verkooplijn (−{C.BUFFER * 100:.0f}%), markeringen = signalen volgens de regels (simulatie).</div>
{''.join(charts)}
<h2>Signalenlog (paper)</h2><div class="tw"><table><tr><th>Datum</th><th>Munt</th><th>Actie</th><th>Reden</th><th>Koers</th><th>Resultaat</th></tr>{table}</table></div>
</main>
<script src="{CHART_JS}"></script>
<script>
const D={json.dumps(data, separators=(',', ':'))};
const css=n=>getComputedStyle(document.documentElement).getPropertyValue(n).trim();
Chart.defaults.color=css('--mut');Chart.defaults.borderColor=css('--bd');Chart.defaults.font.size=11;
const opt={{responsive:true,maintainAspectRatio:false,animation:false,interaction:{{mode:'index',intersect:false}},
 plugins:{{legend:{{position:'bottom',labels:{{boxWidth:10}}}}}},scales:{{x:{{ticks:{{maxTicksLimit:6}}}}}},elements:{{point:{{radius:0}}}}}};
new Chart(c_pf,{{type:'line',data:{{labels:D._pf.labels,datasets:[
 {{label:'Paper',data:D._pf.eq,borderColor:'#2563eb',borderWidth:2}},{{label:'Vasthouden',data:D._pf.bh,borderColor:'#a8a29e',borderWidth:1.5}}]}},options:opt}});
for(const k of Object.keys(D)){{if(k==='_pf')continue;const x=D[k];
 new Chart(document.getElementById('c_'+k),{{type:'line',data:{{labels:x.labels,datasets:[
  {{label:'Koers',data:x.c,borderColor:css('--fg'),borderWidth:1.5}},
  {{label:'200d',data:x.sma,borderColor:'#a8a29e',borderWidth:1}},
  {{label:'Kooplijn',data:x.buy,borderColor:'#16a34a',borderWidth:1,borderDash:[4,3]}},
  {{label:'Verkooplijn',data:x.sell,borderColor:'#dc2626',borderWidth:1,borderDash:[4,3]}},
  {{label:'Koop',data:x.b,showLine:false,pointRadius:6,pointStyle:'triangle',backgroundColor:'#16a34a',borderColor:'#16a34a'}},
  {{label:'Verkoop',data:x.s,showLine:false,pointRadius:6,pointStyle:'triangle',rotation:180,backgroundColor:'#dc2626',borderColor:'#dc2626'}}]}},options:opt}});}}
</script></body></html>"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(page, encoding="utf-8")
