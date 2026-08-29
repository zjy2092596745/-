#!/usr/bin/env python3
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

SPORT_URL = "https://tv.iill.top/m3u/Sport"
MATCH_LIST_URL = "https://v0-sc.miguvideo.com/vms-match/v6/staticcache/basic/match-list/normal-match-list/0/all/default/1/miguvideo"
BASIC_DATA_URL = "https://vms-sc.miguvideo.com/vms-match/v6/staticcache/basic/basic-data/{mgdb_id}/miguvideo"
OUT = Path(__file__).with_name("migu-epl.m3u")
UA = "okhttp/3.15"
EPL_RE = re.compile(r"英超|英格兰(?:足球)?超级联赛|Premier\s+League|\bEPL\b", re.I)


def fetch_text(url, timeout=25):
    req = Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def fetch_json(url, timeout=20):
    return json.loads(fetch_text(url, timeout))


def parse_m3u(text):
    lines = [x.strip() for x in text.replace("\r", "").split("\n")]
    entries = []
    i = 0
    while i < len(lines):
        if not lines[i].startswith("#EXTINF"):
            i += 1
            continue
        meta = lines[i]
        extras = []
        stream = None
        i += 1
        while i < len(lines) and not lines[i].startswith("#EXTINF"):
            line = lines[i]
            if line:
                if line.startswith("#"):
                    extras.append(line)
                elif stream is None:
                    stream = line
                else:
                    extras.append(line)
            i += 1
        if stream:
            entries.append({"meta": meta, "extras": extras, "url": stream})
    return entries


def display_name(meta):
    return meta.rsplit(",", 1)[-1].strip() if "," in meta else meta


def replace_attr(meta, attr, value):
    q = re.compile(rf'{re.escape(attr)}="[^"]*"')
    token = f'{attr}="{value}"'
    if q.search(meta):
        return q.sub(token, meta)
    comma = meta.rfind(",")
    if comma >= 0:
        return meta[:comma] + " " + token + meta[comma:]
    return meta + " " + token


def rename_meta(meta, title):
    meta = replace_attr(meta, "group-title", "英超")
    meta = replace_attr(meta, "tvg-name", title)
    comma = meta.rfind(",")
    return (meta[:comma + 1] + title) if comma >= 0 else meta


def migu_epl_events():
    pid_titles = {}
    team_titles = []
    try:
        data = fetch_json(MATCH_LIST_URL)
    except Exception as e:
        print(f"MiGu match list unavailable: {e}")
        return pid_titles, team_titles

    body = data.get("body") or {}
    match_map = body.get("matchList") or {}
    for _, matches in match_map.items():
        for match in matches or []:
            competition = str(match.get("competitionName") or "")
            if not EPL_RE.search(competition):
                continue
            mgdb_id = match.get("mgdbId")
            teams = match.get("confrontTeams") or []
            if len(teams) >= 2:
                matchup = f"{teams[0].get('name','')} VS {teams[1].get('name','')}".strip()
                t1 = str(teams[0].get("name") or "").strip()
                t2 = str(teams[1].get("name") or "").strip()
                if t1 and t2:
                    team_titles.append((t1, t2, matchup))
            else:
                matchup = str(match.get("pkInfoTitle") or "英超")
            if not mgdb_id:
                continue
            try:
                detail = fetch_json(BASIC_DATA_URL.format(mgdb_id=mgdb_id))
                dbody = detail.get("body") or {}
                live_list = (((dbody.get("multiPlayList") or {}).get("liveList")) or [])
                for live in live_list:
                    pid = str(live.get("pID") or "").strip()
                    if not pid:
                        continue
                    live_name = str(live.get("name") or "直播").strip()
                    start = str(live.get("startTimeStr") or "")
                    hm = start[11:16] if len(start) >= 16 else ""
                    parts = ["英超", matchup]
                    if live_name:
                        parts.append(live_name)
                    if hm:
                        parts.append(hm)
                    pid_titles[pid] = "｜".join(parts)
            except Exception as e:
                print(f"MiGu detail {mgdb_id} unavailable: {e}")
    return pid_titles, team_titles


def main():
    try:
        sport_text = fetch_text(SPORT_URL)
    except Exception as e:
        print(f"Sport source unavailable: {e}", file=sys.stderr)
        sys.exit(1)

    entries = parse_m3u(sport_text)
    pid_titles, team_titles = migu_epl_events()
    selected = []
    seen = set()

    for entry in entries:
        hay = f"{entry['meta']} {entry['url']} {' '.join(entry['extras'])}"
        title = None

        for pid, event_title in pid_titles.items():
            if pid in hay:
                title = event_title
                break

        if title is None and EPL_RE.search(entry["meta"]):
            title = display_name(entry["meta"])

        if title is None:
            low = hay.casefold()
            for t1, t2, matchup in team_titles:
                if t1.casefold() in low and t2.casefold() in low:
                    title = f"英超｜{matchup}"
                    break

        if title is None:
            continue

        key = (title, entry["url"])
        if key in seen:
            continue
        seen.add(key)
        entry["meta"] = rename_meta(entry["meta"], title)
        selected.append(entry)

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    out = ["#EXTM3U", f"# Auto-filtered EPL list; updated {stamp}"]
    for entry in selected:
        out.append(entry["meta"])
        out.extend(entry["extras"])
        out.append(entry["url"])

    OUT.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"Wrote {len(selected)} EPL entries to {OUT}")


if __name__ == "__main__":
    main()
