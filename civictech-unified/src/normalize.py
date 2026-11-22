"""Per-source normalizers -> list of dicts in the common (pre-merge) schema."""
import ast, glob, json, re
import pandas as pd
from bs4 import BeautifulSoup
from common import (RAW, clean_text, as_list, uniq, fix_url, norm_country, norm_countries, norm_status,
                    norm_org_type, norm_open_source, norm_sdgs, ai_tags, city_from_lab)

FIELDS = ["source", "source_id", "source_url", "name", "description", "url", "url_flag", "repository_url",
          "status", "status_raw", "org_type", "org_type_raw", "organization", "city", "country", "countries",
          "region", "geographic_focus", "sdgs", "categories", "issues", "tags", "technologies", "ai_technology",
          "project_type", "funding", "open_source", "open_source_license", "start_year", "end_year", "impact",
          "notes", "language", "raw_fields"]


def year(v):
    m = re.search(r"(19[5-9]\d|20[0-4]\d)", str(v or ""))
    return int(m.group(1)) if m else None


def rec(**kw):
    r = {f: None for f in FIELDS}
    r.update(kw)
    for f in ["countries", "geographic_focus", "sdgs", "categories", "issues", "tags", "technologies", "project_type"]:
        r[f] = uniq(r[f] or [])
    urls = re.findall(r"(?:https?://|www\.)[^\s,;]+", str(r["url"] or ""))
    if len(urls) > 1:
        repo = next((u for u in urls if "github.com" in u or "gitlab.com" in u), None)
        r["repository_url"] = r["repository_url"] or repo
        r["url"] = next((u for u in urls if u != repo), urls[0])
        r["url"], _ = fix_url(r["url"]); r["url_flag"] = "fixed"
    else:
        r["url"], r["url_flag"] = fix_url(r["url"])
    if r["repository_url"]:
        r["repository_url"] = fix_url(r["repository_url"])[0]
    if r["countries"] and not r["country"]:
        r["country"] = r["countries"][0]
    if r["country"] and r["country"] not in r["countries"]:
        r["countries"] = [r["country"]] + r["countries"]
    r["ai_technology"] = uniq((r["ai_technology"] or []) + ai_tags(
        r["name"], r["description"], " ; ".join(r["categories"] + r["tags"] + r["technologies"])))
    if len(r["ai_technology"]) > 1 and "Artificial Intelligence (general)" in r["ai_technology"]:
        r["ai_technology"].remove("Artificial Intelligence (general)")
    r["raw_fields"] = json.dumps(r["raw_fields"] or {}, ensure_ascii=False, default=str)
    return r


# ---------------------------------------------------------------- CTFG
CTFG_DROP_RAW = {"Images", "Images (file)", "File (from Images) 2", "Upload image(s)", "Images (from Parent organization(s))",
                 "feeling lucky formula", "Number of integrations", "Categories 3", "Logo URL", "Image url"}


