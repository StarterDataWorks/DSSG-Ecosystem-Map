"""Cross-source deduplication with union-find + merge of clusters into unified records."""
import collections, json, itertools, re
from rapidfuzz import fuzz
from common import canon_url, reg_domain, norm_name, uniq, stable_id, GENERIC_HOSTS, clean_text

SOURCE_PRIORITY = ["CTFG", "HIIG", "CodeForDE", "CivicDataLab", "CivicTechFundAfrica", "HackCorruption", "Awesome-Civic-Tech"]
GENERIC_NAMES = {"app", "website", "platform", "project", "map", "dashboard", "hackathon", "open data", "open data day",
                 "data", "tool", "petition", "chatbot", "ki", "ai", "index", "portal", "toolkit", "the project"}


class UF:
    def __init__(self, recs):
        self.p = list(range(len(recs)))
        self.src = [{r["source"]} for r in recs]
        self.names = [{(r["source"], r["_nn"])} for r in recs]
        self.how = collections.Counter()

    def find(self, i):
        while self.p[i] != i:
            self.p[i] = self.p[self.p[i]]; i = self.p[i]
        return i

    def union(self, a, b, how, allow_same_source=False):
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return False
        shared = self.src[ra] & self.src[rb]
        if shared and not allow_same_source:
            return False
        for s in shared:  # same-source records may only join if they carry the same normalized name
            if not {n for src, n in self.names[ra] if src == s} & {n for src, n in self.names[rb] if src == s}:
                return False
        self.p[rb] = ra; self.src[ra] |= self.src[rb]; self.names[ra] |= self.names[rb]; self.how[how] += 1
        return True


def name_sim(a, b):
    return max(fuzz.token_sort_ratio(a, b), fuzz.ratio(a, b))


def contains(a, b):
    return len(a) >= 4 and len(b) >= 4 and (re.search(rf"\b{re.escape(a)}\b", b) or re.search(rf"\b{re.escape(b)}\b", a))


def prepare(recs):
    for r in recs:
        r["_nn"] = norm_name(r["name"])
        keys, hosts = set(), set()
        for u in [r.get("url"), r.get("repository_url")] + ([r["source_url"]] if r["source"] in ("CodeForDE", "CivicDataLab") else []):
            fu, ck, host = canon_url(u)
            if ck:
                keys.add(ck)
                if u == r.get("url") and host:
                    hosts.add(host)
        r["_keys"] = keys
        r["_rd"] = {reg_domain(h) for h in hosts if h not in GENERIC_HOSTS and reg_domain(h) not in GENERIC_HOSTS}
        r["_org"] = norm_name(r.get("organization") or "")
    # URL keys that are shared by >3 records of one source are generic (e.g. a listing homepage) -> drop
    cnt = collections.Counter((r["source"], k) for r in recs for k in r["_keys"])
    for r in recs:
        r["_keys"] = {k for k in r["_keys"] if cnt[(r["source"], k)] <= 3 and "/" in k or (cnt[(r["source"], k)] <= 1 and k.split("/")[0] not in GENERIC_HOSTS)}


def countries_ok(a, b):
    return not a["country"] or not b["country"] or a["country"] == b["country"]


def cluster(recs):
    prepare(recs)
    uf = UF(recs)
    # pass 1: same canonical URL + exactly the same normalized name (allowed within one source = true duplicates)
    by_key = collections.defaultdict(list)
    for i, r in enumerate(recs):
        for k in r["_keys"]:
            by_key[k].append(i)
    for k, idx in by_key.items():
        for a, b in itertools.combinations(idx, 2):
            if recs[a]["_nn"] and recs[a]["_nn"] == recs[b]["_nn"]:
                uf.union(a, b, "url+exact_name", allow_same_source=True)
    # pass 2: same canonical URL + similar name (cross-source)
    for k, idx in by_key.items():
        for a, b in itertools.combinations(idx, 2):
            na, nb = recs[a]["_nn"], recs[b]["_nn"]
            if name_sim(na, nb) >= 80 or fuzz.token_set_ratio(na, nb) >= 95 or contains(na, nb):
                uf.union(a, b, "url+similar_name")
    # pass 3: exact normalized name, compatible country, and not contradicting domains
    by_name = collections.defaultdict(list)
    for i, r in enumerate(recs):
        if len(r["_nn"]) >= 5 and r["_nn"] not in GENERIC_NAMES:
            by_name[r["_nn"]].append(i)
    for n, idx in by_name.items():
        if len(idx) > 6:  # very common names -> too ambiguous
            continue
        for a, b in itertools.combinations(idx, 2):
            ra, rb = recs[a], recs[b]
            if not countries_ok(ra, rb):
                continue
            same_dom = bool(ra["_rd"] & rb["_rd"])
            no_conflict = not ra["_rd"] or not rb["_rd"]
            if same_dom or (no_conflict and (len(n) >= 8 or ra["country"] == rb["country"] is not None)):
                uf.union(a, b, "exact_name", allow_same_source=same_dom)
    # pass 4: same registered domain + fuzzy name
    by_dom = collections.defaultdict(list)
    for i, r in enumerate(recs):
        for d in r["_rd"]:
            by_dom[d].append(i)
    for d, idx in by_dom.items():
        if len(idx) > 60:
            continue
        for a, b in itertools.combinations(idx, 2):
            if name_sim(recs[a]["_nn"], recs[b]["_nn"]) >= 85:
                uf.union(a, b, "domain+fuzzy_name")
    # pass 5: fuzzy name + same organization (URLs differ or missing)
    by_org = collections.defaultdict(list)
    for i, r in enumerate(recs):
        if len(r["_org"]) >= 3:
            by_org[r["_org"][:12]].append(i)
    for o, idx in by_org.items():
        if len(idx) > 300:
            continue
        for a, b in itertools.combinations(idx, 2):
            ra, rb = recs[a], recs[b]
            if fuzz.token_set_ratio(ra["_org"], rb["_org"]) >= 85 and name_sim(ra["_nn"], rb["_nn"]) >= 92 and countries_ok(ra, rb):
                uf.union(a, b, "org+fuzzy_name")
    # pass 6: fuzzy name (very high) when one side has no URL at all (e.g. CTF Africa, HackCorruption ideas)
    nourl = [i for i, r in enumerate(recs) if not r["_keys"] and len(r["_nn"]) >= 5]
    blocks = collections.defaultdict(list)
    for i, r in enumerate(recs):
        if len(r["_nn"]) >= 5:
            blocks[r["_nn"][:4]].append(i)
    for a in nourl:
        for b in blocks[recs[a]["_nn"][:4]]:
            if a != b and countries_ok(recs[a], recs[b]) and name_sim(recs[a]["_nn"], recs[b]["_nn"]) >= 95 and recs[a]["_nn"] not in GENERIC_NAMES:
                uf.union(a, b, "fuzzy_name_no_url")
    groups = collections.defaultdict(list)
    for i in range(len(recs)):
        groups[uf.find(i)].append(i)
    return list(groups.values()), uf.how


