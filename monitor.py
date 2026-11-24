import hashlib, html, json, os, re, sys, time, urllib.parse, urllib.request
from pathlib import Path

BASE = "https://www.thenrai.in/"
STATE = Path("state.json")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36"


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def fetch(url: str) -> str:
    for attempt in range(1, 4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=25) as r:
                return r.read().decode(r.headers.get_content_charset() or "utf-8", errors="replace")
        except Exception as e:
            if attempt == 3:
                raise
            time.sleep(2 * attempt)


def parse(page: str) -> list[dict]:
    items, seen_ids = [], set()

    # 1. News & Events (#enve2)
    s = page.find('id="enve2"')
    e = page.find("news_events_details.aspx", s) if s != -1 else -1
    if s != -1:
        sec = page[s:e] if e != -1 else page[s:]
        for b in re.findall(r"<td[^>]*class=[\"']fo[\"'][^>]*>(.*?)</td>", sec, re.S | re.I):
            t = re.search(r"<h2[^>]*>(.*?)</h2>", b, re.S | re.I)
            if not t:
                continue
            title = clean(t.group(1))
            sp = re.search(r"<span[^>]*>(.*?)</span>", b, re.S | re.I)
            date = clean(sp.group(1)).rstrip(":").strip() if sp else ""
            hrefs = re.findall(r"href=[\"']([^\"']+)[\"']", b, re.I)
            href = next((u for u in hrefs if "details.aspx?view=" in u.lower()), hrefs[-1] if hrefs else "")
            url = urllib.parse.urljoin(BASE, href.strip()) if href else BASE
            m = re.search(r"view=(\d+)", url, re.I)
            iid = f"news:{m.group(1)}" if m else "news:" + hashlib.sha256(f"{url}|{title}".encode()).hexdigest()[:12]
            if title and iid not in seen_ids:
                seen_ids.add(iid)
                items.append({"id": iid, "cat": "News & Events", "title": title, "date": date, "url": url})

    # 2. Featured Notices (#DL_ftrNws)
    s2 = page.find('id="DL_ftrNws"')
    e2 = page.find("</table>", s2) if s2 != -1 else -1
    if s2 != -1:
        sec2 = page[s2:e2] if e2 != -1 else page[s2:]
        for c in re.findall(r'<div class="prr"[^>]*>(.*?)</div>\s*</td>', sec2, re.S | re.I):
            t = re.search(r'<div class="prr3"[^>]*>(.*?)</div>', c, re.S | re.I)
            if not t:
                continue
            title = clean(t.group(1))
            hrefs = re.findall(r"href=[\"']([^\"']+)[\"']", c, re.I)
            href = next((u for u in hrefs if "newsdetails.aspx" in u.lower()), hrefs[-1] if hrefs else "")
            url = urllib.parse.urljoin(BASE, href.strip()) if href else BASE
            m = re.search(r"view=(\d+)", url, re.I)
            iid = f"feat:{m.group(1)}" if m else "feat:" + hashlib.sha256(f"{url}|{title}".encode()).hexdigest()[:12]
            if title and iid not in seen_ids:
                seen_ids.add(iid)
                items.append({"id": iid, "cat": "Featured Notice", "title": title, "date": "", "url": url})

    return items


def notify(topic: str, title: str, body: str, url: str, tags: str = "loudspeaker,dart") -> None:
    safe_title = re.sub(r"[\r\n]+", " ", title.encode("ascii", "ignore").decode()).strip() or "NRAI Update"
    req = urllib.request.Request(
        f"https://ntfy.sh/{urllib.parse.quote(topic, safe='')}",
        data=body.encode("utf-8"),
        method="POST",
        headers={
            "Title": safe_title[:120],
            "Priority": "high",
            "Tags": tags,
            "Click": url,
            "Actions": f"view, Open Notice, {url}",
            "Content-Type": "text/plain; charset=utf-8",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        if r.status >= 300:
            raise RuntimeError(f"ntfy HTTP {r.status}")


def main() -> None:
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    if not topic:
        sys.exit("Error: NTFY_TOPIC secret is not set.")

    items = parse(fetch(BASE))
    if len(items) < 10:
        print(f"Skipping: only parsed {len(items)} items (site may be temporarily down).")
        return

    seen = set(json.loads(STATE.read_text("utf-8"))) if STATE.exists() else set()

    if not seen:
        STATE.write_text(json.dumps([i["id"] for i in items], indent=2) + "\n", "utf-8")
        latest = items[0]
        notify(
            topic,
            "NRAI Notifier Active",
            f"Watching {len(items)} items on thenrai.in.\nLatest: {latest['title']}",
            latest["url"],
            tags="white_check_mark,dart",
        )
        print(f"Initialized with {len(items)} items.")
        return

    new_items = [i for i in items if i["id"] not in seen]
    if not new_items:
        print("No new items.")
        return

    for item in reversed(new_items[:10]):
        msg = item["title"] + (f"\nPublished: {item['date']}" if item["date"] else "")
        notify(topic, f"NRAI {item['cat']}", msg, item["url"])
        time.sleep(0.5)

    all_ids = list(dict.fromkeys([i["id"] for i in items] + list(seen)))
    STATE.write_text(json.dumps(all_ids, indent=2) + "\n", "utf-8")
    print(f"Sent {min(len(new_items), 10)} notification(s).")


if __name__ == "__main__":
    main()
