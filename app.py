import json
import urllib.parse
import urllib.request
from datetime import date, timedelta

import streamlit as st

st.set_page_config(page_title="COT Tracker", layout="wide")

URL = "https://publicreporting.cftc.gov/resource/6dca-aqww.json"  # CFTC Legacy, futures only
EXTREME_LEVEL = 10  # index <= 10 or >= 90 counts as extreme

MARKETS = [
    ("EUR", "Euro", "099741"),
    ("GBP", "British Pound", "096742"),
    ("JPY", "Japanese Yen", "097741"),
    ("CHF", "Swiss Franc", "092741"),
    ("CAD", "Canadian Dollar", "090741"),
    ("AUD", "Australian Dollar", "232741"),
    ("NZD", "New Zealand Dollar", "112741"),
    ("MXN", "Mexican Peso", "095741"),
    ("ZAR", "South African Rand", "122741"),
]

GROUPS = {
    "Large Speculators": ("noncomm_positions_long_all", "noncomm_positions_short_all"),
    "Commercials": ("comm_positions_long_all", "comm_positions_short_all"),
    "Small Traders": ("nonrept_positions_long_all", "nonrept_positions_short_all"),
}

FIELDS = ["report_date_as_yyyy_mm_dd", "cftc_contract_market_code"] + [f for g in GROUPS.values() for f in g]

CSS = """
<style>
.stApp{background:#0e1a33}
.stApp, .stApp label, .stApp p, .stApp h1{color:#e6ecfa}
.cot-wrap{background:#142447;border:1px solid #233763;border-radius:12px;padding:6px 14px;overflow-x:auto}
table.cot{border-collapse:collapse;width:100%;min-width:900px;font-variant-numeric:tabular-nums}
table.cot th{color:#8fa2c8;font-size:12px;text-align:right;padding:12px 8px;border-bottom:1px solid #233763;letter-spacing:.06em}
table.cot td{padding:12px 8px;text-align:right;border-bottom:1px solid #1d2f58;color:#e6ecfa}
table.cot th:first-child,table.cot td:first-child{text-align:left}
.tick{font-weight:700;margin-right:10px}.nm{color:#8fa2c8;font-size:14px}
.g{color:#3ecf8e}.r{color:#ff6b6b}.sm{font-size:12px;display:block}
.bar{display:inline-block;width:120px;height:8px;border-radius:4px;background:#ff6b6b;overflow:hidden;vertical-align:middle;margin:0 8px}
.bar i{display:block;height:100%;background:#3ecf8e}
.trk{display:inline-block;width:80px;height:6px;border-radius:3px;background:#233763;position:relative;vertical-align:middle;margin-right:8px}
.trk i{position:absolute;top:-4px;width:3px;height:14px;background:#fff;border-radius:2px}
.tag{display:inline-block;padding:4px 12px;border-radius:12px;font-size:11px;font-weight:700}
.ex{background:rgba(245,185,66,.18);color:#f5b942}
.be{background:rgba(255,107,107,.18);color:#ff6b6b}
.bu{background:rgba(62,207,142,.18);color:#3ecf8e}
</style>
"""


