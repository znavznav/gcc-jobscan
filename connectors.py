"""One function per careers-site system. Each returns a list of
{"title", "location", "url", "posted"} dicts (posted = ISO date or raw text or None).
"""
import re, json, time, datetime as dt
from urllib.parse import urlparse, urljoin, quote
import requests
from bs4 import BeautifulSoup

UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}
S = requests.Session()
S.headers.update(UA)
TIMEOUT = 30

# Keywords used where a site needs a search term (Workday, SuccessFactors)
SEARCH_TERMS = ["strategy", "head", "director", "transformation", "islamic", "corporate development",
                "business development", "product", "planning", "chief"]


def _get(url, **kw):
    r = S.get(url, timeout=TIMEOUT, **kw)
    r.raise_for_status()
    return r


# ---------- Oracle Recruiting Cloud (FAB, Emirates NBD, ADIB, BSF, KFH, Gulf Bank, JPM ...) ----------
def oracle(emp):
    url = emp["careers_url"]
    host = urlparse(url).netloc
    m = re.search(r"/sites/([^/?#]+)", url)
    site = m.group(1) if m else "CX_1"
    api = (f"https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
           f"?onlyData=true&expand=requisitionList.secondaryLocations"
           f"&finder=findReqs;siteNumber={site},limit=200,sortBy=POSTING_DATES_DESC")
    data = _get(api, headers={"Accept": "application/json"}).json()
    out = []
    for item in data.get("items", []):
        for r in item.get("requisitionList", []):
            out.append({
                "title": r.get("Title"),
                "location": ", ".join(filter(None, [r.get("PrimaryLocation"), r.get("PrimaryLocationCountry")])),
                "url": f"https://{host}/hcmUI/CandidateExperience/en/sites/{site}/job/{r.get('Id')}",
                "posted": r.get("PostedDate"),
                "detail_api": (f"https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails"
                               f"?expand=all&onlyData=true&finder=ById;Id=%22{r.get('Id')}%22,siteNumber={site}"),
            })
    return out


# ---------- Workday (Deutsche, MUFG, Julius Baer, Lombard Odier, Visa ...) ----------
def workday(emp):
    url = emp["careers_url"]
    p = urlparse(url)
    tenant = p.netloc.split(".")[0]
    parts = [x for x in p.path.split("/") if x and not re.match(r"^[a-z]{2}-[A-Z]{2}$", x)]
    site = parts[0] if parts else "External"
    api = f"https://{p.netloc}/wday/cxs/{tenant}/{site}/jobs"
    out, seen = [], set()
    for term in SEARCH_TERMS:
        body = {"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": term}
        r = S.post(api, json=body, timeout=TIMEOUT, headers={"Accept": "application/json"})
        if r.status_code != 200:
            continue
        for j in r.json().get("jobPostings", []):
            path = j.get("externalPath")
            if not path or path in seen:
                continue
            seen.add(path)
            out.append({
                "title": j.get("title"),
                "location": j.get("locationsText"),
                "url": f"https://{p.netloc}/{site}{path}",
                "posted": j.get("postedOn"),  # e.g. "Posted 3 Days Ago"
            })
        time.sleep(0.5)
    return out


# ---------- SAP SuccessFactors career sites (ADCB, SAB, Standard Chartered, EY ...) ----------
def successfactors(emp):
    url = emp["careers_url"]
    p = urlparse(url)
    base = f"{p.scheme}://{p.netloc}"
    loc = re.search(r"locationsearch=([^&]+)", url)
    out = []
    for start in (0, 25, 50):
        q = f"{base}/search/?q=&sortColumn=referencedate&sortDirection=desc&startrow={start}"
        if loc:
            q += f"&locationsearch={loc.group(1)}"
        soup = BeautifulSoup(_get(q).text, "lxml")
        rows = soup.select("tr.data-row") or soup.select("li.job-tile")
        if not rows:
            break
        for row in rows:
            a = row.select_one("a.jobTitle-link") or row.select_one("a")
            if not a:
                continue
            locs = row.select_one(".jobLocation")
            date = row.select_one(".jobDate")
            out.append({
                "title": a.get_text(strip=True),
                "location": locs.get_text(" ", strip=True) if locs else "",
                "url": urljoin(base, a.get("href")),
                "posted": date.get_text(strip=True) if date else None,
            })
    return out


# ---------- Eightfold (HSBC) ----------
def eightfold(emp):
    url = emp["careers_url"]
    p = urlparse(url)
    dom = re.search(r"domain=([^&]+)", url)
    domain = dom.group(1) if dom else p.netloc
    out = []
    for loc in ["United Arab Emirates", "Saudi Arabia", "Qatar", "Bahrain", "Kuwait", "Oman"]:
        api = (f"https://{p.netloc}/api/apply/v2/jobs?domain={domain}&start=0&num=100"
               f"&location={quote(loc)}&sort_by=timestamp")
        r = S.get(api, timeout=TIMEOUT, headers={"Accept": "application/json"})
        if r.status_code != 200:
            continue
        for j in r.json().get("positions", []):
            ts = j.get("t_create") or j.get("t_update")
            out.append({
                "title": j.get("name"),
                "location": j.get("location"),
                "url": j.get("canonicalPositionUrl") or f"https://{p.netloc}/careers/job/{j.get('id')}",
                "posted": dt.datetime.utcfromtimestamp(ts).date().isoformat() if ts else None,
            })
    return out


