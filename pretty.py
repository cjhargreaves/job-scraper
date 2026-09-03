"""pretty.py: rewrite jobs.md from jobs_resolved.jsonl (or jobs.jsonl) in a readable format"""

import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SEASON = "summer 2027"


def load(path):
    if not os.path.exists(path):
        return []
    with open(path) as source:
        return [json.loads(line) for line in source if line.strip()]


def is_season(job):
    season = str(job.get("season", "")).strip().lower()
    if season:
        return season == SEASON
    return SEASON in job.get("role", "").lower()


def main():
    jobs = load(os.path.join(BASE_DIR, "jobs_resolved.jsonl")) or load(os.path.join(BASE_DIR, "jobs.jsonl"))
    jobs = [job for job in jobs if is_season(job)]
    lines = [f"# Internship targets ({SEASON})\n"]
    for job in jobs:
        lines.append(f"## {job['company']} - {job['role']}")
        lines.append(f"- Location: {job.get('location', '')}")
        lines.append(f"- Apply: {job['url']}")
        if job.get("deadline"):
            lines.append(f"- Deadline: {job['deadline']}")
        if job.get("form_fields"):
            lines.append("- Form fields: " + ", ".join(job["form_fields"]))
        lines.append("")
    out_path = os.path.join(BASE_DIR, "jobs.md")
    with open(out_path, "w") as out_file:
        out_file.write("\n".join(lines))
    print(f"Wrote {out_path} ({len(jobs)} jobs).")


if __name__ == "__main__":
    main()
