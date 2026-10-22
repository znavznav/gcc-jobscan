"""Daily GCC job scan. Runs in GitHub Actions (needs open internet + Playwright).

Outputs (committed back to the repo by the workflow):
  results/latest.json        new candidate roles since the previous run, pre-filtered and flagged
  results/health.json        per-source status, so broken sources are visible
  results/history/<date>.json
  state/seen.json            every job URL ever seen -> first-seen date
"""
import json, os, re, sys, time, hashlib, datetime as dt, traceback
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse, urlunparse

sys.path.insert(0, os.path.dirname(__file__))
from connectors import API_CONNECTORS, browser, fetch_detail_text
from filters import title_score, text_flags, in_gcc

ROOT = os.path.dirname(os.path.abspath(__file__))
REG = ROOT
RES = os.path.join(ROOT, "results")
STATE = os.path.join(ROOT, "state", "seen.json")
TODAY = dt.date.today().isoformat()
MAX_DETAILS = int(os.environ.get("MAX_DETAILS", "120"))
MAX_AGE_DAYS = int(os.environ.get("MAX_AGE_DAYS", "14"))
GLOBAL_SECTORS = {"foreign_bank_branch", "private_bank", "consulting", "investment_bank", "asset_manager",
                  "fintech_payments"}


def load(p, default):
    try:
        return json.load(open(p))
    except Exception:
        return default


def norm_url(u):
    p = urlparse(u or "")
    # keep query only where it identifies the job (e.g. ?jobId=)
    keep_q = p.query if re.search(r"(job|req|id)=", p.query, re.I) else ""
    return urlunparse((p.scheme, p.netloc.lower(), p.path.rstrip("/"), "", keep_q, ""))


def job_key(j):
    return hashlib.sha1(norm_url(j["url"]).encode()).hexdigest()[:16] if j.get("url") else \
        hashlib.sha1(f"{j['employer']}|{j['title']}|{j.get('location')}".lower().encode()).hexdigest()[:16]


def parse_posted(raw):
    """Best-effort ISO date from the many formats sites use. Returns (iso or None, raw)."""
    if not raw:
        return None, None
    s = str(raw).strip()
    today = dt.date.today()
    m = re.search(r"(\d+)\+?\s*(hour|day|week|month)s?\s*ago", s, re.I)
    if m:
        n, unit = int(m.group(1)), m.group(2).lower()
        days = {"hour": 0, "day": n, "week": 7 * n, "month": 30 * n}[unit]
        return (today - dt.timedelta(days=days)).isoformat(), s
    if re.search(r"\btoday\b|just posted|hours? ago", s, re.I):
        return today.isoformat(), s
    if re.search(r"yesterday", s, re.I):
        return (today - dt.timedelta(days=1)).isoformat(), s
    cand = re.search(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[ -][A-Za-z]{3,9},?[ -]\d{2,4}|[A-Za-z]{3,9} \d{1,2}, \d{4}|\d{1,2}/\d{1,2}/\d{4}", s)
    if cand:
        c = cand.group(0).replace(",", "")
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d %b %Y", "%d %B %Y", "%b %d %Y", "%B %d %Y", "%d-%b-%Y", "%d-%B-%Y",
                    "%d/%m/%Y", "%d-%b-%y", "%d %b %y"):
            try:
                return dt.datetime.strptime(c, fmt).date().isoformat(), s
            except Exception:
                pass
    m = re.search(r"\d{4}-\d{2}-\d{2}", s)
    if m:
        return m.group(0), s
    return None, s


def run_api(emp):
    fn = API_CONNECTORS[emp["connector"]]
    return fn(emp)