GERMAN_SOURCES = {"CivicDataLab", "CodeForDE"}
LIST_FIELDS = ["countries", "geographic_focus", "sdgs", "categories", "issues", "tags", "technologies", "ai_technology", "project_type"]
SCALAR_FIELDS = ["url", "url_flag", "repository_url", "status", "org_type", "organization", "city", "country", "region",
                 "funding", "open_source", "open_source_license", "start_year", "end_year", "impact", "notes", "language"]


def merge(recs, groups):
    out, membership = [], []
    for g in groups:
        rs = sorted((recs[i] for i in g), key=lambda r: (SOURCE_PRIORITY.index(r["source"]), r["source_id"]))
        top = rs[0]
        m = {}
        ctfg = [r for r in rs if r["source"] == "CTFG"]
        m["name"] = top["name"]
        # richest description, preferring the English-language sources; keep the richest German one separately
        descs = [r for r in rs if r["description"]]
        en = [r for r in descs if r["source"] not in GERMAN_SOURCES and len(r["description"]) >= 80]
        best = max(en or descs, key=lambda r: len(r["description"]), default=None)
        m["description"] = best["description"] if best else None
        de = [r["description"] for r in descs if r["source"] in GERMAN_SOURCES and r["description"] != m["description"]]
        m["description_de"] = max(de, key=len) if de else None
        for f in SCALAR_FIELDS:
            vals = [r[f] for r in rs if r[f] not in (None, "", "unknown", "unsure")]
            m[f] = vals[0] if vals else ("unknown" if f == "status" else "unsure" if f == "org_type" else None)
        # prefer a reachable/ok URL that is not just a directory listing page
        cands = [r for r in rs if r["url"] and r["url_flag"] in ("ok", "fixed")]
        nonlisting = [r for r in cands if (canon_url(r["url"])[2] or "") not in ("civic-coding.de", "codefor.de", "huggingface.co")]
        pick = (nonlisting or cands or [r for r in rs if r["url"]] or [None])[0]
        m["url"], m["url_flag"] = (pick["url"], pick["url_flag"]) if pick else (None, "missing")
        if m["url_flag"] == "ok" and any(r["url_flag"] == "unreachable" and canon_url(r["url"])[1] == canon_url(m["url"])[1] for r in rs):
            m["url_flag"] = "unreachable"
        for f in LIST_FIELDS:
            m[f] = uniq([x for r in rs for x in (r[f] or [])])
        if len(m["ai_technology"]) > 1 and "Artificial Intelligence (general)" in m["ai_technology"]:
            m["ai_technology"].remove("Artificial Intelligence (general)")
        m["ai_related"] = bool(m["ai_technology"])
        if m["country"] and m["country"] not in m["countries"]:
            m["countries"].insert(0, m["country"])
        m["id"] = ctfg[0]["source_id"] if ctfg else stable_id(m["name"], m["url"])
        m["ctfg_slug"] = ctfg[0]["source_id"] if ctfg else None
        m["sources"] = uniq(r["source"] for r in rs)
        m["n_sources"] = len(m["sources"])
        m["source_ids"] = [r["source_id"] for r in rs]
        m["source_urls"] = uniq(r["source_url"] for r in rs)
        m["alt_names"] = uniq(r["name"] for r in rs if r["name"] != m["name"])
        m["status_raw"] = uniq(f"{r['source']}: {r['status_raw']}" for r in rs if r["status_raw"])
        m["raw_fields"] = json.dumps({r["source_id"]: json.loads(r["raw_fields"]) if r["raw_fields"] else None for r in rs},
                                     ensure_ascii=False)
        out.append(m)
        for r in rs:
            membership.append({"id": m["id"], "source": r["source"], "source_id": r["source_id"], "name": r["name"]})
    # guarantee unique ids
    seen = collections.Counter()
    for m in out:
        seen[m["id"]] += 1
        if seen[m["id"]] > 1:
            m["id"] = f"{m['id']}-{seen[m['id']]}"
    return out, membership
