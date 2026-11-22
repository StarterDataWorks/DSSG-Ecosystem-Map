"""Shared cleaning helpers: text, URLs, names, countries, status, org type, SDGs, AI tags."""
import re, unicodedata, hashlib
from urllib.parse import urlsplit, urlunsplit
import pycountry

ROOT_DIR = __import__("pathlib").Path(__file__).resolve().parents[1]
RAW = ROOT_DIR / "raw"
UNIFIED = ROOT_DIR / "unified"

EMOJI_RE = re.compile("[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF\uFE0F\u200d]+")


def clean_text(s):
    if s is None:
        return None
    if isinstance(s, float) and s != s:
        return None
    s = str(s).replace("\u00ad", "").replace("\xa0", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s or None


def as_list(v, sep=r"[;,|]"):
    if v is None or (isinstance(v, float) and v != v):
        return []
    if isinstance(v, (list, tuple, set)):
        out = []
        for x in v:
            out += as_list(x, sep)
        return out
    return [t for t in (clean_text(x) for x in re.split(sep, str(v))) if t]


def uniq(seq):
    seen, out = set(), []
    for x in seq:
        if x is None:
            continue
        k = x.lower() if isinstance(x, str) else x
        if k not in seen:
            seen.add(k); out.append(x)
    return out


def strip_accents(s):
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def norm_name(s):
    s = strip_accents(clean_text(s) or "").lower()
    s = s.replace("&", " and ")
    s = re.sub(r"\(.*?\)", " ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def slugify(s, maxlen=60):
    return norm_name(s).replace(" ", "-")[:maxlen].strip("-") or "project"


def stable_id(name, url):
    h = hashlib.sha1(f"{norm_name(name)}|{canon_url(url)[1] or ''}".encode()).hexdigest()[:8]
    return f"{slugify(name, 50)}-{h}"


# ---------------- URLs ----------------
GENERIC_HOSTS = {
    "github.com", "gitlab.com", "facebook.com", "twitter.com", "x.com", "instagram.com", "linkedin.com",
    "youtube.com", "youtu.be", "medium.com", "google.com", "docs.google.com", "drive.google.com",
    "sites.google.com", "play.google.com", "apps.apple.com", "itunes.apple.com", "wordpress.com",
    "blogspot.com", "wixsite.com", "notion.site", "huggingface.co", "civic-coding.de", "codefor.de",
    "civictech.guide", "bit.ly", "linktr.ee", "eventbrite.com", "meetup.com", "substack.com",
    "t.me", "tiktok.com", "reddit.com", "wikipedia.org", "en.wikipedia.org", "archive.org",
    "web.archive.org", "airtable.com", "app.powerbi.com", "netlify.app", "herokuapp.com", "vercel.app",
    "github.io", "correlaid.org", "publicinterest.ai", "civictechfund.africa", "accountabilitylab.org",
}


def fix_url(u):
    """Return (url, flag) where flag in ok|fixed|malformed|missing."""
    u = clean_text(u)
    if not u or u.lower() in ("n/a", "na", "none", "-", "unknown", "nan"):
        return None, "missing"
    u = u.strip(" <>\"'()[]")
    m = re.search(r"https?://\S+", u)
    flag = "ok"
    if m and m.start() > 0:
        u, flag = m.group(0), "fixed"
    if u.lower().startswith("http//") or u.lower().startswith("https//"):
        u, flag = re.sub(r"^(https?)//", r"\1://", u, flags=re.I), "fixed"
    if not re.match(r"^https?://", u, re.I):
        if re.match(r"^(www\.)?[\w.-]+\.[a-z]{2,}(/|$)", u, re.I):
            u, flag = "https://" + u, "fixed"
        else:
            return u, "malformed"
    u = u.rstrip(".,;")
    try:
        p = urlsplit(u)
    except ValueError:
        return u, "malformed"
    if not p.netloc or "." not in p.netloc or " " in p.netloc:
        return u, "malformed"
    return u, flag


def canon_url(u):
    """(fixed_url, canonical_key, host) - canonical key drops scheme, www, query, fragment, trailing slash."""
    fu, flag = fix_url(u)
    if not fu or flag == "malformed":
        return fu, None, None
    p = urlsplit(fu)
    host = p.netloc.lower().split("@")[-1].split(":")[0]
    host = re.sub(r"^(www\d?|m)\.", "", host)
    path = re.sub(r"/(index\.(html?|php))?$", "", p.path.rstrip("/"))
    path = re.sub(r"/+", "/", path)
    if host in ("github.com", "gitlab.com"):
        path = "/".join(path.lower().split("/")[:3])
    return fu, (host + path).lower(), host


def reg_domain(host):
    if not host:
        return None
    parts = host.split(".")
    if len(parts) >= 3 and len(parts[-1]) == 2 and (len(parts[-2]) <= 3 or parts[-2] in ("gov", "gouv", "govt")):
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


# ---------------- countries ----------------
COUNTRY_ALIASES = {
    "usa": "US", "us": "US", "u.s.": "US", "u.s.a.": "US", "united states of america": "US", "america": "US",
    "uk": "GB", "u.k.": "GB", "england": "GB", "scotland": "GB", "wales": "GB", "northern ireland": "GB",
    "great britain": "GB", "britain": "GB", "deutschland": "DE", "the netherlands": "NL", "holland": "NL",
    "south korea": "KR", "korea": "KR", "north korea": "KP", "russia": "RU", "iran": "IR", "syria": "SY",
    "vietnam": "VN", "laos": "LA", "bolivia": "BO", "venezuela": "VE", "tanzania": "TZ", "moldova": "MD",
    "czech republic": "CZ", "czechia": "CZ", "ivory coast": "CI", "cote d'ivoire": "CI", "turkey": "TR",
    "türkiye": "TR", "turkiye": "TR", "palestine": "PS", "taiwan": "TW", "macedonia": "MK", "drc": "CD",
    "dr congo": "CD", "democratic republic of the congo": "CD", "republic of the congo": "CG", "congo": "CG",
    "cape verde": "CV", "cabo verde": "CV", "eswatini": "SZ", "swaziland": "SZ", "brasil": "BR",
    "méxico": "MX", "españa": "ES", "schweiz": "CH", "österreich": "AT", "kosovo": "XK", "micronesia": "FM",
    "the gambia": "GM", "gambia": "GM", "burma": "MM", "east timor": "TL", "vatican": "VA", "hong kong": "HK",
}
COUNTRY_NAME_OVERRIDE = {"XK": "Kosovo", "TW": "Taiwan", "KR": "South Korea", "KP": "North Korea", "RU": "Russia",
                         "IR": "Iran", "VN": "Vietnam", "BO": "Bolivia", "VE": "Venezuela", "TZ": "Tanzania",
                         "MD": "Moldova", "SY": "Syria", "LA": "Laos", "PS": "Palestine", "CD": "DR Congo",
                         "CG": "Congo", "CZ": "Czechia", "TR": "Turkey", "FM": "Micronesia", "VA": "Vatican City",
                         "MK": "North Macedonia", "BN": "Brunei", "CI": "Côte d'Ivoire", "GB": "United Kingdom",
                         "US": "United States"}
NON_COUNTRY = {"global", "worldwide", "international", "unknown", "unkown", "unclear", "n/a", "none", "online",
               "europe", "africa", "asia", "latin america", "global south", "eu", "european union", "multiple",
               "north america", "south america", "oceania", "middle east", "the caribbean", "caribbean"}
_country_cache = {}


def norm_country(s):
    """Return a standardized country name (ISO 3166 common name) or None."""
    s = clean_text(s)
    if not s:
        return None
    s = clean_text(EMOJI_RE.sub("", s))
    s = re.sub(r"\s*\(.*?\)\s*", " ", s).strip(" .")
    if not s:
        return None
    key = s.lower()
    if key in _country_cache:
        return _country_cache[key]
    res = None
    if key not in NON_COUNTRY:
        code = COUNTRY_ALIASES.get(key)
        try:
            c = pycountry.countries.get(alpha_2=code) if code and code != "XK" else pycountry.countries.lookup(s)
            if code == "XK":
                res = "Kosovo"
            elif c:
                res = COUNTRY_NAME_OVERRIDE.get(c.alpha_2) or getattr(c, "common_name", None) or c.name
        except LookupError:
            if code == "XK":
                res = "Kosovo"
            else:
                try:
                    m = pycountry.countries.search_fuzzy(s)
                    if len(m) == 1:
                        c = m[0]; res = COUNTRY_NAME_OVERRIDE.get(c.alpha_2) or getattr(c, "common_name", None) or c.name
                except LookupError:
                    res = None
    _country_cache[key] = res
    return res


def norm_countries(v):
    out = []
    for t in as_list(v, r"[;,/|]| and | & "):
        c = norm_country(t)
        if c:
            out.append(c)
    return uniq(out)


# ---------------- status / org type ----------------
STATUS_VALUES = ["active", "inactive", "prototype", "research", "failed/sunset", "unknown"]


def norm_status(raw):
    s = (clean_text(raw) or "").lower()
    if not s or s in ("n/a", "nan", "unbekannt", "unknown", "none"):
        return "unknown"
    rules = [
        ("failed/sunset", ["graveyard", "eingestellt", "shut down", "shutdown", "defunct", "sunset", "dead", "failed", "acquired", "discontinued"]),
        ("prototype", ["prototype", "prototyp", "beta", "testbetrieb", "planung", "not active yet", "in development", "pilot", "no tool yet"]),
        ("research", ["research", "forschung"]),
        ("active", ["ended / but running"]),
        ("inactive", ["inactive", "inaktiv", "abgeschlossen", "completed", "stagnant", "pause", "ended", "closed", "archived", "done", "finished"]),
        ("active", ["active", "aktiv", "in betrieb", "ongoing", "in progress", "running", "weiterentwicklung", "live", "maintained"]),
    ]
    for val, kws in rules:
        if any(k in s for k in kws):
            return val
    return "unknown"


ORG_MAP = [
    ("government", ["government", "public sector", "multilateral", "municipal", "ministry", "behörde", "öffentlich"]),
    ("research", ["academic", "research", "university", "think tank", "forschung", "hochschule"]),
    ("for-profit", ["for-profit", "for profit", "business", "enterprise", "b corp", "company", "commercial"]),
    ("non-profit", ["non-profit", "nonprofit", "non profit", "charity", "foundation", "grassroots", "indie", "advocacy",
                    "ngo", "e.v.", "gemeinnützig", "volunteer", "community"]),
]


def norm_org_type(values):
    vals = [v for v in as_list(values, r"[;|]") if v]
    if not vals:
        return "unsure"
    found = []
    for v in vals:
        lv = v.lower()
        if lv in ("non-profit / research",):
            found.append("research"); continue
        for out, kws in ORG_MAP:
            if any(k in lv for k in kws):
                found.append(out); break
    found = uniq(found)
    if not found:
        return "unsure"
    return found[0] if len(found) == 1 else "hybrid"


def norm_open_source(*vals):
    for v in vals:
        s = (clean_text(v) or "").lower()
        if not s or s in ("n/a", "nan", "none"):
            continue
        if "partial" in s or "open core" in s:
            return "partial"
        if s in ("yes", "true", "open source") or "open source" in s or "open-source" in s:
            return "yes"
        if s in ("no", "false") or "proprietary" in s:
            return "no"
    return None


# ---------------- SDGs ----------------
SDG_NAMES = ["No Poverty", "Zero Hunger", "Good Health and Well-being", "Quality Education", "Gender Equality",
             "Clean Water and Sanitation", "Affordable and Clean Energy", "Decent Work and Economic Growth",
             "Industry, Innovation and Infrastructure", "Reduced Inequalities", "Sustainable Cities and Communities",
             "Responsible Consumption and Production", "Climate Action", "Life Below Water", "Life on Land",
             "Peace, Justice and Strong Institutions", "Partnerships for the Goals"]
_SDG_NORM = {norm_name(n): i + 1 for i, n in enumerate(SDG_NAMES)}


def norm_sdg(v):
    s = clean_text(v)
    if not s:
        return None
    m = re.match(r"^\s*(?:sdg\s*)?(\d{1,2})\b", s, re.I)
    n = int(m.group(1)) if m else _SDG_NORM.get(norm_name(s))
    if n is None:
        from rapidfuzz import process, fuzz
        best = process.extractOne(norm_name(s), list(_SDG_NORM), scorer=fuzz.token_set_ratio)
        if best and best[1] >= 85:
            n = _SDG_NORM[best[0]]
    if n and 1 <= n <= 17:
        return f"SDG {n}: {SDG_NAMES[n - 1]}"
    return None


def norm_sdgs(values):
    return uniq([x for x in (norm_sdg(v) for v in as_list(values, r"[;|]")) if x])


# ---------------- AI technology tagging ----------------
AI_PATTERNS = {
    "Generative AI / LLM": r"\b(llms?|large language models?|generative ai|genai|gpt|chatgpt|gen ai|foundation models?|agentic)\b",
    "NLP": r"\b(nlp|natural language|text mining|sprachverarbeitung|translation|speech|transcription|spracherkennung)\b",
    "Computer Vision": r"\b(computer vision|image recognition|bilderkennung|object detection|satellite imagery|remote sensing|vision)\b",
    "Machine Learning": r"\b(machine learning|maschinelles lernen|ml|deep learning|neural networks?|supervised|predictive|prediction|prognose|recsys|recommender)\b",
    "Chatbot / Conversational AI": r"\b(chatbots?|chat bot|conversational ai|virtual assistant|sprachassistent)\b",
    "Artificial Intelligence (general)": r"\b(ai|artificial intelligence|künstliche intelligenz|ki)\b",
}
_AI_RE = {k: re.compile(v, re.I) for k, v in AI_PATTERNS.items()}


def ai_tags(*texts):
    blob = " ".join(t for t in texts if t)
    tags = [k for k, r in _AI_RE.items() if r.search(blob)]
    if len(tags) > 1 and "Artificial Intelligence (general)" in tags:
        tags.remove("Artificial Intelligence (general)")
    return tags


def city_from_lab(lab):
    lab = clean_text(lab) or ""
    m = re.match(r"^(?:OK ?Lab|Code for|Open Knowledge Lab)\s+(.+?)(?:,|$)", lab, re.I)
    if not m:
        return None
    c = m.group(1).strip()
    return {"Bonn-Rhein-Sieg": "Bonn", "Ruhr": None,
            "Niederrhein": None, "Rhein-Neckar": None, "Saar": None}.get(c, c)
