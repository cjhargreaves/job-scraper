"""resolve_jobs.py: resolve each job in jobs.jsonl to a direct application page and extract its form fields"""

import json
import os
import sys

import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
JOBS_FILE = os.path.join(BASE_DIR, "jobs.jsonl")
OUT_FILE = os.path.join(BASE_DIR, "jobs_resolved.jsonl")
FALLBACK_ENV = os.path.join(BASE_DIR, "..", "ml-training-data", ".env")
FIRECRAWL_SEARCH = "https://api.firecrawl.dev/v1/search"
FIRECRAWL_SCRAPE = "https://api.firecrawl.dev/v1/scrape"
GROK_ENDPOINT = "https://api.x.ai/v1/chat/completions"
GROK_MODEL = "grok-4.20-0309-non-reasoning"

DIRECT_MARKERS = [
    "greenhouse.io",
    "lever.co",
    "ashbyhq.com",
    "myworkdayjobs.com",
    "workable.com",
    "smartrecruiters.com",
    "jobvite.com",
    "icims.com",
    "amazon.jobs",
    "/careers",
    "careers.",
]

AGGREGATORS = [
    "linkedin.com",
    "indeed.com",
    "glassdoor.com",
    "builtinsf.com",
    "builtin.com",
    "jobleads.com",
    "ziprecruiter.com",
    "simplyhired.com",
]


def load_key(name):
    if os.environ.get(name):
        return os.environ[name]
    for env_path in (os.path.join(BASE_DIR, ".env"), FALLBACK_ENV):
        if os.path.exists(env_path):
            with open(env_path) as env_file:
                for line in env_file:
                    line = line.strip()
                    if line.startswith("export "):
                        line = line[len("export "):]
                    if line.startswith(name + "="):
                        return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def is_direct(url):
    if any(agg in url for agg in AGGREGATORS):
        return False
    return any(marker in url for marker in DIRECT_MARKERS)


def firecrawl_search(api_key, query, limit=5):
    response = requests.post(
        FIRECRAWL_SEARCH,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"query": query, "limit": limit},
        timeout=60,
    )
    if response.status_code != 200:
        print(f"  Firecrawl search error {response.status_code}")
        return []
    return response.json().get("data", [])


def firecrawl_scrape(api_key, url):
    response = requests.post(
        FIRECRAWL_SCRAPE,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"url": url, "formats": ["markdown"]},
        timeout=90,
    )
    if response.status_code != 200:
        print(f"  Firecrawl scrape error {response.status_code}")
        return ""
    return response.json().get("data", {}).get("markdown", "")


def extract_form_fields(grok_key, company, role, markdown):
    prompt = (
        f"Below is the markdown of a job page for '{role}' at {company}. "
        "List the exact fields and questions the application form asks for (for example: name, email, "
        "resume upload, LinkedIn URL, short-answer questions, work authorization, sponsorship, demographics). "
        "If the page has no application form, answer with exactly NO_FORM. "
        "Return ONLY a valid JSON array of short strings, or NO_FORM. No commentary.\n\nPAGE:\n"
        + markdown[:6000]
    )
    response = requests.post(
        GROK_ENDPOINT,
        headers={"Authorization": f"Bearer {grok_key}", "Content-Type": "application/json"},
        json={
            "model": GROK_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
        },
        timeout=120,
    )
    if response.status_code != 200:
        print(f"  Grok error {response.status_code}")
        return []
    content = response.json()["choices"][0]["message"]["content"].strip()
    if "NO_FORM" in content:
        return []
    if content.startswith("```"):
        lines = content.split("\n")
        content = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return []
    return [str(field) for field in parsed] if isinstance(parsed, list) else []


def main():
    firecrawl_key = load_key("FIRECRAWL_API_KEY")
    grok_key = load_key("XAI_API_KEY")
    if not firecrawl_key or not grok_key:
        sys.exit("Missing FIRECRAWL_API_KEY or XAI_API_KEY.")

    with open(JOBS_FILE) as jobs_file:
        jobs = [json.loads(line) for line in jobs_file if line.strip()]

    with open(OUT_FILE, "w") as out_file:
        for job in jobs:
            company = job["company"]
            print(f"\n{company} - {job['role']}")
            url = job["url"]
            resolved = is_direct(url)

            if not resolved:
                results = firecrawl_search(firecrawl_key, f"{company} {job['role']} internship apply")
                for item in results:
                    candidate = item.get("url", "")
                    if is_direct(candidate):
                        url = candidate
                        resolved = True
                        break
            print(f"  url: {url} ({'direct' if resolved else 'UNRESOLVED'})")

            markdown = firecrawl_scrape(firecrawl_key, url)
            accessible = len(markdown) > 500
            print(f"  accessible: {accessible}")

            fields = extract_form_fields(grok_key, company, job["role"], markdown) if accessible else []
            print(f"  form fields: {len(fields)}")

            record = dict(job)
            record["url"] = url
            record["original_url"] = job["url"]
            record["resolved"] = resolved
            record["accessible"] = accessible
            record["form_fields"] = fields
            out_file.write(json.dumps(record) + "\n")
            out_file.flush()

    print(f"\nDone. Results in {OUT_FILE}.")


if __name__ == "__main__":
    main()