# ---------- Public job-board APIs ----------
def ashby(emp):
    slug = emp.get("api_slug")
    d = _get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}").json()
    return [{"title": j.get("title"), "location": j.get("location"), "url": j.get("jobUrl"),
             "posted": (j.get("publishedAt") or "")[:10]} for j in d.get("jobs", [])]


def workable(emp):
    slug = emp.get("api_slug")
    d = _get(f"https://apply.workable.com/api/v1/widget/accounts/{slug}").json()
    return [{"title": j.get("title"), "location": ", ".join(filter(None, [j.get("city"), j.get("country")])),
             "url": j.get("url") or j.get("shortlink"), "posted": j.get("published_on")} for j in d.get("jobs", [])]


def smartrecruiters(emp):
    slug = emp.get("api_slug")
    d = _get(f"https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=100").json()
    return [{"title": j.get("name"), "location": (j.get("location") or {}).get("city", ""),
             "url": f"https://jobs.smartrecruiters.com/{slug}/{j.get('id')}",
             "posted": (j.get("releasedDate") or "")[:10]} for j in d.get("content", [])]


def greenhouse(emp):
    slug = emp.get("api_slug")
    d = _get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs").json()
    return [{"title": j.get("title"), "location": (j.get("location") or {}).get("name", ""),
             "url": j.get("absolute_url"), "posted": (j.get("updated_at") or "")[:10]} for j in d.get("jobs", [])]


def lever(emp):
    slug = emp.get("api_slug")
    d = _get(f"https://api.lever.co/v0/postings/{slug}?mode=json").json()
    return [{"title": j.get("text"), "location": (j.get("categories") or {}).get("location", ""),
             "url": j.get("hostedUrl"),
             "posted": dt.datetime.utcfromtimestamp(j["createdAt"] / 1000).date().isoformat() if j.get("createdAt") else None}
            for j in d]


# ---------- Generic: render the careers page in a browser and pull job-like links ----------
JOB_HREF = re.compile(r"(job|vacanc|position|requisition|opening|career|opportunit|apply|/jobs?/)", re.I)
NOISE = re.compile(r"^(apply|apply now|view|read more|more|details|search|login|sign in|register|home|careers?|"
                   r"jobs?|back|next|previous|submit|upload cv|join us|about|contact|privacy|cookies?)$", re.I)
DATE_TXT = re.compile(r"(\d{1,2}[ -/][A-Za-z]{3,9}[ -/]\d{2,4}|\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}/\d{1,2}/\d{4}|"
                      r"\d+\+? (hour|day|week|month)s? ago|today|yesterday|posted [^|\n]{0,25})", re.I)


def browser(emp, page):
    url = emp["careers_url"]
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
    except Exception as e:
        # redirects ("navigation interrupted") and slow sites: retry once, accept whatever loaded
        if "interrupted" in str(e) or "Timeout" in str(e):
            page.wait_for_timeout(3000)
            try:
                page.goto(page.url if page.url.startswith("http") else url, wait_until="commit", timeout=45000)
            except Exception:
                pass
            page.wait_for_timeout(5000)
        else:
            raise
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass
    # scroll to trigger lazy lists
    for _ in range(3):
        page.mouse.wheel(0, 4000)
        page.wait_for_timeout(800)
    links = page.eval_on_selector_all(
        "a[href]",
        """els => els.map(a => {
             const card = a.closest('li,tr,article,div[class*=job],div[class*=card],div[class*=item]');
             return {href: a.href, text: (a.innerText||'').trim(),
                     ctx: card ? (card.innerText||'').trim().slice(0,400) : ''};
           })""",
    )
    out, seen = [], set()
    base_host = urlparse(url).netloc
    for l in links:
        t = re.sub(r"\s+", " ", l["text"])
        href = l["href"]
        if not t or len(t) < 6 or len(t) > 140 or NOISE.match(t) or href in seen:
            continue
        if not JOB_HREF.search(href) and not JOB_HREF.search(l["ctx"][:60]):
            continue
        if href.rstrip("/") == url.rstrip("/"):
            continue
        seen.add(href)
        d = DATE_TXT.search(l["ctx"])
        t = re.split(r" \| |📣|\bJob Ad\b", t)[0].strip()
        ctx = l["ctx"] if len(l["ctx"]) < 350 else t  # a huge ctx means the whole list, not this job's card
        out.append({"title": t[:140], "location": ctx[:200], "url": href,
                    "posted": d.group(0) if d else None})
    return out


API_CONNECTORS = {
    "oracle": oracle, "workday": workday, "successfactors": successfactors, "eightfold": eightfold,
    "ashby": ashby, "workable": workable, "smartrecruiters": smartrecruiters,
    "greenhouse": greenhouse, "lever": lever,
}


def fetch_detail_text(job, page=None):
    """Full posting text, used for the nationals-only / mandatory-Arabic checks."""
    try:
        if job.get("detail_api"):
            d = _get(job["detail_api"], headers={"Accept": "application/json"}).json()
            it = (d.get("items") or [{}])[0]
            return " ".join(str(it.get(k) or "") for k in
                            ("ExternalDescriptionStr", "ExternalQualificationsStr", "ExternalResponsibilitiesStr"))
        if page is not None:
            page.goto(job["url"], wait_until="domcontentloaded", timeout=40000)
            page.wait_for_timeout(2500)
            return page.inner_text("body")[:20000]
        return BeautifulSoup(_get(job["url"]).text, "lxml").get_text(" ", strip=True)[:20000]
    except Exception as e:
        return f"__detail_error__ {e}"
