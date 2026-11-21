"""Shared by app.py (the web page) and alert.py (the Discord message).
To add a market later, add one line to CATEGORIES below: (short name, full name, CFTC code)."""
import json
import urllib.parse
import urllib.request
from datetime import date, timedelta

URL = "https://publicreporting.cftc.gov/resource/6dca-aqww.json"  # CFTC Legacy, futures only
EXTREME = 10  # index <= 10 (net below 0) or >= 90 (net above 0) counts as extreme

CATEGORIES = {
    "Forex": [
        ("USD", "US Dollar Index", "098662"), ("EUR", "Euro", "099741"), ("GBP", "British Pound", "096742"),
        ("JPY", "Japanese Yen", "097741"), ("CHF", "Swiss Franc", "092741"), ("CAD", "Canadian Dollar", "090741"),
        ("AUD", "Australian Dollar", "232741"), ("NZD", "New Zealand Dollar", "112741"),
        ("MXN", "Mexican Peso", "095741"), ("ZAR", "South African Rand", "122741"),
    ],
    "Metals": [
        ("GOLD", "Gold", "088691"), ("SILVER", "Silver", "084691"), ("COPPER", "Copper", "085692"),
        ("PLAT", "Platinum", "076651"), ("PALL", "Palladium", "075651"),
    ],
    "Energy": [
        ("WTI", "Crude Oil (WTI)", "067651"), ("NATGAS", "Natural Gas", "023651"), ("RBOB", "Gasoline (RBOB)", "111659"),
    ],
    "Agriculture": [
        ("CORN", "Corn", "002602"), ("SOY", "Soybeans", "005602"), ("WHEAT", "Wheat (HRW)", "001612"),
        ("SUGAR", "Sugar #11", "080732"), ("COFFEE", "Coffee", "083731"), ("COTTON", "Cotton", "033661"),
    ],
    "Crypto": [("BTC", "Bitcoin", "133741"), ("ETH", "Ether", "146021")],
    "Indices": [
        ("SPX", "S&P 500 (E-mini)", "13874A"), ("NDX", "Nasdaq 100 (E-mini)", "209742"),
        ("DJI", "Dow Jones (x$5)", "124603"), ("RUT", "Russell 2000 (E-mini)", "239742"),
    ],
}

GROUPS = {
    "Large Speculators": ("noncomm_positions_long_all", "noncomm_positions_short_all"),
    "Commercials": ("comm_positions_long_all", "comm_positions_short_all"),
    "Small Traders": ("nonrept_positions_long_all", "nonrept_positions_short_all"),
}


def download(weeks=170):
    codes = ",".join("'%s'" % m[2] for ms in CATEGORIES.values() for m in ms)
    start = (date.today() - timedelta(days=weeks * 7)).isoformat()
    fields = ["report_date_as_yyyy_mm_dd", "cftc_contract_market_code"] + [f for g in GROUPS.values() for f in g]
    params = {
        "$select": ",".join(fields),
        "$where": "cftc_contract_market_code in(%s) AND report_date_as_yyyy_mm_dd >= '%sT00:00:00.000'" % (codes, start),
        "$order": "report_date_as_yyyy_mm_dd",
        "$limit": "50000",
    }
    req = urllib.request.Request(URL + "?" + urllib.parse.urlencode(params), headers={"User-Agent": "Mozilla/5.0 COT-tracker"})
    with urllib.request.urlopen(req, timeout=90) as resp:
        return json.loads(resp.read().decode("utf-8"))


def group_by_code(rows):
    by = {}
    for r in rows:
        by.setdefault(r["cftc_contract_market_code"], []).append(r)
    for k in by:
        by[k].sort(key=lambda x: x["report_date_as_yyyy_mm_dd"])
    return by


def _v(row, field):
    return int(float(row.get(field) or 0))


def nets_for(weeks, group):
    lk, sk = GROUPS[group]
    return [_v(x, lk) - _v(x, sk) for x in weeks]


def index_at(nets, i, lookback):
    window = nets[max(0, i - lookback + 1): i + 1]
    lo, hi = min(window), max(window)
    return round((nets[i] - lo) / (hi - lo) * 100) if hi != lo else 50


def signal(net, idx):
    if idx <= EXTREME and net < 0:
        return "EXTREME SHORT", "ex"
    if idx >= 100 - EXTREME and net > 0:
        return "EXTREME LONG", "ex"
    return ("BULLISH", "bu") if net >= 0 else ("BEARISH", "be")


def summarise(by, markets, group, lookback):
    """Returns (rows for the table, list of markets the CFTC sent no data for)."""
    lk, sk = GROUPS[group]
    out, missing = [], []
    for tick, name, code in markets:
        w = by.get(code, [])
        if len(w) < 3:
            missing.append(tick)
            continue
        n = nets_for(w, group)
        i = len(n) - 1
        L, S = _v(w[-1], lk), _v(w[-1], sk)
        pL, pS = _v(w[-2], lk), _v(w[-2], sk)
        out.append(dict(
            tick=tick, name=name, L=L, S=S, dL=L - pL, dS=S - pS, net=n[i], wk=n[i] - n[i - 1],
            lp=round(L / (L + S) * 100) if L + S else 0, idx=index_at(n, i, lookback),
            prev_net=n[i - 1], prev_idx=index_at(n, i - 1, lookback), date=w[-1]["report_date_as_yyyy_mm_dd"][:10]))
    return out, missing


# ---- Pair lean (used by the "My pairs" section and the Discord alert) ----
# Edit this list to change your pairs: (pair name, base ticker, quote ticker). Tickers come from CATEGORIES above.
PAIRS = [
    ("EUR/USD", "EUR", "USD"),
    ("USD/JPY", "USD", "JPY"),
    ("GBP/USD", "GBP", "USD"),
    ("XAU/USD", "GOLD", "USD"),
]
LEAN_MIN = 30     # COT Index gap needed before there is a lean
LEAN_STRONG = 60  # gap needed for a "strong" lean


def pair_lean(base, quote):
    """base and quote are rows from summarise(). The lean compares where each currency sits in its own range."""
    gap = base["idx"] - quote["idx"]
    lean = "BUY" if gap >= LEAN_MIN else "SELL" if gap <= -LEAN_MIN else "NONE"
    strength = "strong" if abs(gap) >= LEAN_STRONG else "moderate"
    text = "NO CLEAR LEAN" if lean == "NONE" else "LEAN %s (%s)" % (lean, strength)
    notes = []
    for o in (base, quote):
        label = signal(o["net"], o["idx"])[0]
        if label.startswith("EXTREME"):
            notes.append("%s is at an %s: a crowded trade, so reversals can be sharp." % (o["tick"], label.lower()))
    return dict(lean=lean, text=text, gap=gap, notes=notes)


def verdict(lean, trend):
    """Combines the weekly COT lean with the trend the user reads from their own daily chart."""
    if trend == "Not set":
        return "Pick today's chart trend above to compare it with the COT lean."
    if lean["lean"] == "NONE":
        return "COT has no clear lean here. Rely on your other indicators."
    want = "Up" if lean["lean"] == "BUY" else "Down"
    if trend == want:
        return "Aligned: COT and your chart agree (%s bias)." % lean["lean"]
    if trend == "Sideways":
        return "Your chart is sideways, so the COT lean has no trend support yet."
    return "Conflict: COT leans %s but your chart trend is %s. Wait for more confirmation." % (lean["lean"], trend.lower())
