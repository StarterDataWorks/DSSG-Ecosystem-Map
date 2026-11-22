"""Fetch the full Civic Tech Field Guide directory via the public export API."""
import json, time
from pathlib import Path
import requests

BASE = "https://civictech.guide/api/v1"
RAW = Path(__file__).resolve().parents[2] / "raw" / "ctfg"
UA = {"User-Agent": "civictech-unified/0.1 (research dataset builder)"}


def get(url, params=None, tries=8):
    for i in range(tries):
        r = requests.get(url, params=params, headers=UA, timeout=120)
        if r.status_code == 429:
            wait = int(r.headers.get("retry-after") or r.headers.get("ratelimit-reset") or 30)
            print(f"429, sleeping {wait}s"); time.sleep(wait + 1); continue
        if r.status_code >= 500:
            time.sleep(5 * (i + 1)); continue
        r.raise_for_status()
        return r
    raise RuntimeError(f"failed {url} {params}")


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    offset, limit, pages = 0, 1000, []
    while True:
        out = RAW / f"export_{offset:05d}.json"
        if out.exists():
            d = json.loads(out.read_text())
        else:
            r = get(f"{BASE}/projects/export", {"limit": limit, "offset": offset, "include": "raw_fields"})
            d = r.json(); out.write_text(json.dumps(d))
            rem = int(r.headers.get("ratelimit-remaining", 5))
            if rem <= 1:
                time.sleep(int(r.headers.get("ratelimit-reset", 60)) + 1)
        n, total = len(d["data"]), d["meta"]["total"]
        print(f"offset={offset} got={n} total={total}")
        pages.append(d)
        offset += n
        if n == 0 or offset >= total:
            break
    for ep in ["facets", "categories", "issues", "sdgs"]:
        p = RAW / f"{ep}.json"
        if not p.exists():
            try:
                p.write_text(get(f"{BASE}/{ep}").text)
            except Exception as e:
                print("facet fail", ep, e)
    # graveyard listing (HTML) for provenance of failed/sunset projects
    p = RAW / "graveyard.html"
    if not p.exists():
        try:
            p.write_text(get("https://civictech.guide/graveyard/").text)
        except Exception as e:
            print("graveyard fail", e)


if __name__ == "__main__":
    main()