@st.cache_data(ttl=6 * 3600, show_spinner="Downloading from the CFTC...")
def download():
    codes = ",".join("'%s'" % m[2] for m in MARKETS)
    start = (date.today() - timedelta(days=170 * 7)).isoformat()
    params = {
        "$select": ",".join(FIELDS),
        "$where": "cftc_contract_market_code in(%s) AND report_date_as_yyyy_mm_dd >= '%sT00:00:00.000'" % (codes, start),
        "$order": "report_date_as_yyyy_mm_dd",
        "$limit": "5000",
    }
    req = urllib.request.Request(URL + "?" + urllib.parse.urlencode(params), headers={"User-Agent": "Mozilla/5.0 COT-tracker"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def signal(net, index):
    if index <= EXTREME_LEVEL and net < 0:
        return "EXTREME SHORT", "ex"
    if index >= 100 - EXTREME_LEVEL and net > 0:
        return "EXTREME LONG", "ex"
    return ("BULLISH", "bu") if net >= 0 else ("BEARISH", "be")


def num(n, plus=False):
    s = format(abs(n), ",")
    if n < 0:
        return "&minus;" + s
    return ("+" + s) if plus and n > 0 else s


def colored(n):
    return '<span class="%s">%s</span>' % ("r" if n < 0 else "g", num(n, True))


def build(rows, group, lookback):
    lk, sk = GROUPS[group]
    by = {}
    for r in rows:
        by.setdefault(r["cftc_contract_market_code"], []).append(r)
    out = []
    for tick, name, code in MARKETS:
        w = sorted(by.get(code, []), key=lambda x: x["report_date_as_yyyy_mm_dd"])
        if len(w) < 2:
            continue
        nets = [int(x[lk]) - int(x[sk]) for x in w]
        recent = nets[-lookback:]
        lo, hi = min(recent), max(recent)
        idx = round((nets[-1] - lo) / (hi - lo) * 100) if hi != lo else 50
        L, S = int(w[-1][lk]), int(w[-1][sk])
        pL, pS = int(w[-2][lk]), int(w[-2][sk])
        out.append(dict(tick=tick, name=name, L=L, S=S, dL=L - pL, dS=S - pS, net=nets[-1],
                        wk=nets[-1] - nets[-2], lp=round(L / (L + S) * 100) if L + S else 0,
                        idx=idx, date=w[-1]["report_date_as_yyyy_mm_dd"][:10]))
    return out


def table_html(data):
    head = "".join("<th>%s</th>" % h for h in ["MARKET", "LONG", "SHORT", "NET", "WEEKLY &Delta;", "LONG / SHORT", "COT INDEX", "SIGNAL"])
    body = ""
    for o in data:
        label, cls = signal(o["net"], o["idx"])
        body += (
            '<tr><td><span class="tick">%s</span><span class="nm">%s</span></td>' % (o["tick"], o["name"])
            + '<td>%s<span class="sm">%s</span></td>' % (num(o["L"]), colored(o["dL"]))
            + '<td>%s<span class="sm">%s</span></td>' % (num(o["S"]), colored(o["dS"]))
            + '<td><b>%s</b></td>' % colored(o["net"])
            + '<td>%s</td>' % colored(o["wk"])
            + '<td>%d%%<span class="bar"><i style="width:%d%%"></i></span>%d%%</td>' % (o["lp"], o["lp"], 100 - o["lp"])
            + '<td><span class="trk"><i style="left:%d%%"></i></span>%d</td>' % (min(o["idx"], 97), o["idx"])
            + '<td><span class="tag %s">%s</span></td></tr>' % (cls, label)
        )
    return '<div class="cot-wrap"><table class="cot"><thead><tr>%s</tr></thead><tbody>%s</tbody></table></div>' % (head, body)


st.markdown(CSS, unsafe_allow_html=True)
st.title("COT Tracker")

c1, c2, c3 = st.columns([3, 1.4, 1])
group = c1.radio("Who are we looking at?", list(GROUPS), horizontal=True)
lookback = c2.selectbox("COT Index looks back (weeks)", [26, 52, 104, 156], index=1)
c3.write("")
if c3.button("Refresh"):
    st.cache_data.clear()
    st.rerun()

try:
    rows = download()
    data = build(rows, group, lookback)
except Exception as e:
    st.error("Could not get the data from the CFTC. Try Refresh in a minute. Details: %s" % e)
    st.stop()

if not data:
    st.warning("The CFTC sent no data. Try Refresh.")
    st.stop()

st.caption("Forex · %s · Positions as of %s (a Tuesday; the CFTC publishes on Fridays)" % (group, data[0]["date"]))
st.markdown(table_html(data), unsafe_allow_html=True)
st.caption("Net = Long minus Short. Weekly change = how much Net moved since last week. "
           "COT Index: 0 = most bearish in the lookback period, 100 = most bullish. "
           "This is information, not trading advice.")