def main():
    employers = [e for e in load(os.path.join(REG, "employers.json"), [])
                 if e.get("established_ok", True) is not False]
    boards = load(os.path.join(REG, "boards.json"), [])
    seen = load(STATE, {})
    health, raw = [], []

    # 1) API connectors in parallel
    api_emps = [e for e in employers if e["connector"] in API_CONNECTORS]

    def do(e):
        t0 = time.time()
        try:
            jobs = run_api(e)
            return e, jobs, None, time.time() - t0
        except Exception as ex:
            return e, [], f"{type(ex).__name__}: {str(ex)[:200]}", time.time() - t0

    with ThreadPoolExecutor(8) as ex:
        for e, jobs, err, secs in ex.map(do, api_emps):
            health.append({"source": e["name"], "connector": e["connector"], "count": len(jobs),
                           "error": err, "secs": round(secs, 1)})
            for j in jobs:
                j.update(employer=e["name"], country=e["country"], sector=e.get("sector"),
                         islamic=e.get("islamic"), global_employer=e.get("sector") in GLOBAL_SECTORS)
                raw.append(j)

    # 2) Browser-rendered career pages and job boards
    from playwright.sync_api import sync_playwright
    browser_emps = [e for e in employers if e["connector"] == "browser" and e.get("careers_url")]
    board_srcs = []
    for b in boards:
        if b.get("fetch_ok"):
            for u in b.get("urls", [])[:12]:
                board_srcs.append({"name": b["source"], "careers_url": u, "country": "", "sector": "job_board",
                                   "islamic": False, "connector": "browser"})

    with sync_playwright() as p:
        br = p.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = br.new_context(ignore_https_errors=True, user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                                         "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"), locale="en-US")
        for e in browser_emps + board_srcs:
            t0 = time.time()
            page = ctx.new_page()  # fresh tab per source so one site's redirects can't break the next
            try:
                jobs = browser(e, page)
                err = None
            except Exception as ex:
                jobs, err = [], f"{type(ex).__name__}: {str(ex)[:200]}"
            finally:
                page.close()
            health.append({"source": e["name"], "connector": "board" if e["sector"] == "job_board" else "browser",
                           "url": e["careers_url"], "count": len(jobs), "error": err,
                           "secs": round(time.time() - t0, 1)})
            for j in jobs:
                j.update(employer=e["name"], country=e.get("country"), sector=e.get("sector"),
                         islamic=e.get("islamic"), global_employer=e.get("sector") in GLOBAL_SECTORS | {"job_board"})
                raw.append(j)

        # 3) Filter, dedupe against history, flag
        new = []
        for j in raw:
            if not j.get("title"):
                continue
            j["title"] = re.sub(r"\s+", " ", j["title"]).strip()
            k = job_key(j)
            if k in seen:
                continue
            seen[k] = TODAY
            sc = title_score(j["title"])
            if sc == 0:
                continue
            if not in_gcc(j.get("location") or "", j.get("country"), j.get("global_employer")):
                continue
            iso, rawd = parse_posted(j.get("posted"))
            if iso and iso < (dt.date.today() - dt.timedelta(days=MAX_AGE_DAYS)).isoformat():
                continue  # old posting we are only now discovering (mainly the first run)
            j.update(key=k, score=sc, posted_iso=iso, posted_raw=rawd, first_seen=TODAY)
            new.append(j)

        page = ctx.new_page()
        # 4) Read full postings for the best candidates and apply the hard exclusions
        new.sort(key=lambda j: (j["score"], j.get("posted_iso") or ""), reverse=True)
        for j in new[:MAX_DETAILS]:
            txt = fetch_detail_text(j, page if not j.get("detail_api") else None)
            flags = text_flags(j["title"] + " " + txt)
            j.update(flags)
            j["detail_ok"] = not txt.startswith("__detail_error__")
            j["excerpt"] = re.sub(r"\s+", " ", txt)[:1500]
        br.close()

    # nationals-only / mandatory Arabic visible in the title alone
    for j in new[MAX_DETAILS:]:
        j.update(text_flags(j["title"]))

    kept = [j for j in new if not j.get("nationals_only") and not j.get("arabic_mandatory")]
    dropped = [{"title": j["title"], "employer": j["employer"], "url": j["url"],
                "why": j.get("nationals_match") or j.get("arabic_match")} for j in new if j not in kept]

    os.makedirs(os.path.join(RES, "history"), exist_ok=True)
    out = {"run_date": TODAY, "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
           "raw_jobs_seen": len(raw), "new_candidates": len(kept), "excluded": dropped, "candidates": kept}
    json.dump(out, open(os.path.join(RES, "latest.json"), "w"), indent=1, ensure_ascii=False)
    json.dump(out, open(os.path.join(RES, "history", f"{TODAY}.json"), "w"), indent=1, ensure_ascii=False)
    json.dump({"run_date": TODAY, "sources": health}, open(os.path.join(RES, "health.json"), "w"), indent=1)
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    json.dump(seen, open(STATE, "w"))
    ok = sum(1 for h in health if not h["error"] and h["count"] > 0)
    print(f"sources={len(health)} working={ok} raw={len(raw)} new_candidates={len(kept)} excluded={len(dropped)}")


if __name__ == "__main__":
    main()
