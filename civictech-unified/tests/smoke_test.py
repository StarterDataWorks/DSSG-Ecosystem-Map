"""Smoke test of the unified outputs: python tests/smoke_test.py"""
import json, sqlite3, sys
from pathlib import Path
import pandas as pd

U = Path(__file__).resolve().parents[1] / "unified"
STATUSES = {"active", "inactive", "prototype", "research", "failed/sunset", "unknown"}
df = pd.read_parquet(U / "civictech_unified.parquet")
assert len(df) > 10000 and df.id.is_unique and df.name.notna().all()
assert set(df.status) <= STATUSES, set(df.status) - STATUSES
assert df.sources.map(len).gt(0).all() and (df.sources.map(len) == df.n_sources).all()
assert {"CTFG", "HIIG", "CivicDataLab", "CodeForDE", "CivicTechFundAfrica", "HackCorruption", "Awesome-Civic-Tech"} <= set(df.sources.explode())
assert df.raw_fields.map(lambda s: isinstance(json.loads(s), dict)).all()
assert len(pd.read_csv(U / "civictech_unified.csv")) == len(df)
assert sum(1 for _ in open(U / "civictech_unified.jsonl")) == len(df)
assert len(json.load(open(U / "civictech_unified.json"))) == len(df)
con = sqlite3.connect(U / "civictech_unified.sqlite")
assert con.execute("select count(*) from projects").fetchone()[0] == len(df)
mem = pd.read_csv(U / "source_membership.csv")
assert set(mem.id) == set(df.id)
for slug in ["decidim", "fixmystreet"]:
    assert slug in set(df.id), slug
print(f"OK: {len(df)} projects, {len(mem)} source records")
