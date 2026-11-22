# Unified Civic Tech / Public Interest AI Project Dataset

Reproducible pipeline that collects civic tech, public-interest AI and public-good technology projects from 7 open sources,
normalizes them to one schema, deduplicates across sources and exports a single dataset.

Snapshot: all raw files downloaded **2026-11-09**. Headline numbers (see `unified/stats.md` for full statistics):

| | |
|---|---:|
| Source records (after dropping empty ones) | 14,822 |
| Unique projects after dedup | 14,345 |
| Projects found in >1 source | 422 |
| AI-related projects (tag/keyword based) | 2,543 |

## Run

```bash
./run_pipeline.sh               # fetch everything into raw/ and rebuild unified/  (~5 min, CTFG rate limit respected)
./run_pipeline.sh --skip-fetch  # rebuild unified/ from the existing raw/ snapshots (~15 s)
python tests/smoke_test.py      # sanity checks on all output files
```

Layout: `raw/` (untouched downloads) -> `src/fetch/*.py` (downloaders) -> `src/normalize.py` (one parser per source)
-> `src/dedup.py` (clustering + merge) -> `src/build.py` (exports + stats) -> `unified/`.

## Outputs (`unified/`)

| file | content |
|---|---|
| `civictech_unified.parquet` | preferred for analysis; list fields are real arrays, `raw_fields` is a JSON string |
| `civictech_unified.jsonl` | one project per line, includes `raw_fields` |
| `civictech_unified.json` | JSON array without `raw_fields` (smaller) |
| `civictech_unified.csv` | flat; list fields joined with ` \| `; no `raw_fields` |
| `civictech_unified.sqlite` | table `projects` (list fields as JSON text) + `project_sources` (one row per contributing source record) |
| `source_membership.csv` | unified `id` -> `source`, `source_id`, original `name` (audit trail of every merge) |
| `stats.md` / `stats.json` | counts, overlap matrix, merge rules applied, status/country/SDG/AI distributions |

## Sources

