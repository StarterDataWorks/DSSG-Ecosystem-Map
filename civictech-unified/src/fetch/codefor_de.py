"""Scrape Code for Germany project list + detail pages (codefor.de/projekte/alle/)."""
import json, re, time
from pathlib import Path
import requests
from bs4 import BeautifulSoup

RAW = Path(__file__).resolve().parents[2] / "raw" / "codefor_de"
UA = {"User-Agent": "Mozilla/5.0 (civictech-unified research dataset builder)"}
LIST = "https://codefor.de/projekte/alle/"


def fetch(url, path):
    if path.exists():
        return path.read_text()
    r = requests.get(url, headers=UA, timeout=60); r.raise_for_status()
    path.write_text(r.text); time.sleep(0.7)
    return r.text


def main():
    (RAW / "pages").mkdir(parents=True, exist_ok=True)
    s = BeautifulSoup(fetch(LIST, RAW / "alle.html"), "html.parser")
    out = []
    for c in s.select(".project-preview-card"):
        a = c.find("a", href=True)
        labs = [x for x in c.select(".lab-link") if x.get_text(strip=True)]
        rec = {
            "name": c.get("data-name"),
            "date": c.get("data-date"),
            "page_url": a["href"],
            "topics": [i.get("alt") for i in c.select(".tags img")],
            "teaser": (c.select_one(".description") or c).get_text(" ", strip=True),
            "labs": [x.get_text(strip=True) for x in labs],
            "lab_urls": [x.get("href") for x in labs if x.get("href")],
            "status": (c.select_one(".status").get_text(strip=True) if c.select_one(".status") else None),
        }
        slug = rec["page_url"].rstrip("/").split("/")[-1]
        d = BeautifulSoup(fetch(rec["page_url"], RAW / "pages" / f"{slug}.html"), "html.parser")
        m = d.find("main") or d.body
        links = {}
        for x in m.find_all("a", href=True):
            t = x.get_text(" ", strip=True).lower()
            if t in ("website", "webseite") and "website" not in links:
                links["website"] = x["href"]
            elif "github" in t or "gitlab" in t or "code" == t:
                links.setdefault("repository", x["href"])
        h = m.find(["h1", "h2"])
        # longest paragraph block = description
        paras = [p.get_text(" ", strip=True) for p in m.find_all("p")]
        rec.update(slug=slug, website=links.get("website"), repository=links.get("repository"),
                   description=max(paras, key=len) if paras else None,
                   contributors_count=len(m.select("a[href*='github.com/']")) )
        out.append(rec)
    (RAW / "projects.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(len(out), "projects")


if __name__ == "__main__":
    main()
