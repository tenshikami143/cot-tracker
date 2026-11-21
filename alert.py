"""
COT Discord alert - Large Speculators, all tabs (Forex, Metals, Energy, Agriculture, Crypto, Indices).
Runs on GitHub every Friday and posts a short summary to Discord.
The Discord address comes from the GitHub secret DISCORD_WEBHOOK_URL (never type it in this file).
"""
import json
import os
import sys
import urllib.request

from cot_core import CATEGORIES, PAIRS, commercial_short, download, group_by_code, pair_lean, signal, summarise

APP_LINK = "https://gm-cot-tracker.streamlit.app"
LOOKBACK = 52
GROUP = "Large Speculators"


def build_message():
    by = group_by_code(download())
    sections, as_of, by_tick, com_tick = [], "", {}, {}
    for cat, markets in CATEGORIES.items():
        data, _ = summarise(by, markets, GROUP, LOOKBACK)
        com = {c["tick"]: c for c in summarise(by, markets, "Commercials", LOOKBACK)[0]}
        com_tick.update(com)
        lines, left = [], []
        for o in data:
            as_of = o["date"]
            by_tick[o["tick"]] = o
            now = signal(o["net"], o["idx"])[0]
            before = signal(o["prev_net"], o["prev_idx"])[0]
            if now.startswith("EXTREME"):
                tag = "" if before == now else " - NEW this week"
                c = com.get(o["tick"])
                cm = " | Commercials: %s (index %d)" % (signal(c["net"], c["idx"])[0].title(), c["idx"]) if c else ""
                lines.append("%s: %s (index %d, net %s)%s%s" % (o["tick"], now.title(), o["idx"], format(o["net"], ","), tag, cm))
            elif before.startswith("EXTREME"):
                left.append("%s: was %s, now index %d" % (o["tick"], before.title(), o["idx"]))
        if lines or left:
            text = "**%s**\n" % cat + "\n".join(lines)
            if left:
                text += ("\n" if lines else "") + "No longer extreme:\n" + "\n".join(left)
            sections.append(text)
    if not as_of:
        raise RuntimeError("The CFTC sent no usable data.")
    head = "**COT update** - %s, positions as of %s" % (GROUP, as_of)
    body = "\n\n".join(sections) if sections else "No markets at an extreme this week."
    pair_lines = []
    for name, b, q in PAIRS:
        if b in by_tick and q in by_tick:
            line = "%s: %s" % (name, pair_lean(by_tick[b], by_tick[q])["text"])
            if b in com_tick and q in com_tick:
                line += " | " + commercial_short(pair_lean(com_tick[b], com_tick[q]))
            pair_lines.append(line)
    if pair_lines:
        body = "**My pairs (weekly lean)**\n" + "\n".join(pair_lines) + "\n\n" + body
    return head + "\n\n" + body + "\n\n<%s>" % APP_LINK


def post(text):
    hook = os.environ.get("DISCORD_WEBHOOK_URL", "")
    if not hook:
        print("DISCORD_WEBHOOK_URL is missing. Add it in GitHub: Settings > Secrets and variables > Actions.")
        sys.exit(1)
    chunks, current = [], ""
    for part in text.split("\n\n"):  # Discord allows about 2000 characters per message
        if len(current) + len(part) > 1800 and current:
            chunks.append(current)
            current = ""
        current += ("\n\n" if current else "") + part
    chunks.append(current)
    for c in chunks:
        req = urllib.request.Request(hook, data=json.dumps({"content": c}).encode("utf-8"), method="POST",
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
