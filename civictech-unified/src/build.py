"""Build the unified dataset: normalize all sources, deduplicate, export, write stats."""
import collections, json, sqlite3, sys, time
import pandas as pd
from common import UNIFIED, STATUS_VALUES
from normalize import load_all
from dedup import cluster, merge, SOURCE_PRIORITY

COLUMNS = ["id", "ctfg_slug", "name", "alt_names", "description", "description_de", "url", "url_flag", "repository_url", "status",
           "status_raw", "org_type", "organization", "city", "country", "countries", "region", "geographic_focus",
           "sdgs", "categories", "issues", "tags", "technologies", "ai_technology", "ai_related", "project_type",
           "funding", "open_source", "open_source_license", "start_year", "end_year", "impact", "notes", "language",
           "sources", "n_sources", "source_ids", "source_urls", "raw_fields"]
LIST_COLS = ["alt_names", "status_raw", "countries", "geographic_focus", "sdgs", "categories", "issues", "tags",
             "technologies", "ai_technology", "project_type", "sources", "source_ids", "source_urls"]


def main():
    t0 = time.time()
    recs = load_all()
    recs = [r for r in recs if r["name"] and (r["description"] or r["url"] or r["organization"])]
    n_in = len(recs)
    groups, how = cluster(recs)
    unified, membership = merge(recs, groups)
    fix_regions(unified, recs)
    df = pd.DataFrame(unified)[COLUMNS].sort_values(["n_sources", "name"], ascending=[False, True]).reset_index(drop=True)
    for c in ["start_year", "end_year"]:
        df[c] = df[c].astype("Int64")
    UNIFIED.mkdir(exist_ok=True)
    df.to_parquet(UNIFIED / "civictech_unified.parquet", index=False)
    df.to_json(UNIFIED / "civictech_unified.jsonl", orient="records", lines=True, force_ascii=False)
    with open(UNIFIED / "civictech_unified.json", "w") as f:
        json.dump(json.loads(df.drop(columns=["raw_fields"]).to_json(orient="records", force_ascii=False)), f, ensure_ascii=False)
    flat = df.drop(columns=["raw_fields"]).copy()
    for c in LIST_COLS:
        flat[c] = flat[c].map(lambda v: " | ".join(map(str, v)) if isinstance(v, list) else v)
    flat.to_csv(UNIFIED / "civictech_unified.csv", index=False)
    mem = pd.DataFrame(membership)
    mem.to_csv(UNIFIED / "source_membership.csv", index=False)
    # SQLite: projects (lists as JSON text) + project_sources link table
    db = UNIFIED / "civictech_unified.sqlite"
    db.unlink(missing_ok=True)
    con = sqlite3.connect(db)
    sq = df.copy()
    for c in LIST_COLS:
        sq[c] = sq[c].map(lambda v: json.dumps(v, ensure_ascii=False))
    sq.to_sql("projects", con, index=False)
    mem.to_sql("project_sources", con, index=False)
    con.execute("CREATE INDEX ix_ps_id ON project_sources(id)"); con.execute("CREATE UNIQUE INDEX ix_p_id ON projects(id)")
    con.commit(); con.close()
    stats = make_stats(df, mem, n_in, how)
    (UNIFIED / "stats.json").write_text(json.dumps(stats, indent=1, ensure_ascii=False))
    (UNIFIED / "stats.md").write_text(stats_md(stats))
    print(stats_md(stats)); print(f"done in {time.time()-t0:.0f}s")


CONTINENTS = {"Africa", "Asia", "Europe", "North America", "South America", "Oceania", "Antarctica", "Global"}