def ctfg():
    out = []
    for f in sorted(glob.glob(str(RAW / "ctfg" / "export_*.json"))):
        for r in json.load(open(f))["data"]:
            rf, ln = r.get("raw_fields") or {}, r.get("linked_names") or {}
            res = lambda k: [ln.get(x, x) for x in (rf.get(k) or [])] if isinstance(rf.get(k), list) else as_list(rf.get(k))
            cats = r.get("categories") or []
            graveyard = "Graveyard" in cats
            stage = clean_text(rf.get("Project stage"))
            status = "failed/sunset" if graveyard else norm_status(r.get("status_raw"))
            if status == "active" and stage and norm_status(stage) == "prototype":
                status = "prototype"
            loc = r.get("location") or {}
            country = norm_country(loc.get("country")) or next(iter(norm_countries(res("Country (from Headquarters Location)"))), None)
            longer = clean_text(rf.get("Longer description"))
            short = clean_text(r.get("description") or rf.get("1-liner"))
            desc = longer if longer and len(longer) > len(short or "") else short
            raw = {k: v for k, v in rf.items() if k not in CTFG_DROP_RAW}
            out.append(rec(
                source="CTFG", source_id=r["slug"],
                source_url=rf.get("Field Guide Directory URL") or f"https://civictech.guide/listing/{r['slug']}",
                name=clean_text(r.get("title")), description=desc,
                url=r.get("url") or (r.get("socials") or {}).get("website"),
                repository_url=r.get("repository_url") or rf.get("Github URL"),
                status=status, status_raw=("Graveyard; " if graveyard else "") + str(r.get("status_raw")),
                org_type=norm_org_type(r.get("organizationType")), org_type_raw="; ".join(r.get("organizationType") or []) or None,
                organization=clean_text(rf.get("Parent organization(s)")),
                city=clean_text(rf.get("City (from Headquarters Location)")), country=country,
                region=next(iter(res("Continent")), None) or (clean_text(loc.get("country")) if not country and loc.get("country") else None),
                geographic_focus=as_list(rf.get("Geo. focus country"), r"[;|]") + res("Political unit"),
                sdgs=norm_sdgs(res("SDGs")), categories=cats, issues=res("Issues"),
                tags=r.get("tags") or [], technologies=res("Platforms"), project_type=r.get("projectTypes") or [],
                funding="; ".join(uniq(res("Funding_funded_by_who (from Funding)"))) or None,
                open_source=norm_open_source(rf.get("Open source?"), rf.get("Open source")),
                open_source_license=clean_text(rf.get("Open source license")),
                start_year=year(rf.get("Founded") or rf.get("Founded (number)") or r.get("founded")), end_year=year(rf.get("Closed")),
                impact=" | ".join(uniq(as_list(rf.get("Impact_impact_statement (from Impact)"), r"\|"))) or None,
                notes="; ".join(x for x in [clean_text(rf.get("If shut down, what happened?")) and f"Shutdown: {clean_text(rf.get('If shut down, what happened?'))}",
                                             clean_text(rf.get("Postmortem")) and f"Postmortem: {clean_text(rf.get('Postmortem'))}"] if x) or None,
                language=clean_text(r.get("language")), raw_fields=raw))
    return out


# ---------------------------------------------------------------- HIIG
def hiig():
    rows = []
    for fname, demo in [("public_interest_ai_projects_2024.xlsx", False), ("public_interest_ai_projects_2024_democracy.xlsx", True)]:
        for sheet in ["NetworkSearch", "GoogleSearch"]:
            d = pd.read_excel(RAW / "hiig" / fname, sheet_name=sheet)
            d.columns = [c.strip() for c in d.columns]
            d = d.rename(columns={"SDGCategory1": "SDG Category1", "SDGCategory2": "SDG Category2"})
            for i, x in d.iterrows():
                x = {k: (None if (isinstance(v, float) and v != v) else v) for k, v in x.items()}
                if not clean_text(x.get("Name")):
                    continue
                x["_table"] = "Connected to democracy" if demo else "Public Interest AI Projects"
                x["_sheet"] = sheet
                rows.append(x)
    # merge the democracy subset into the main table (same project listed twice)
    by = {}
    for x in rows:
        k = (clean_text(x["Name"]).lower(), (clean_text(x.get("Link")) or "").lower().rstrip("/"))
        if k in by:
            by[k]["_tables"].add(x["_table"]); by[k]["_sheets"].add(x["_sheet"])
            for kk, vv in x.items():
                if by[k].get(kk) is None and vv is not None:
                    by[k][kk] = vv
        else:
            x["_tables"], x["_sheets"] = {x["_table"]}, {x["_sheet"]}
            by[k] = x
    out = []
    for x in by.values():
        tables = sorted(x.pop("_tables")); sheets = sorted(x.pop("_sheets"))
        x.pop("_table"); x.pop("_sheet")
        x["tables"], x["sheets"] = tables, sheets
        countries = norm_countries(x.get("Country-LegalBase"))
        region_raw = clean_text(x.get("Region-ProjectActivity"))
        out.append(rec(
            source="HIIG", source_id=f"hiig:{clean_text(x['Name'])}",
            source_url="https://huggingface.co/datasets/hiig-ai-lab/publicinterest-ai-projects",
            name=clean_text(x["Name"]), description=clean_text(x.get("Description")), url=x.get("Link"),
            status=norm_status(x.get("ActivityStatus")), status_raw=clean_text(x.get("ActivityStatus")),
            org_type=norm_org_type(x.get("For-or-NonProfit")), org_type_raw=clean_text(x.get("For-or-NonProfit")),
            organization=clean_text(x.get("ProjectOwner")), city=clean_text(x.get("City")), countries=countries,
            region=None if (region_raw or "").lower() in ("unclear", "unkown", "unknown") else region_raw,
            geographic_focus=as_list(region_raw, r"[;,/]"),
            sdgs=norm_sdgs([x.get("SDG Category1"), x.get("SDG Category2")]),
            categories=["Connected to democracy"] if "Connected to democracy" in tables else [],
            tags=[t.lstrip("#") for t in as_list(x.get("Hashtags"), r"[;,\s]+") if t.strip("#")],
            technologies=as_list(x.get("AI/Technology")), ai_technology=["Artificial Intelligence (general)"],
            funding=clean_text(x.get("Funding")), start_year=year(x.get("StartingYear")),
            notes=f"HIIG search: {x.get('SearchPhrase')}" if x.get("SearchPhrase") else None, raw_fields=x))
    return out


