"""find_jobs.py: search for software engineering roles with Firecrawl, structure them with Grok, save to jobs.jsonl"""

import json
import os
import sys

import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
JOBS_FILE = os.path.join(BASE_DIR, "jobs.jsonl")
FALLBACK_ENV = os.path.join(BASE_DIR, "..", "ml-training-data", ".env")
FIRECRAWL_SEARCH = "https://api.firecrawl.dev/v1/search"
FIRECRAWL_SCRAPE = "https://api.firecrawl.dev/v1/scrape"
GROK_ENDPOINT = "https://api.x.ai/v1/chat/completions"
GROK_MODEL = "grok-4.20-0309-non-reasoning"
SEARCH_LIMIT = 20

MODES = {
    "internship": {
        "label": "Summer internship 2027",
        "term": "intern summer 2027",
        "season": "summer 2027",
        "yc_query": "software-engineer-intern-summer-2027",
        "linkedin_keywords": "software+engineer+intern+summer+2027",
        "linkedin_level": "1",
        "prompt_kind": (
            "software engineering INTERNSHIP listings for SUMMER 2027. Skip new-grad / full-time positions. "
            "Skip roles for a different term (winter, fall, spring, summer 2026, summer 2028)."
        ),
        "prompt_season": (
            "season is the internship term as stated or clearly implied by the posting, normalized to the form "
            "'summer 2027', 'winter 2027', 'fall 2026', etc. Use 'unknown' if no term is given."
        ),
    },
    "newgrad": {
        "label": "New grad 2027",
        "term": "new grad 2027",
        "season": "new grad 2027",
        "yc_query": "software-engineer-new-grad-2027",
        "linkedin_keywords": "software+engineer+new+grad+2027",
        "linkedin_level": "2",
        "prompt_kind": (
            "entry-level / NEW GRAD software engineering listings for candidates graduating in 2027 or starting "
            "in 2027. These are full-time roles labeled new grad, early career, university graduate, entry level, "
            "or 'Software Engineer I' with 0-1 years experience. Skip internships. Skip roles requiring 2+ years "
            "of experience. Skip roles explicitly for 2026 grads only."
        ),
        "prompt_season": (
            "season is 'new grad 2027' if the posting targets 2027 graduates, a 2027 start date, or is a new-grad "
            "posting open now with no year stated. Otherwise use the stated year, e.g. 'new grad 2026', or 'unknown'."
        ),
    },
}

ATS_SITES = [
    "greenhouse.io",
    "lever.co",
    "ashbyhq.com",
    "myworkdayjobs.com",
    "workable.com",
    "smartrecruiters.com",
    "icims.com",
    "jobvite.com",
    "wd1.myworkdayjobs.com",
    "wd5.myworkdayjobs.com",
    "linkedin.com/jobs/view",
    "workatastartup.com",
    "ycombinator.com/companies",
    "rippling-ats.com",
    "jobs.dover.com",
    "boards.greenhouse.io",
    "job-boards.greenhouse.io",
]

COMPANY_SITES = [
    "careers.google.com",
    "metacareers.com",
    "amazon.jobs",
    "careers.microsoft.com",
    "jobs.apple.com",
    "nvidia.com/en-us/about-nvidia/careers",
    "stripe.com/jobs",
    "jobs.netflix.com",
    "careers.salesforce.com",
    "uber.com/careers",
    "careers.airbnb.com",
    "jobs.lyft.com",
    "careers.doordash.com",
    "snap.com/jobs",
    "careers.roblox.com",
    "jobs.coinbase.com",
    "careers.palantir.com",
    "anthropic.com/careers",
    "openai.com/careers",
    "databricks.com/company/careers",
    "careers.tiktok.com",
    "jobs.bloomberg.com",
    "capitalone.com/careers",
    "jpmorganchase.com/careers",
    "goldmansachs.com/careers",
    "citadel.com/careers",
    "janestreet.com/join-jane-street",
    "hudsonrivertrading.com/careers",
    "twosigma.com/careers",
    "ibm.com/careers",
    "intel.com/jobs",
    "amd.com/careers",
    "qualcomm.com/company/careers",
    "cisco.com/careers",
    "oracle.com/careers",
    "adobe.com/careers",
    "atlassian.com/company/careers",
    "shopify.com/careers",
    "careers.walmart.com",
    "jobs.lockheedmartin.com",
    "boeing.com/careers",
    "spacex.com/careers",
    "tesla.com/careers",
]

