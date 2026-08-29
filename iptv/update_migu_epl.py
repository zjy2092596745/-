#!/usr/bin/env python3
import re
import ssl
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

SPORT_URL = "https://tv.iill.top/m3u/Sport"
OUT = Path(__file__).with_name("migu-epl.m3u")
UA = "okhttp/3.15"
EPL_RE = re.compile(r"英超|英格兰(?:足球)?超级联赛|Premier\s+League|\bEPL\b", re.I)
MIGU_RE = re.compile(r"咪咕|migu|cmvideo", re.I)


def fetch_sport():
    req = Request(SPORT_URL, headers={"User-Agent": UA, "Accept": "*/*"})
    # tv.iill.top 当前证书链在 GitHub Actions 上校验异常，因此仅对这个公开播放列表关闭证书校验。
    ctx = ssl._create_unverified_context()
    with urlopen(req, timeout=30, context=ctx) as r:
        return r.read().decode("utf-8", errors="replace")


def parse_entries(text):
    lines = text.replace("\r", "").split("\n")
    entries = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line.startswith("#EXTINF"):
            i += 1
            continue
        meta = line
        extra = []
        url = ""
        i += 1
        while i < len(lines) and not lines[i].strip().startswith("#EXTINF"):
            x = lines[i].strip()
            if x:
                if x.startswith("#"):
                    extra.append(x)
                elif not url:
                    url = x
                else:
                    extra.append(x)
            i += 1
        if url:
            entries.append((meta, extra, url))
    return entries


def set_group(meta, group="英超"):
    if 'group-title="' in meta:
        return re.sub(r'group-title="[^"]*"', f'group-title="{group}"', meta)
    pos = meta.rfind(",")
    if pos >= 0:
        return meta[:pos] + f' group-title="{group}"' + meta[pos:]
    return meta


def main():
    text = fetch_sport()
    entries = parse_entries(text)

    epl = []
    migu_epl = []
    for meta, extra, url in entries:
        hay = " ".join([meta, url, *extra])
        if not EPL_RE.search(hay):
            continue
        item = (set_group(meta), extra, url)
        epl.append(item)
        if MIGU_RE.search(hay):
            migu_epl.append(item)

    # 如果源里明确标记了咪咕，就只保留咪咕；否则保留作者 Sport 中所有英超项，避免误删实际的咪咕代理链接。
    selected = migu_epl if migu_epl else epl

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    out = ["#EXTM3U", f"# MiGu EPL auto-filter; updated {stamp}"]
    for meta, extra, url in selected:
        out.append(meta)
        out.extend(extra)
        out.append(url)

    OUT.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"Sport entries={len(entries)}, EPL={len(epl)}, MiGu-EPL={len(migu_epl)}, selected={len(selected)}")


if __name__ == "__main__":
    main()