# ---------------------------------------------------------------- Civic Data Lab
GERMAN_SOURCES = ("civic-coding.de", "codefor.de", "correlaid.org", "ok-lab-karlsruhe.de", "civic-innovation.de",
                  "mi4people.org", "awo.org", "drk-wohlfahrt.de", "civic-data.de", "dajeb.de")


def _pylist(v):
    v = clean_text(v)
    if not v:
        return []
    try:
        x = ast.literal_eval(v)
        return [clean_text(i) for i in x if clean_text(i)] if isinstance(x, (list, tuple)) else [v]
    except Exception:
        return as_list(v)


def civicdatalab():
    d = pd.read_csv(RAW / "civicdatalab" / "data.csv", sep=";", dtype=str)
    try:
        bad = pd.read_csv(RAW / "civicdatalab" / "unreachable_websites.csv", dtype=str, sep=None, engine="python")
        bad_urls = {u.strip().rstrip("/").lower() for c in bad.columns for u in bad[c].dropna() if str(u).startswith("http")}
    except Exception:
        bad_urls = set()
    out = []
    for i, x in d.iterrows():
        x = {k: clean_text(v) for k, v in x.items()}
        if not x.get("projektname"):
            continue
        q = x.get("quelle") or ""
        german = any(g in q for g in GERMAN_SOURCES)
        orgs = as_list(x.get("organisation"), r",")
        city = next((c for c in (city_from_lab(o) for o in orgs) if c), None)
        r = rec(source="CivicDataLab", source_id=f"cdl:{i}", source_url=q or "https://civic-data.de/machen/projektsammlung/",
                name=x["projektname"], description=x.get("kurzzusammenfassung"), url=x.get("webseite_link") or q,
                status=norm_status(x.get("status")), status_raw=x.get("status"),
                org_type="unsure", organization=x.get("organisation"), city=city,
                country="Germany" if german else None, region="Europe" if german else None,
                categories=_pylist(x.get("einsatzbereich")), technologies=_pylist(x.get("art")),
                open_source="yes" if "Open-Source-Software" in _pylist(x.get("art")) else None,
                language="German" if german else None, raw_fields=x)
        if r["url"] and r["url"].rstrip("/").lower() in bad_urls:
            r["url_flag"] = "unreachable"
        out.append(r)
    return out


# ---------------------------------------------------------------- Code for Germany
def codefor_de():
    out = []
    for x in json.load(open(RAW / "codefor_de" / "projects.json")):
        labs = x.get("labs") or []
        out.append(rec(
            source="CodeForDE", source_id=f"codefor:{x['slug']}", source_url=x["page_url"], name=clean_text(x["name"]),
            description=clean_text(x.get("description")) or clean_text(x.get("teaser")),
            url=x.get("website") or x.get("repository") or x["page_url"], repository_url=x.get("repository"),
            status=norm_status(x.get("status")), status_raw=x.get("status"), org_type="non-profit",
            organization=", ".join(labs + ["Code for Germany"]) if labs else "Code for Germany",
            city=next((c for c in (city_from_lab(l) for l in labs) if c), None), country="Germany", region="Europe",
            categories=x.get("topics") or [], start_year=year(x.get("date")),
            open_source="yes" if x.get("repository") else None, language="German", raw_fields=x))
    return out