| source key | what | how | records | license / terms |
|---|---|---|---:|---|
| `CTFG` | [Civic Tech Field Guide](https://civictech.guide) - backbone | `GET /api/v1/projects/export?include=raw_fields` (paged, 1000/page) + facets, issues, SDGs, graveyard page | 13,198 | per civictech.guide terms; attribute CTFG |
| `HIIG` | [HIIG Public Interest AI projects](https://huggingface.co/datasets/hiig-ai-lab/publicinterest-ai-projects) main table + "connected to democracy" subset | HF XLSX files | 211 | CC-BY-4.0 |
| `CivicDataLab` | [Caritas/Civic Data Lab datenprojekte](https://github.com/Caritas-Deutschland-Digitallabor/datenprojekte) (backs civic-data.de Projektsammlung) | `data.csv` + `unreachable_websites.csv` | 1,071 | license stated per project (`open_source_license`) |
| `CodeForDE` | [Code for Germany](https://codefor.de/projekte/alle/) | listing page + 249 project detail pages | 249 | site content of OKF DE |
| `CivicTechFundAfrica` | [Civic Tech Fund Africa projects](https://civictechfund.africa/projects/) | HTML initiative cards | 36 | site content |
| `HackCorruption` | [hackcorruption.org](https://hackcorruption.org/) tools + Accountability Lab winner posts (WordPress API) | HTML/JSON | 22 | site content |
| `Awesome-Civic-Tech` | [brandonhimpfen](https://github.com/brandonhimpfen/awesome-civic-tech) + [sllvn](https://github.com/sllvn/awesome-civic-tech) lists | raw Markdown | 35 | brandonhimpfen: CC BY-SA 4.0; sllvn: CC0 |

Note: most of the Civic Data Lab rows are themselves aggregated from Public Interest AI, CorrelAid, Code for Germany etc.,
which explains the large CivicDataLab<->HIIG and CivicDataLab<->CodeForDE overlaps.

## Data dictionary

| field | type | description |
|---|---|---|
| `id` | str | CTFG slug if the project is in CTFG, else stable slug `name-slug-<hash(name+url)>` |
| `ctfg_slug` | str | CTFG slug or null |
| `name` | str | name from highest-priority source (CTFG > HIIG > CodeForDE > CivicDataLab > CTF Africa > HackCorruption > Awesome) |
| `alt_names` | list | other names the project has in other sources |
| `description` | str | richest (longest) description, preferring English-language sources; original language kept (not translated) |
| `description_de` | str | richest German description when a German source (CivicDataLab/CodeForDE) also had one |
| `url` | str | primary website (directory/listing pages are de-prioritized) |
| `url_flag` | str | `ok`, `fixed` (scheme added / multi-URL field split), `malformed`, `missing`, `unreachable` (reported dead by Civic Data Lab). Not live-checked. |
| `repository_url` | str | GitHub/GitLab repository if known |
| `status` | enum | `active`, `inactive`, `prototype`, `research`, `failed/sunset`, `unknown` |
| `status_raw` | list | original status per source, e.g. `CTFG: Active`, `CivicDataLab: In Betrieb` |
| `org_type` | enum | `non-profit`, `for-profit`, `government`, `research`, `hybrid`, `unsure` |
| `organization` | str | project owner / organization |
| `city`, `country` | str | HQ city / country (country names standardized via pycountry, English short names) |
| `countries` | list | all countries mentioned (HQ + operating countries) |
| `region` | str | continent (or `Global`); filled from country when missing |
| `geographic_focus` | list | other region strings from sources (e.g. "Southeast Asia", "Latin America") |
| `sdgs` | list | `SDG n: Title` |
| `categories` | list | CTFG categories, HIIG/CDL themes, Code for DE topics, Awesome sections, etc. |
| `issues` | list | CTFG issues |
| `tags` | list | hashtags / misc tags |
| `technologies` | list | technologies / platforms as given by sources |
| `ai_technology` | list | derived AI tags: `Generative AI / LLM`, `NLP`, `Computer Vision`, `Machine Learning`, `Chatbot / Conversational AI`, `Artificial Intelligence (general)` |
| `ai_related` | bool | `ai_technology` non-empty |
| `project_type` | list | CTFG project type (Tool or platform, Organization, Program, ...) |
| `funding` | str | funding info as text |
| `open_source` | enum | `yes`, `no`, `partial`, null |
| `open_source_license` | str | license if stated |
| `start_year`, `end_year` | int | founded / closed year |
| `impact`, `notes` | str | impact statements and provenance notes |
| `language` | str | language of the project / interface where given |
| `sources`, `n_sources` | list, int | contributing source keys |
| `source_ids`, `source_urls` | list | IDs and page/file URLs in each source |
| `raw_fields` | JSON str | `{source_id: {...all original fields...}}` for every contributing record (parquet/jsonl/sqlite only) |

## Normalization & deduplication

* Text cleaned (whitespace, HTML), URLs given a scheme and split when a field held several URLs; status/org type/open
  source/SDGs mapped to the enums above; CTFG "Graveyard" projects -> `failed/sunset`.
* Same-source duplicates: CTFG contains 32 duplicate listings; these are merged only if the normalized name matches and the URL or registered domain matches.
* Cross-source clustering (union-find), in order of confidence; counts in `stats.md`:
  1. same canonical URL (host+path, `www.` stripped) + same normalized name
  2. same canonical URL + similar name (RapidFuzz >= 80, or one name contains the other)
  3. identical normalized name, compatible countries, no conflicting domains
  4. same registered domain + fuzzy name >= 85
  5. same organization + fuzzy name >= 92
  6. fuzzy name >= 95 when one side has no URL
  Generic hosts (github.com, facebook.com, huggingface.co, ...) never count as a shared URL. Two records of the
  same source can only end up in one cluster if they carry the same normalized name.
* Merge: priority source for scalars, longest description, union of all list fields, every contributing record listed in
  `sources`/`source_ids`/`source_membership.csv`, all original fields in `raw_fields`.

## Known limitations

* Coverage is dominated by CTFG (92% of projects) and therefore by US/European, English-language projects.
* Status is as reported by each source at snapshot time; CTF Africa projects are "documented in the May 2024 booklet",
  not verified as operating (status `unknown` unless CTFG has a status). URLs were **not** live-checked (only Civic Data Lab's dead-link list is used).
* Dedup is heuristic. Known edge cases: an organization and its flagship project with the same URL can be merged
  (e.g. `DataKind` + "DataKind: efficient vaccine coverage"); renamed projects with different URLs may stay separate
  (e.g. CTFG has both `Botometer` and `Botometer Blue`). Review via `source_membership.csv`.
* `ai_related` is keyword/tag based (CTFG AI categories, HIIG membership, description keywords) - expect some false positives.
* German descriptions are kept in German (no machine translation). `country` is missing for ~26% of projects.
* HackCorruption: only tools/winners named on the site and on Accountability Lab announcement posts; many hackathon
  prototypes have no URL. Code for Germany: status is the site's own label.
* Wayback/archived sources were not needed and not used.
