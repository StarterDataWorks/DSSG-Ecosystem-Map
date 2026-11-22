"""Download HTML/markdown/CSV snapshots for the smaller sources into raw/."""
import time
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[2] / "raw"
UA = {"User-Agent": "Mozilla/5.0 (civictech-unified research dataset builder)"}
HF = "https://huggingface.co/datasets/hiig-ai-lab/publicinterest-ai-projects/resolve/main/"
GH = "https://raw.githubusercontent.com/"

FILES = {
    "hiig/public_interest_ai_projects_2024.xlsx": HF + "Public%20Interest%20AI%20Projects%202024.xlsx",
    "hiig/public_interest_ai_projects_2024_democracy.xlsx": HF + "Public%20Interest%20AI%20Projects%202024_Connected%20to%20democracy.xlsx",
    "hiig/README.md": HF + "README.md",
    "civicdatalab/data.csv": GH + "Caritas-Deutschland-Digitallabor/datenprojekte/main/data.csv",
    "civicdatalab/README.md": GH + "Caritas-Deutschland-Digitallabor/datenprojekte/main/README.md",
    "civicdatalab/unreachable_websites.csv": GH + "Caritas-Deutschland-Digitallabor/datenprojekte/main/2026-07-05_TO_BE_CHECKED_unreachable_websites.csv",
    "awesome/brandonhimpfen_awesome-civic-tech.md": GH + "brandonhimpfen/awesome-civic-tech/main/README.md",
    "awesome/sllvn_awesome-civic-tech.md": GH + "sllvn/awesome-civic-tech/master/README.md",
    "ctfafrica/projects_en.html": "https://civictechfund.africa/projects/",
    "hackcorruption/home.html": "https://hackcorruption.org/",
    "hackcorruption/nepal-hackathon.html": "https://hackcorruption.org/nepal-hackathon/",
    "hackcorruption/south-africa-hackathon.html": "https://hackcorruption.org/south-africa-hackathon/",
    "hackcorruption/malaysia-hackathon.html": "https://hackcorruption.org/malaysia-hackathon/",
    "hackcorruption/albania-hackathon.html": "https://hackcorruption.org/albania-hackathon/",
}


def main(force=False):
    for rel, url in FILES.items():
        p = ROOT / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if p.exists() and not force:
            continue
        r = requests.get(url, headers=UA, timeout=120)
        r.raise_for_status()
        p.write_bytes(r.content)
        print("saved", rel, len(r.content))
        time.sleep(0.5)


if __name__ == "__main__":
    main()