# ---------------------------------------------------------------- Civic Tech Fund Africa
COHORTS = {"pilot": "AUCTF pilot", "sadc": "Regional SADC", "southern": "Southern Africa national", "west": "West Africa"}


def ctfafrica():
    s = BeautifulSoup(open(RAW / "ctfafrica" / "projects_en.html").read(), "html.parser")
    out = []
    for a in s.select("article.initiative-card"):
        org = a.select_one(".initiative-org")
        desc = org.find_next_sibling("p") if org else None
        dtype = clean_text(a.select_one(".document-type").get_text(" ")) if a.select_one(".document-type") else ""
        theme = dtype.split("/", 1)[1].strip() if "/" in dtype else a.get("data-theme")
        details = [clean_text(p.get_text(" ")) for p in a.select("details p")]
        cohort = a.get("data-cohort")
        raw = {"id": a.get("id"), "country": a.get("data-country"), "theme": a.get("data-theme"),
               "cohort": cohort, "document_type": dtype, "details": details,
               "practical_application": (a.select_one("a.text-link") or {}).get("href")}
        out.append(rec(
            source="CivicTechFundAfrica", source_id=f"ctfa:{a.get('id')}",
            source_url=f"https://civictechfund.africa/projects/#{a.get('id')}",
            name=clean_text(a.find("h2").get_text(" ")), description=clean_text(desc.get_text(" ")) if desc else None,
            url=None, status="unknown", status_raw="Documented May 2024", org_type="unsure",
            organization=clean_text(org.get_text(" ")) if org else None, countries=norm_countries(a.get("data-country")),
            region="Africa", categories=[theme] if theme else [],
            funding=f"Civic Tech Fund Africa / Charter Project Africa ({COHORTS.get(cohort, cohort)})",
            start_year=None, notes="Documented in the Charter Project Africa booklet (May 2024); does not certify present operation.",
            raw_fields=raw))
    return out


# ---------------------------------------------------------------- HackCorruption
HC_EVENTS = {
    "malaysia": ("HackCorruption Malaysia 2024 winner", "Southeast Asia", 2024),
    "colombia": ("HackCorruption Colombia 2023 winner", "Latin America", 2023),
    "announces-5": ("HackCorruption South Africa 2022 winner", "Southern & East Africa", 2022),
}


def hackcorruption():
    out = []
    s = BeautifulSoup(open(RAW / "hackcorruption" / "home.html").read(), "html.parser")
    for d in s.select("div.fusion-text"):
        h = d.find("h4"); a = h.find("a", href=True) if h else None
        if not h or not a or not d.find("p"):
            continue
        name = clean_text(h.get_text(" "))
        out.append(rec(source="HackCorruption", source_id=f"hc:{name}", source_url="https://hackcorruption.org/",
                       name=name, description=clean_text(d.find("p").get_text(" ")), url=a["href"],
                       status="active", status_raw="Featured tool on hackcorruption.org", org_type="unsure",
                       categories=["Anti-corruption"], countries=norm_countries(re.findall(r"in ([A-Z][a-z]+(?: and [A-Z][a-z]+)?)", d.get_text(" "))[:1]),
                       raw_fields={"page": "home"}))
    posts = json.load(open(RAW / "hackcorruption" / "accountabilitylab_posts.json"))
    for p in posts:
        ev = next((v for k, v in HC_EVENTS.items() if k in p["link"]), None)
        if not ev:
            continue
        label, region, yr = ev
        soup = BeautifulSoup(p["content"]["rendered"], "html.parser")
        found = []
        for b in soup.find_all("b"):
            t = clean_text(b.get_text(" ")) or ""
            m = re.match(r"^(\d+)\.\s*(.+?)\s*:?\s*$", t)
            if not m:
                continue
            name = re.sub(r"\s*\(Transnational\)\s*", "", m.group(2)).strip(" :")
            desc = []
            for sib in b.next_siblings:
                if getattr(sib, "name", None) in ("b", "ul", "div") or (getattr(sib, "name", None) and sib.find("b")):
                    break
                txt = clean_text(sib.get_text(" ") if hasattr(sib, "get_text") else str(sib))
                if txt and not txt.lower().startswith("members"):
                    desc.append(txt)
            dtxt = clean_text(" ".join(desc)).lstrip(": ") if desc else None
            found.append((name, dtxt if dtxt and len(dtxt) > 15 else None, "(Transnational)" in t))
        if not found:  # prose press release: "The winning teams include A, B, C and D."
            text = soup.get_text(" ")
            m = re.search(r"winning teams include ([^.]+)\.", text)
            names = [n.strip() for n in re.split(r",| and ", m.group(1)) if n.strip()] if m else []
            sents = re.split(r"(?<=[.!?])\s+|, while ", clean_text(text))
            for n in names:
                ds = [x for x in sents if n in x and "winning teams include" not in x]
                found.append((n, ds[0] if ds else None, False))
        for name, desc, trans in found:
            out.append(rec(source="HackCorruption", source_id=f"hc:{name}", source_url=p["link"], name=name,
                           description=desc, url=None, status="prototype", status_raw=label, org_type="unsure",
                           region=region, categories=["Anti-corruption", "Hackathon project"], start_year=yr,
                           notes=label + ("; transnational" if trans else ""),
                           raw_fields={"post": p["link"], "event": label}))
    # one project may appear on the homepage and in a winners post
    by = {}
    for r in out:
        k = r["name"].lower().replace("á", "a")
        if k in by:
            o = by[k]
            for f, v in r.items():
                if not o.get(f) and v:
                    o[f] = v
        else:
            by[k] = r
    return list(by.values())


