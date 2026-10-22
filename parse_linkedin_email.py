"""Parse LinkedIn job emails (plain text from Gmail) into job records.
Usage: python tools/parse_linkedin_email.py email.txt [more.txt ...]  -> JSON on stdout
Each block looks like:  Title \n Company \n Location \n View job: https://www.linkedin.com/comm/jobs/view/<id>/...
"""
import re, sys, json
BLOCK = re.compile(r"\n\s*([^\n]{3,160})\n([^\n]{2,120})\n([^\n]{2,120})\nView job: https?://www\.linkedin\.com/comm/jobs/view/(\d+)")
out, seen = [], set()
for f in sys.argv[1:]:
    txt = "\n" + open(f, encoding="utf-8").read()
    for t, c, l, jid in BLOCK.findall(txt):
        if jid in seen:
            continue
        seen.add(jid)
        t = re.sub(r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) \d{1,2}, \d{4}$", "", t.strip())
        out.append({"title": t.strip(), "company": c.strip(), "location": l.strip(),
                    "url": f"https://www.linkedin.com/jobs/view/{jid}", "source": "LinkedIn email"})
print(json.dumps(out, indent=1, ensure_ascii=False))
