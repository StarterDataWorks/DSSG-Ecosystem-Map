#!/usr/bin/env bash
# Full reproducible run. Use --skip-fetch to rebuild unified/ from the existing raw/ snapshots.
set -euo pipefail
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
. .venv/bin/activate
pip install -q -r requirements.txt
if [ "${1:-}" != "--skip-fetch" ]; then
  python src/fetch/ctfg.py          # ~14 requests, respects 15/min export limit
  python src/fetch/web_sources.py   # HIIG, Awesome lists, Civic Data Lab, CTF Africa, HackCorruption
  python src/fetch/codefor_de.py    # 1 listing + ~249 detail pages
fi
cd src && python build.py | tee ../unified/build.log