GENERIC_TEMPLATES = [
    "software engineer {term}",
    "software engineering {term}",
    "software development engineer {term}",
    "SWE {term}",
    "software engineer {term} United States",
    "2027 software engineer {term}",
    "full stack engineer {term}",
    "backend engineer {term}",
    "frontend engineer {term}",
    "mobile engineer {term}",
    "infrastructure engineer {term}",
    "platform engineer {term}",
    "systems software engineer {term}",
    "embedded software engineer {term}",
    "AI engineer {term}",
    "machine learning engineer {term}",
    "research engineer {term}",
    "security engineer {term}",
    "DevOps engineer {term}",
    "cloud engineer {term}",
    "game engineer {term}",
    "quant developer {term}",
    "software engineer {term} remote",
    "software engineer {term} New York",
    "software engineer {term} Seattle",
    "software engineer {term} San Francisco",
    "software engineer {term} Austin",
    "software engineer {term} Boston",
    "software engineer {term} Chicago",
    "software engineer {term} Los Angeles",
    "software engineer {term} Denver",
    "software engineer {term} Atlanta",
    "software engineer {term} Washington DC",
    "software engineer {term} startup",
    "software engineer {term} YC startup",
    "software engineer {term} fintech",
    "software engineer {term} defense",
    "software engineer {term} healthcare",
    "software engineer {term} robotics",
    "software engineer {term} hedge fund",
    "software engineer {term} bank",
]

LIST_TEMPLATES = [
    "site:github.com {term} software engineering list",
    "site:github.com 2027 SWE {term} README",
    "{term} software engineering positions list",
    "{term} tech roles open now",
    "site:reddit.com {term} software open",
    "site:levels.fyi {term}",
    "site:ripplematch.com software engineer {term}",
    "site:joinhandshake.com software engineer {term}",
    "site:wellfound.com software engineer {term}",
    "site:builtin.com software engineer {term}",
    "site:simplify.jobs software engineer {term}",
    "site:jobright.ai software engineer {term}",
    "site:untapped.io software engineer {term}",
    "site:wayup.com software engineer {term}",
]

MODE_LIST_QUERIES = {
    "internship": ["site:github.com Summer2027-Internships"],
    "newgrad": ["site:github.com New-Grad-Positions 2027"],
}


def build_queries(mode):
    term = MODES[mode]["term"]
    return (
        [f"site:{site} software engineer {term}" for site in ATS_SITES]
        + [f"site:{site} software engineer {term}" for site in COMPANY_SITES]
        + [template.format(term=term) for template in GENERIC_TEMPLATES]
        + [template.format(term=term) for template in LIST_TEMPLATES]
        + MODE_LIST_QUERIES[mode]
    )


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


def search_firecrawl(api_key, query):
    response = requests.post(
        FIRECRAWL_SEARCH,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"query": query, "limit": SEARCH_LIMIT},
        timeout=60,
    )
    if response.status_code != 200:
        print(f"Firecrawl error {response.status_code}: {response.text}")
        return ""
    results = response.json().get("data", [])
    chunks = []
    for item in results:
        body = item.get("markdown") or item.get("description") or ""
        chunks.append(f"URL: {item.get('url', '')}\nTITLE: {item.get('title', '')}\n{body[:8000]}")
    return "\n\n---\n\n".join(chunks)


def extract_listings(content):
    content = content.strip()
    if content.startswith("```"):
        lines = content.split("\n")
        content = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])
    try:
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            parsed = [parsed]
        return [item for item in parsed if isinstance(item, dict) and "url" in item]
    except json.JSONDecodeError:
        pass
    listings = []
    decoder = json.JSONDecoder()
    index = 0
    while index < len(content):
        while index < len(content) and content[index] not in "{[":
            index += 1
        if index >= len(content):
            break
        try:
            obj, end = decoder.raw_decode(content, index)
        except json.JSONDecodeError:
            index += 1
            continue
        index = end
        if isinstance(obj, dict) and "url" in obj:
            listings.append(obj)
        elif isinstance(obj, list):
            listings.extend(item for item in obj if isinstance(item, dict) and "url" in item)
    return listings


