# GCC job scan

Daily scan of GCC employer career sites and job boards for senior strategy, Islamic banking,
corporate development, transformation and growth roles.

- `employers.json` – employers, their careers URL and connector (oracle, workday, successfactors,
  eightfold, ashby, workable, smartrecruiters, greenhouse, lever, browser). Add an employer by adding a row;
  the connector is inferred by `build_registry.py`.
- `boards.json` – job boards / recruiter pages (rendered with the browser connector).
- `main.py`, `connectors.py`, `filters.py` – the scraper. `filters.py` holds the title rules and the nationals-only / mandatory-Arabic exclusions.
- `.github/workflows/scan.yml` – runs daily at 05:17 Gulf time and commits `results/` and `state/`.
- `results/latest.json` – new candidates since the last run; `results/health.json` – per-source status.

A Claude scheduled task reads `results/latest.json` plus LinkedIn alert emails each morning, verifies and scores
the roles against the candidate profile, updates the tracker page and sends the digest.