def fix_regions(unified, recs):
    """region = continent (or Global). Other activity-region strings move to geographic_focus; fill from country."""
    votes = collections.defaultdict(collections.Counter)
    for r in recs:
        if r["source"] == "CTFG" and r["country"] and r["region"] in CONTINENTS:
            votes[r["country"]][r["region"]] += 1
    c2r = {c: v.most_common(1)[0][0] for c, v in votes.items()}
    c2r.update({"Germany": "Europe", "Kosovo": "Europe"})
    for m in unified:
        reg = m.get("region")
        if reg and reg.strip().title() == "Global":
            m["region"] = "Global"; continue
        if reg and reg not in CONTINENTS:
            if reg not in m["geographic_focus"]:
                m["geographic_focus"].append(reg)
            m["region"] = None
        if not m["region"] and m["country"]:
            m["region"] = c2r.get(m["country"])


def make_stats(df, mem, n_in, how):
    srcs = [s for s in SOURCE_PRIORITY if s in set(mem.source)]
    per_src = mem.groupby("source").size().to_dict()
    uniq_per_src = {s: int(df.sources.map(lambda v: s in v).sum()) for s in srcs}
    overlap = {a: {b: int(df.sources.map(lambda v: a in v and b in v).sum()) for b in srcs} for a in srcs}
    only = {s: int(df.sources.map(lambda v: v == [s]).sum()) for s in srcs}
    vc = lambda col, n=20: {str(k): int(v) for k, v in df[col].value_counts(dropna=False).head(n).items()}
    ex = lambda col, n=20: {str(k): int(v) for k, v in df[col].explode().value_counts().head(n).items()}
    return {
        "input_records": int(n_in), "unique_projects": int(len(df)), "merged_away": int(n_in - len(df)),
        "multi_source_projects": int((df.n_sources > 1).sum()), "merge_rules_applied": dict(how),
        "records_per_source": {s: int(per_src.get(s, 0)) for s in srcs},
        "unique_projects_per_source": uniq_per_src, "only_in_source": only, "overlap_matrix": overlap,
        "status": vc("status"), "org_type": vc("org_type"), "url_flag": vc("url_flag"),
        "top_countries": vc("country", 25), "top_regions": vc("region", 15), "top_sdgs": ex("sdgs", 17),
        "top_categories": ex("categories", 25), "ai_related": int(df.ai_related.sum()), "ai_technology": ex("ai_technology", 10),
        "open_source": vc("open_source"), "with_description": int(df.description.notna().sum()),
        "with_url": int(df.url.notna().sum()), "with_country": int(df.country.notna().sum()),
    }


def stats_md(s):
    L = ["# Unified civic tech dataset - statistics", "",
         f"- Input records (all sources): **{s['input_records']}**",
         f"- Unique projects after dedup: **{s['unique_projects']}** ({s['merged_away']} records merged)",
         f"- Projects found in >1 source: **{s['multi_source_projects']}**",
         f"- AI-related projects (keyword/tag based): **{s['ai_related']}**", ""]
    def table(title, d, h=("value", "count")):
        L.extend([f"## {title}", "", f"| {h[0]} | {h[1]} |", "|---|---:|"] + [f"| {k} | {v} |" for k, v in d.items()] + [""])
    table("Records per source", s["records_per_source"], ("source", "records"))
    table("Unique projects containing source", s["unique_projects_per_source"], ("source", "projects"))
    table("Projects only in this source", s["only_in_source"], ("source", "projects"))
    srcs = list(s["overlap_matrix"])
    L.extend(["## Overlap matrix (projects shared between sources)", "", "| | " + " | ".join(srcs) + " |",
              "|---|" + "---:|" * len(srcs)] + [f"| {a} | " + " | ".join(str(s["overlap_matrix"][a][b]) for b in srcs) + " |" for a in srcs] + [""])
    table("Merge rules applied", s["merge_rules_applied"], ("rule", "unions"))
    for k in ["status", "org_type", "url_flag", "open_source", "top_countries", "top_regions", "top_sdgs", "ai_technology", "top_categories"]:
        table(k.replace("_", " ").title(), s[k])
    return "\n".join(L)


if __name__ == "__main__":
    main()
