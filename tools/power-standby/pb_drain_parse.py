#!/usr/bin/env python3
# pb_drain_parse.py — last night's discharge forensics. arg1 = dir with bs.txt/bsh.txt (batterystats dumps)
import re, sys, datetime
from collections import Counter

B = sys.argv[1]
lines = open(B + "/bsh.txt", encoding="utf-8", errors="replace").read().splitlines()
m = next((re.search(r"RESET:TIME:\s*(\d{4})-(\d{2})-(\d{2})-(\d{2})-(\d{2})-(\d{2})", l) for l in lines if "RESET:TIME" in l), None)
if not m: sys.exit("no RESET:TIME")
reset = datetime.datetime(*map(int, m.groups()))
W0 = datetime.datetime(2026, 11, 13, 23, 30); W1 = datetime.datetime(2026, 11, 14, 11, 40)

OFF = re.compile(r"^\+?(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?(?:(\d+)ms)?(?=$|\s)")
wlk = Counter(); hourly = {}; out = []
dev_prev = top_prev = act_prev = ""
for l in lines:
    l = l.strip()
    if not l or ("RESET" in l): continue
    tok = l.split(" ", 1)[0]
    mm = OFF.match(tok)
    if not mm or tok == "0" and " " not in l: continue
    d, h, mi, s, ms = [int(g or 0) for g in mm.groups()]
    t = reset + datetime.timedelta(days=d, hours=h, minutes=mi, seconds=s, milliseconds=ms)
    body = l[len(tok):].strip()
    if not (W0 <= t <= W1): continue
    hh = t.strftime("%m-%d %H:%M:%S")
    if re.search(r"[+~-](screen|running|doze|idle|plugged|sensors|audio|video|gps|wifi|cell|bluetooth|nfc|usb|charging|notification|heads up|job|sync)", body, re.I) or \
       re.search(r"(^| )(device_idle|top|active|temp|status|phone_signal|wifi_signal|battery_level)=", body):
        out.append(hh + " | " + body[:130])
    for sign, owner, name in re.findall(r"([+~-])wake_lock=([^:\s]+):\"?([^\"]*)", body):
        if sign == "+": wlk[(owner, name[:34])] += 1
    ch = re.search(r"charge=(\d+)", body)
    if ch: hourly[t.strftime("%m-%d %H")] = int(ch.group(1))
    di = re.search(r"device_idle=(\w+)", body)
    if di and di.group(1) != dev_prev: dev_prev = di.group(1); out.append(hh + " | IDLE -> " + di.group(1))
    tp = re.search(r"top=(\S+)", body)
    if tp and tp.group(1) != top_prev: top_prev = tp.group(1); out.append(hh + " | TOP=" + tp.group(1))

# dedupe consecutive identical bodies (keep first+last per run to compress storms)
comp = []
prevk = None; prevline = None
for o in out:
    k = o.split(" | ", 1)[1]
    if k == prevk: prevline = o; continue
    if prevline: comp.append(prevline)
    comp.append(o); prevk = k; prevline = None
if prevline: comp.append(prevline)

print("== transitions 23:30 -> 11:40 (runs compressed), total %d ==" % len(out))
for c in comp[:400]: print(c)
if len(comp) > 400: print("...TRUNCATED..."); [print(c) for c in comp[-12:]]
print("\n== wake_lock openers (owner, name) ==")
for (owner, name), n in wlk.most_common(18): print("%6d  %-9s %s" % (n, owner, name))
print("\n== hourly battery charge units (trend) ==")
ks = sorted(hourly)
print(" | ".join("%s:%d" % (k[6:], hourly[k]) for k in ks))

txt = open(B + "/bs.txt", encoding="utf-8", errors="replace").read().splitlines()
def block(head, n):
    for i, l in enumerate(txt):
        if head in l:
            print("\n== bs.txt %s ==" % head)
            for j in range(i, min(i + n, len(txt))): print(txt[j][:150])
            return
block("Estimated power use", 40)
block("Partial wake locks", 30)
