"""
COT Discord alert - Large Speculators, forex currencies.
Runs on GitHub every Friday, posts a short summary to Discord.
The Discord address comes from a GitHub secret named DISCORD_WEBHOOK_URL (never type it in this file).
"""
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import date, timedelta

URL = "https://publicreporting.cftc.gov/resource/6dca-aqww.json"
APP_LINK = "https://gm-cot-tracker.streamlit.app"
LOOKBACK = 52   # weeks the COT Index looks back
EXTREME = 10    # index <= 10 (net below 0) or >= 90 (net above 0) = extreme
LONG_F, SHORT_F = "noncomm_positions_long_all", "noncomm_positions_short_all"

MARKETS = [("EUR", "099741"), ("GBP", "096742"), ("JPY", "097741"), ("CHF", "092741"),
           ("CAD", "090741"), ("AUD", "232741"), ("NZD", "112741"), ("MXN", "095741"), ("ZAR", "122741")]


def download():
    codes = ",".join("'%s'" % c for _, c in MARKETS)
    start = (date.today() - timedelta(days=(LOOKBACK + 10) * 7)).isoformat()
    params = {
        "$select": "report_date_as_yyyy_mm_dd,cftc_contract_market_code,%s,%s" % (LONG_F, SHORT_F),
        "$where": "cftc_contract_market_code in(%s) AND report_date_as_yyyy_mm_dd >= '%sT00:00:00.000'" % (codes, start),
        "$order": "report_date_as_yyyy_mm_dd",
        "$limit": "5000",
    }
    req = urllib.request.Request(URL + "?" + urllib.parse.urlencode(params), headers={"User-Agent": "Mozilla/5.0 COT-alert"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def index_at(nets, i):
    window = nets[max(0, i - LOOKBACK + 1): i + 1]
    lo, hi = min(window), max(window)
    return round((nets[i] - lo) / (hi - lo) * 100) if hi != lo else 50


def status(net, idx):
    if idx <= EXTREME and net < 0:
        return "EXTREME SHORT"
    if idx >= 100 - EXTREME and net > 0:
        return "EXTREME LONG"
    return "NORMAL"


def build_message():
    rows = download()
    by = {}
    for r in rows:
        by.setdefault(r["cftc_contract_market_code"], []).append(r)
    extremes, left, as_of = [], [], ""
    for tick, code in MARKETS:
        w = sorted(by.get(code, []), key=lambda x: x["report_date_as_yyyy_mm_dd"])
        if len(w) < 3:
            continue
        nets = [int(x[LONG_F]) - int(x[SHORT_F]) for x in w]
        i = len(nets) - 1
        idx_now, idx_before = index_at(nets, i), index_at(nets, i - 1)
        now, before = status(nets[i], idx_now), status(nets[i - 1], idx_before)
        as_of = w[-1]["report_date_as_yyyy_mm_dd"][:10]
        if now != "NORMAL":
            tag = "" if before == now else " - NEW this week"
            extremes.append("%s: %s (index %d, net %s)%s" % (tick, now.title(), idx_now, format(nets[i], ","), tag))
        elif before != "NORMAL":
            left.append("%s: was %s, now index %d" % (tick, before.title(), idx_now))
    if not as_of:
        raise RuntimeError("The CFTC sent no usable data.")
    text = "**COT update** - Large Speculators, positions as of %s\n\n" % as_of
    if extremes:
        text += "**At an extreme right now**\n" + "\n".join(extremes) + "\n"
    else:
        text += "No currencies at an extreme this week.\n"
    if left:
        text += "\n**No longer extreme**\n" + "\n".join(left) + "\n"
    text += "\n<%s>" % APP_LINK
    return text


def post(text):
    hook = os.environ.get("DISCORD_WEBHOOK_URL", "")
    if not hook:
        print("DISCORD_WEBHOOK_URL is missing. Add it in GitHub: Settings > Secrets and variables > Actions.")
        sys.exit(1)
    req = urllib.request.Request(hook, data=json.dumps({"content": text}).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": "DiscordBot (cot-alert, 1.0)"})
    urllib.request.urlopen(req, timeout=30).read()


if __name__ == "__main__":
    try:
        message = build_message()
    except Exception as e:
        post("**COT alert failed:** %s" % e)
        raise
    print(message)
    post(message)
