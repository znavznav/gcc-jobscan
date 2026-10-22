"""Merge the researched employer files into registry/employers.json and tag each with a connector.

Connector is inferred from the careers URL so new employers only need a URL.
Run: python tools/build_registry.py <dir-with-employer-json-files>
"""
import json, glob, re, sys, os
from urllib.parse import urlparse

SRC = sys.argv[1] if len(sys.argv) > 1 else "employers"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "employers.json")


def connector_for(url: str) -> str:
    if not url:
        return "none"
    u = url.lower()
    host = urlparse(u).netloc
    if "linkedin.com" in host:
        return "none"
    if "oraclecloud.com" in host and "candidateexperience" in u:
        return "oracle"
    if "myworkdayjobs.com" in host:
        return "workday"
    if "portal.careers.hsbc.com" in host or "eightfold" in host:
        return "eightfold"
    if "ashbyhq.com" in host:
        return "ashby"
    if "workable.com" in host:
        return "workable"
    if "smartrecruiters.com" in host:
        return "smartrecruiters"
    if "greenhouse.io" in host:
        return "greenhouse"
    if "lever.co" in host:
        return "lever"
    if "/search/?" in u and ("sortcolumn" in u or "locationsearch" in u or "q=" in u):
        return "successfactors"
    return "browser"  # render with Playwright and pull job-like links


# Known API slugs for career pages that wrap an ATS (found during research)
OVERRIDES = {
    "Lean Technologies": {"connector": "ashby", "api_slug": "LeanTech"},
    "Ziina": {"connector": "ashby", "api_slug": "ziina"},
    "Checkout.com (Dubai)": {"connector": "ashby", "api_slug": "checkout.com"},
    "Moyasar": {"connector": "workable", "api_slug": "moyasar-financial-company-1"},
    "Abu Dhabi Investment Council": {"connector": "workable", "api_slug": "abu-dhabi-investment-council"},
    "Mumtalakat Holding Company": {"connector": "smartrecruiters", "api_slug": "BahrainMumtalakatHoldingCompany"},
}

SKIP_NOTES = re.compile(r"do-not-scrape|hijack|gambling", re.I)

rows, seen_urls = [], set()
for f in sorted(glob.glob(os.path.join(SRC, "*.json"))):
    for e in json.load(open(f)):
        url = e.get("careers_url")
        if e.get("notes") and SKIP_NOTES.search(e["notes"]):
            url = None
        rec = {
            "name": e["name"],
            "country": e["country"],
            "sector": e.get("sector"),
            "islamic": bool(e.get("islamic")),
            "established_ok": e.get("established_ok", True),
            "careers_url": url,
            "connector": connector_for(url),
            "notes": e.get("notes", ""),
        }
        for k, v in OVERRIDES.items():
            if e["name"].startswith(k):
                rec.update(v)
        # one fetch per distinct URL; extra employers sharing a portal are aliases
        if url and url in seen_urls:
            rec["connector"] = "alias"
        if url:
            seen_urls.add(url)
        rows.append(rec)

os.makedirs(os.path.dirname(OUT), exist_ok=True)
json.dump(rows, open(OUT, "w"), indent=1, ensure_ascii=False)
from collections import Counter
print(len(rows), "employers ->", OUT)
print(Counter(r["connector"] for r in rows))
