import csv
import io

import pandas as pd
import streamlit as st

from cot_core import CATEGORIES, GROUPS, download, group_by_code, index_at, nets_for, signal, summarise

st.set_page_config(page_title="COT Tracker", layout="wide")

CSS = """
<style>
.stApp{background:#0e1a33}
.stApp, .stApp label, .stApp p, .stApp h1, .stApp h3{color:#e6ecfa}
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

SORTS = ["Default order", "COT Index: lowest first", "COT Index: highest first", "Biggest weekly change"]


@st.cache_data(ttl=6 * 3600, show_spinner="Downloading from the CFTC...")
def get_rows():
    return download()


def num(n, plus=False):
    s = format(abs(n), ",")
    if n < 0:
        return "&minus;" + s
    return ("+" + s) if plus and n > 0 else s


def colored(n):
    return '<span class="%s">%s</span>' % ("r" if n < 0 else "g", num(n, True))


def arrange(data, sort, only_extreme):
    view = list(data)
    if only_extreme:
        view = [o for o in view if signal(o["net"], o["idx"])[0].startswith("EXTREME")]
    if sort == SORTS[1]:
        view.sort(key=lambda o: o["idx"])
    elif sort == SORTS[2]:
        view.sort(key=lambda o: -o["idx"])
    elif sort == SORTS[3]:
        view.sort(key=lambda o: -abs(o["wk"]))
    return view


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

c1, c2, c3, c4, c5 = st.columns([3, 1.3, 1.6, 1.2, 0.8])
group = c1.radio("Who are we looking at?", list(GROUPS), horizontal=True)
lookback = c2.selectbox("Index looks back (weeks)", [26, 52, 104, 156], index=1)
sort = c3.selectbox("Sort by", SORTS)
only_extreme = c4.checkbox("Extremes only")
c5.write("")
if c5.button("Refresh"):
    st.cache_data.clear()
    st.rerun()

try:
    by = group_by_code(get_rows())
except Exception as e:
    st.error("Could not get the data from the CFTC. Try Refresh in a minute. Details: %s" % e)
    st.stop()

all_rows, all_missing, as_of = [], [], ""
tabs = st.tabs(list(CATEGORIES))
for tab, (cat, markets) in zip(tabs, CATEGORIES.items()):
    with tab:
        data, missing = summarise(by, markets, group, lookback)
        all_missing += missing
        all_rows += [(cat, o) for o in data]
        if data:
            as_of = data[0]["date"]
        view = arrange(data, sort, only_extreme)
        if view:
            st.markdown(table_html(view), unsafe_allow_html=True)
        else:
            st.info("Nothing at an extreme in this tab right now." if data else "No data came back for this tab.")

st.caption("%s · Positions as of %s (a Tuesday; the CFTC publishes on Fridays)" % (group, as_of))
if all_missing:
    st.warning("No data found for: %s. The CFTC code for these may need fixing. Tell Claude." % ", ".join(all_missing))

buf = io.StringIO()
w = csv.writer(buf)
w.writerow(["tab", "market", "group", "positions_as_of", "long", "short", "net", "weekly_change", "long_pct", "cot_index", "signal"])
for cat, o in all_rows:
    w.writerow([cat, o["tick"], group, o["date"], o["L"], o["S"], o["net"], o["wk"], o["lp"], o["idx"], signal(o["net"], o["idx"])[0]])
st.download_button("Download all tabs as CSV", buf.getvalue(), "cot_%s.csv" % group.replace(" ", "_"), "text/csv")

st.markdown("### Look closer")
flat = [(cat, m) for cat, ms in CATEGORIES.items() for m in ms if m[2] in by]
labels = ["%s - %s" % (m[0], m[1]) for _, m in flat]
if labels:
    pick = st.selectbox("Pick a market to see its history", labels)
    weeks = by[flat[labels.index(pick)][1][2]]
    dates = pd.to_datetime([x["report_date_as_yyyy_mm_dd"][:10] for x in weeks])
    st.caption("Net position over time (Long minus Short) for all three groups")
    st.line_chart(pd.DataFrame({g: nets_for(weeks, g) for g in GROUPS}, index=dates))
    n = nets_for(weeks, group)
    st.caption("COT Index over time for %s (0 = most bearish, 100 = most bullish)" % group)
    st.line_chart(pd.DataFrame({"COT Index": [index_at(n, i, lookback) for i in range(len(n))]}, index=dates))

st.caption("Net = Long minus Short. Weekly change = how much Net moved since last week. "
           "COT Index: 0 = most bearish in the lookback period, 100 = most bullish. "
           "This is information, not trading advice.")
