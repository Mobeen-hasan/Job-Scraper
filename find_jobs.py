#!/usr/bin/env python3
"""Fetch new jobs from the Adzuna API and write them to a dated CSV."""
import csv
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

import requests

ROOT = Path(__file__).parent
API = "https://api.adzuna.com/v1/api/jobs/{country}/search/1"


def load_env():
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def fetch(cfg, title, app_id, app_key):
    params = {
        "app_id": app_id,
        "app_key": app_key,
        "what": title,
        "results_per_page": cfg.get("results_per_page", 50),
        "max_days_old": cfg.get("max_days_old", 1),
        "sort_by": "date",
    }
    if cfg.get("location"):
        params["where"] = cfg["location"]
        params["distance"] = cfg.get("distance_km", 50)
    r = requests.get(API.format(country=cfg.get("country", "us")), params=params, timeout=30)
    r.raise_for_status()
    return r.json().get("results", [])


def main():
    load_env()
    app_id, app_key = os.environ.get("ADZUNA_APP_ID"), os.environ.get("ADZUNA_APP_KEY")
    if not app_id or not app_key:
        sys.exit("Set ADZUNA_APP_ID and ADZUNA_APP_KEY (in .env or environment).")

    cfg = json.loads((ROOT / "config.json").read_text())
    # whole-word match on the job title only, so "lead" doesn't hit "leadership"
    words = [re.escape(w) for w in cfg.get("exclude_words", [])]
    exclude_re = re.compile(r"(?<!\w)(?:%s)(?!\w)" % "|".join(words), re.I) if words else None

    seen_file = ROOT / "seen.json"
    seen = set(json.loads(seen_file.read_text())) if seen_file.exists() else set()

    new_jobs = {}
    for title in cfg["titles"]:
        for job in fetch(cfg, title, app_id, app_key):
            jid = str(job["id"])
            if jid in seen or jid in new_jobs:
                continue
            if exclude_re and exclude_re.search(job.get("title", "")):
                continue
            new_jobs[jid] = job

    out_dir = ROOT / "output"
    out_dir.mkdir(exist_ok=True)
    out = out_dir / f"jobs-{date.today().isoformat()}.csv"
    with out.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["title", "company", "location", "salary_min", "salary_max", "posted", "link"])
        for j in new_jobs.values():
            w.writerow([
                j.get("title", "").replace("<strong>", "").replace("</strong>", ""),
                j.get("company", {}).get("display_name", ""),
                j.get("location", {}).get("display_name", ""),
                j.get("salary_min", ""),
                j.get("salary_max", ""),
                j.get("created", ""),
                j.get("redirect_url", ""),
            ])

    seen.update(new_jobs)
    seen_file.write_text(json.dumps(sorted(seen)))
    print(f"{len(new_jobs)} new jobs -> {out} (Jobs by Adzuna)")


if __name__ == "__main__":
    main()