# ---------------------------------------------------------------- Awesome lists
def awesome():
    out = []
    skip = {"contents", "related awesome lists", "contributing", "license", "general resources"}
    for fname, repo in [("brandonhimpfen_awesome-civic-tech.md", "brandonhimpfen/awesome-civic-tech"),
                        ("sllvn_awesome-civic-tech.md", "sllvn/awesome-civic-tech")]:
        section, cur = None, None
        for line in open(RAW / "awesome" / fname, encoding="utf-8"):
            h = re.match(r"^#{1,3}\s+(.+)", line)
            if h:
                section = h.group(1).strip(); continue
            if section is None or section.lower() in skip:
                continue
            m = re.match(r"^\s*[-*]\s+\[\**(.+?)\**\]\((\S+?)\)\s*(?:[–—:-]\s*|is |are |allows |helps )?(.*)", line)
            if m:
                name, url, desc = m.group(1).strip(), m.group(2), clean_text(m.group(3))
                if re.match(r"^(is|are|allows|helps)\b", line.split(")", 1)[-1].strip()):
                    desc = clean_text(line.split(")", 1)[-1].strip())
                cur = rec(source="Awesome-Civic-Tech", source_id=f"awesome:{repo}:{name}",
                          source_url=f"https://github.com/{repo}", name=name.replace("(archived)", "").strip(),
                          description=desc, url=url, status="inactive" if "archived" in name.lower() else "unknown",
                          status_raw="archived" if "archived" in name.lower() else None, org_type="unsure",
                          categories=[section], raw_fields={"list": repo, "section": section})
                out.append(cur); continue
            src = re.match(r"^\s+Source:\s*(\S+)", line)
            if src and cur:
                cur["repository_url"] = src.group(1); cur["open_source"] = "yes"
    return out


SOURCES = {"CTFG": ctfg, "HIIG": hiig, "CodeForDE": codefor_de, "CivicDataLab": civicdatalab,
           "CivicTechFundAfrica": ctfafrica, "HackCorruption": hackcorruption, "Awesome-Civic-Tech": awesome}


def load_all():
    allr = []
    for name, fn in SOURCES.items():
        rs = fn()
        print(f"{name:20s} {len(rs):6d} records")
        allr += rs
    return allr


if __name__ == "__main__":
    import collections
    for name, fn in SOURCES.items():
        if name == "CodeForDE" and not (RAW / "codefor_de" / "projects.json").exists():
            continue
        rs = fn()
        print(name, len(rs), collections.Counter(r["status"] for r in rs).most_common(), collections.Counter(r["url_flag"] for r in rs).most_common())
        print("  e.g.", {k: rs[0][k] for k in ["name", "url", "country", "city", "region", "org_type", "sdgs", "technologies", "ai_technology"]})