def structure_with_grok(api_key, raw_text, mode):
    settings = MODES[mode]
    prompt = (
        f"Extract {settings['prompt_kind']} "
        "Keep only roles located in the United States (any city, or US remote). "
        "Software engineering means: software engineer, SWE, software developer, full stack, backend, "
        "frontend, mobile, infrastructure, platform, embedded software, systems software, DevOps, cloud, "
        "security engineer, game engineer, quant developer, AI/ML engineer, research engineer, member of "
        "technical staff, applied AI engineer. Skip data science/analytics, QA/test, IT support, product "
        "management, and hardware/electrical roles. Skip roles that say they are closed or expired. "
        "If a page is a list of many roles (a GitHub README, a blog post, a job board), extract every "
        "matching software engineering row on it that has its own apply link. "
        "The url should be a direct application page: a company careers page, an ATS (greenhouse.io, "
        "lever.co, ashbyhq.com, myworkdayjobs.com, workable.com), a LinkedIn individual job posting "
        "(linkedin.com/jobs/view/*), or a Y Combinator startup listing (ycombinator.com/*, "
        "workatastartup.com/*). Skip aggregators that redirect (indeed.com, glassdoor.com, builtin.com, "
        "ziprecruiter.com). "
        "Return ONLY a valid JSON array of objects, each with exactly these string fields: "
        "company, role, location, url, deadline (empty string if unknown), season. "
        f"{settings['prompt_season']} "
        "Do not include any other fields. "
        "No markdown, no commentary.\n\nRESULTS:\n" + raw_text
    )
    response = requests.post(
        GROK_ENDPOINT,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": GROK_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
        },
        timeout=180,
    )
    if response.status_code != 200:
        print(f"Grok error {response.status_code}: {response.text}")
        return []
    listings = extract_listings(response.json()["choices"][0]["message"]["content"])
    wanted = settings["season"]
    kept = []
    for item in listings:
        if str(item.get("season", "")).strip().lower() == wanted:
            item["kind"] = mode
            kept.append(item)
    return kept


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


def scrape_yc(api_key, mode):
    url = (
        f"https://www.workatastartup.com/jobs?query={MODES[mode]['yc_query']}"
        "&usVisaNotRequired=any&location=united-states"
    )
    return firecrawl_scrape(api_key, url)


def scrape_linkedin_guest(api_key, mode):
    settings = MODES[mode]
    pages = []
    for start in (0, 25, 50, 75):
        url = (
            "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
            f"?keywords={settings['linkedin_keywords']}"
            f"&location=United+States&f_E={settings['linkedin_level']}&start={start}"
        )
        markdown = firecrawl_scrape(api_key, url)
        if markdown:
            pages.append(markdown)
    return "\n\n---\n\n".join(pages)


def save_listings(listings, seen):
    count = 0
    with open(JOBS_FILE, "a") as jobs_file:
        for listing in listings:
            url = listing.get("url", "")
            if url and url not in seen:
                seen.add(url)
                jobs_file.write(json.dumps(listing) + "\n")
                count += 1
    return count


def collect_listings(on_new, mode="internship", log=print):
    if mode not in MODES:
        raise RuntimeError(f"Unknown mode {mode!r}. Choose from {list(MODES)}.")
    firecrawl_key = load_key("FIRECRAWL_API_KEY")
    grok_key = load_key("XAI_API_KEY")
    if not firecrawl_key or not grok_key:
        raise RuntimeError("Missing FIRECRAWL_API_KEY or XAI_API_KEY.")

    total_new = 0
    for query in build_queries(mode):
        log(f"Searching: {query}")
        raw = search_firecrawl(firecrawl_key, query)
        if not raw:
            continue
        listings = structure_with_grok(grok_key, raw, mode)
        count = on_new(listings)
        log(f"{count} new listings ({len(listings)} extracted).")
        total_new += count

    for name, raw in [
        ("YC", scrape_yc(firecrawl_key, mode)),
        ("LinkedIn", scrape_linkedin_guest(firecrawl_key, mode)),
    ]:
        if not raw:
            log(f"{name}: nothing scraped.")
            continue
        log(f"{name}: structuring with Grok...")
        listings = structure_with_grok(grok_key, raw, mode)
        count = on_new(listings)
        log(f"{name}: {count} new listings ({len(listings)} extracted).")
        total_new += count

    return total_new


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "internship"
    seen = set()
    if os.path.exists(JOBS_FILE):
        with open(JOBS_FILE) as jobs_file:
            for line in jobs_file:
                try:
                    seen.add(json.loads(line)["url"])
                except (json.JSONDecodeError, KeyError):
                    continue

    try:
        total_new = collect_listings(lambda listings: save_listings(listings, seen), mode=mode)
    except RuntimeError as error:
        sys.exit(str(error))

    print(f"\nDone. {total_new} new listings saved to {JOBS_FILE}.")


if __name__ == "__main__":
    main()
