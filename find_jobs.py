"""find_jobs.py: search for software engineering roles with Firecrawl, structure them with Grok, save to jobs.jsonl"""

import hashlib
import json
import os
import re
import sys
import time

import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
JOBS_FILE = os.path.join(BASE_DIR, "jobs.jsonl")
FALLBACK_ENV = os.path.join(BASE_DIR, "..", "ml-training-data", ".env")
FIRECRAWL_SEARCH = "https://api.firecrawl.dev/v1/search"
FIRECRAWL_SCRAPE = "https://api.firecrawl.dev/v1/scrape"
GROK_ENDPOINT = "https://api.x.ai/v1/chat/completions"
GROK_MODEL = "grok-4.5"
SEARCH_LIMIT = 20
CACHE_FILE = os.path.join(BASE_DIR, "cache.json")
CACHE_TTL = 24 * 60 * 60

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
    "infrastructure engineer {term}",
    "platform engineer {term}",
    "systems software engineer {term}",
    "AI engineer {term}",
    "machine learning engineer {term}",
    "ML engineer {term}",
    "machine learning engineer intern {term}",
    "applied machine learning engineer {term}",
    "deep learning engineer {term}",
    "MLOps engineer {term}",
    "AI/ML engineer {term}",
    "DevOps engineer {term}",
    "cloud engineer {term}",
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


ATS_HOSTS = [
    "greenhouse.io",
    "lever.co",
    "ashbyhq.com",
    "myworkdayjobs.com",
    "workable.com",
    "smartrecruiters.com",
    "rippling-ats.com",
    "jobs.dover.com",
    "icims.com",
    "jobvite.com",
]
BOARD_HOSTS = ["ycombinator.com", "workatastartup.com"]
COMPANY_NOISE = re.compile(r"\b(inc|llc|ltd|corp|corporation|co)\b")
ROLE_NOISE = re.compile(
    r"\b(summer|fall|winter|spring|2026|2027|2028|intern|interns|internship|internships|co op|new grad|new graduate)\b"
)
ROLE_SYNONYMS = {"engineering": "engineer", "swe": "software engineer", "sde": "software development engineer"}


COMPANY_BOARDS = {
    "greenhouse": [
        "affirm", "airbnb", "airtable", "andurilindustries", "anthropic", "asana", "brex", "chime", "cloudflare",
        "cockroachlabs", "coinbase", "databricks", "datadog", "discord", "dropbox", "duolingo", "elastic", "faire",
        "figma", "flexport", "gitlab", "grammarly", "gusto", "instacart", "intercom", "lyft", "mongodb",
        "neuralink", "nuro", "okta", "pagerduty", "pinterest", "postman", "reddit", "robinhood", "roblox",
        "samsara", "scaleai", "spacex", "squarespace", "stripe", "toast", "twilio", "twitch", "vercel",
        "verkada", "waymo", "webflow",
    ],
    "lever": ["palantir", "plaid", "spotify", "zoox"],
    "ashby": ["cohere", "cursor", "harvey", "linear", "modal", "notion", "openai", "posthog", "ramp", "replit", "supabase"],
}
BOARD_APIS = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{token}/jobs",
    "lever": "https://api.lever.co/v0/postings/{token}?mode=json",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{token}",
}
BOARD_URL_PATTERNS = {
    "greenhouse": re.compile(r"greenhouse\.io/(?:embed/job_app\?for=)?([A-Za-z0-9_-]+)"),
    "lever": re.compile(r"jobs\.lever\.co/([A-Za-z0-9_.-]+)"),
    "ashby": re.compile(r"jobs\.ashbyhq\.com/([A-Za-z0-9_.-]+)"),
}
NOT_TOKENS = {"embed", "v1", "jobs"}
SIMPLIFY_LISTINGS = {
    "internship": "https://raw.githubusercontent.com/SimplifyJobs/Summer2027-Internships/dev/.github/scripts/listings.json",
    "newgrad": "https://raw.githubusercontent.com/SimplifyJobs/New-Grad-Positions/dev/.github/scripts/listings.json",
}
SIMPLIFY_CATEGORIES = {"Software", "Software Engineering", "AI/ML/Data", "Data Science, AI & Machine Learning"}
SOFTWARE_TITLE = re.compile(
    r"software|engineer|developer|\bswe\b|\bsde\b|machine learning|\bml\b|\bai\b|infrastructure|backend|back end|"
    r"full ?stack|platform|devops|\bsre\b|reliability",
    re.IGNORECASE,
)
EXCLUDED_TITLE = re.compile(
    r"hardware|electrical|mechanical|manufactur|sales|recruit|analyst|accounting|marketing|legal|finance|support|"
    r"technician|verification|asic|fpga|silicon|firmware|embedded|front ?end|\bios\b|android|mobile|game|"
    r"security|quant|research scientist|researcher|data scien",
    re.IGNORECASE,
)
INTERN_TITLE = re.compile(r"\bintern\b|internship|co-?op", re.IGNORECASE)
OFF_SEASON = re.compile(r"\b(fall|winter|spring)\b", re.IGNORECASE)
NEWGRAD_TITLE = re.compile(
    r"new grad|new graduate|university grad|college grad|early career|entry[- ]level|\b(engineer|developer),? i\b",
    re.IGNORECASE,
)
SENIOR_TITLE = re.compile(r"senior|\bsr\b|staff|principal|\blead\b|manager|director|\bii\b|\biii\b|\biv\b", re.IGNORECASE)
US_EXPLICIT = re.compile(r"united states|\bUSA?\b", re.IGNORECASE)
US_STATE = re.compile(
    r"[,\s](AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|"
    r"OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY|DC)\b"
)
US_CITY = re.compile(
    r"new york|nyc|san francisco|seattle|bay area|boston|austin|chicago|los angeles|denver|atlanta|palo alto|"
    r"mountain view|menlo park|sunnyvale|san jose|redmond|remote",
    re.IGNORECASE,
)
NON_US = re.compile(
    r"canada|toronto|vancouver|united kingdom|\buk\b|london|ireland|dublin|india|bangalore|bengaluru|hyderabad|"
    r"germany|berlin|france|paris|netherlands|amsterdam|poland|spain|israel|singapore|japan|tokyo|australia|"
    r"sydney|brazil|mexico|china|hong kong|korea|taiwan|switzerland|zurich|sweden|europe|emea|apac|latam",
    re.IGNORECASE,
)


def normalize(text):
    return " ".join(re.sub(r"[^a-z0-9]+", " ", str(text).lower()).split())


def job_key(listing):
    company = " ".join(COMPANY_NOISE.sub(" ", normalize(listing.get("company", ""))).split())
    role_words = [ROLE_SYNONYMS.get(word, word) for word in normalize(listing.get("role", "")).split()]
    role = " ".join(ROLE_NOISE.sub(" ", " ".join(role_words)).split())
    return f"{listing.get('kind') or 'internship'}|{company}|{role}"


def source_rank(url):
    if any(host in url for host in ATS_HOSTS):
        return 0
    if "linkedin.com" in url:
        return 3
    if any(host in url for host in BOARD_HOSTS):
        return 2
    return 1


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


def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE) as cache_file:
                return json.load(cache_file)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


CACHE = load_cache()


def cache_get(key):
    entry = CACHE.get(key)
    if entry and time.time() - entry["ts"] < CACHE_TTL:
        return entry["value"]
    return None


def cache_set(key, value):
    CACHE[key] = {"ts": time.time(), "value": value}
    try:
        with open(CACHE_FILE, "w") as cache_file:
            json.dump(CACHE, cache_file)
    except OSError:
        pass


def search_firecrawl(api_key, query):
    key = f"search:{query}"
    cached = cache_get(key)
    if cached is not None:
        return cached
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
    joined = "\n\n---\n\n".join(chunks)
    cache_set(key, joined)
    return joined


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
    cache_key = f"grok:{mode}:{hashlib.sha1(raw_text.encode()).hexdigest()}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached
    prompt = (
        f"Extract {settings['prompt_kind']} "
        "Keep only roles located in the United States (any city, or US remote). "
        "Software engineering means: software engineer, SWE, software developer, full stack, backend, "
        "infrastructure, platform, systems software, DevOps, cloud, "
        "AI/ML engineer, member of "
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
    cache_set(cache_key, kept)
    return kept


def firecrawl_scrape(api_key, url):
    key = f"scrape:{url}"
    cached = cache_get(key)
    if cached is not None:
        return cached
    response = requests.post(
        FIRECRAWL_SCRAPE,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"url": url, "formats": ["markdown"]},
        timeout=90,
    )
    if response.status_code != 200:
        print(f"  Firecrawl scrape error {response.status_code}")
        return ""
    markdown = response.json().get("data", {}).get("markdown", "")
    cache_set(key, markdown)
    return markdown


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


def wanted_title(title, mode):
    if not SOFTWARE_TITLE.search(title) or EXCLUDED_TITLE.search(title):
        return False
    if set(re.findall(r"20\d\d", title)) - {"2027"}:
        return False
    if mode == "internship":
        return bool(INTERN_TITLE.search(title)) and not OFF_SEASON.search(title)
    return bool(NEWGRAD_TITLE.search(title)) and not INTERN_TITLE.search(title) and not SENIOR_TITLE.search(title)


def is_us(location):
    if not location.strip() or US_EXPLICIT.search(location):
        return True
    if NON_US.search(location):
        return False
    return bool(US_STATE.search(location) or US_CITY.search(location))


def board_tokens(urls):
    tokens = {ats: set(names) for ats, names in COMPANY_BOARDS.items()}
    for url in urls:
        for ats, pattern in BOARD_URL_PATTERNS.items():
            match = pattern.search(url)
            if match and match.group(1).lower() not in NOT_TOKENS:
                tokens[ats].add(match.group(1).lower())
    return tokens


def company_name(token):
    return token.replace("-", " ").replace("_", " ").title()


def fetch_board(ats, token):
    key = f"board:{ats}:{token}"
    cached = cache_get(key)
    if cached is not None:
        return cached
    try:
        response = requests.get(BOARD_APIS[ats].format(token=token), timeout=30)
    except requests.RequestException:
        return []
    if response.status_code != 200:
        cache_set(key, False)
        return False
    data = response.json()
    if ats == "greenhouse":
        jobs = [
            {
                "company": job.get("company_name") or company_name(token),
                "role": job.get("title", ""),
                "location": (job.get("location") or {}).get("name", ""),
                "url": f"https://job-boards.greenhouse.io/{token}/jobs/{job['id']}",
            }
            for job in data.get("jobs", [])
        ]
    elif ats == "lever":
        jobs = [
            {
                "company": company_name(token),
                "role": job.get("text", ""),
                "location": (job.get("categories") or {}).get("location") or "",
                "url": job.get("hostedUrl", ""),
            }
            for job in data
        ]
    else:
        jobs = [
            {
                "company": company_name(token),
                "role": job.get("title", ""),
                "location": job.get("location") or "",
                "url": job.get("jobUrl", ""),
            }
            for job in data.get("jobs", [])
        ]
    jobs = [job for job in jobs if SOFTWARE_TITLE.search(job["role"]) and not EXCLUDED_TITLE.search(job["role"])]
    cache_set(key, jobs)
    return jobs


def scrape_boards(mode, tokens, done, on_new, log):
    total_new = 0
    for ats, names in tokens.items():
        names = sorted(names - done[ats])
        if not names:
            continue
        done[ats].update(names)
        log(f"{ats}: checking {len(names)} boards...")
        listings = []
        dead = []
        for token in names:
            jobs = fetch_board(ats, token)
            if jobs is False:
                dead.append(token)
                continue
            for job in jobs:
                if job["url"] and wanted_title(job["role"], mode) and is_us(job["location"]):
                    listings.append({**job, "deadline": "", "season": MODES[mode]["season"], "kind": mode})
        count = on_new(listings)
        log(f"{ats}: {len(listings)} matching roles, {count} new.")
        if dead:
            log(f"{ats}: no board found for {', '.join(dead)}")
        total_new += count
    return total_new


def simplify_title_ok(title, mode):
    if not SOFTWARE_TITLE.search(title) or EXCLUDED_TITLE.search(title):
        return False
    if set(re.findall(r"20\d\d", title)) - {"2027"}:
        return False
    return mode == "internship" or not (INTERN_TITLE.search(title) or SENIOR_TITLE.search(title))


def fetch_simplify(mode, log):
    key = f"simplify:{mode}"
    cached = cache_get(key)
    if cached is not None:
        return cached
    try:
        response = requests.get(SIMPLIFY_LISTINGS[mode], timeout=120)
    except requests.RequestException as error:
        log(f"Simplify: request failed ({error}).")
        return []
    if response.status_code != 200:
        log(f"Simplify: error {response.status_code}.")
        return []
    listings = []
    for item in response.json():
        if not item.get("active") or not item.get("is_visible", True):
            continue
        if item.get("category") not in SIMPLIFY_CATEGORIES:
            continue
        if mode == "internship" and "Summer 2027" not in item.get("terms", []):
            continue
        title = item.get("title", "")
        locations = item.get("locations") or []
        if not simplify_title_ok(title, mode) or not any(is_us(place) for place in locations or [""]):
            continue
        listings.append({
            "company": item.get("company_name", ""),
            "role": title,
            "location": "; ".join(locations),
            "url": item.get("url", ""),
            "deadline": "",
            "season": MODES[mode]["season"],
            "kind": mode,
        })
    cache_set(key, listings)
    return listings


def save_listings(listings, seen):
    count = 0
    with open(JOBS_FILE, "a") as jobs_file:
        for listing in listings:
            url = listing.get("url", "")
            key = job_key(listing)
            if url and key not in seen:
                seen.add(key)
                jobs_file.write(json.dumps(listing) + "\n")
                count += 1
    return count


def collect_listings(on_new, mode="internship", log=print, known_urls=(), boards_only=False):
    if mode not in MODES:
        raise RuntimeError(f"Unknown mode {mode!r}. Choose from {list(MODES)}.")
    log("Simplify: loading list...")
    simplify = fetch_simplify(mode, log)
    total_new = on_new(simplify)
    log(f"Simplify: {len(simplify)} matching roles, {total_new} new.")
    known_urls = [*known_urls, *(listing["url"] for listing in simplify)]
    done = {ats: set() for ats in BOARD_APIS}
    total_new += scrape_boards(mode, board_tokens(known_urls), done, on_new, log)
    if boards_only:
        return total_new

    firecrawl_key = load_key("FIRECRAWL_API_KEY")
    grok_key = load_key("XAI_API_KEY")
    if not firecrawl_key or not grok_key:
        raise RuntimeError("Missing FIRECRAWL_API_KEY or XAI_API_KEY.")

    found_urls = set(known_urls)

    def record(listings):
        found_urls.update(listing.get("url", "") for listing in listings)
        return on_new(listings)

    for query in build_queries(mode):
        log(f"Searching: {query}")
        raw = search_firecrawl(firecrawl_key, query)
        if not raw:
            continue
        listings = structure_with_grok(grok_key, raw, mode)
        count = record(listings)
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
        count = record(listings)
        log(f"{name}: {count} new listings ({len(listings)} extracted).")
        total_new += count

    total_new += scrape_boards(mode, board_tokens(found_urls), done, on_new, log)
    return total_new


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "internship"
    seen = set()
    known_urls = []
    if os.path.exists(JOBS_FILE):
        with open(JOBS_FILE) as jobs_file:
            for line in jobs_file:
                try:
                    listing = json.loads(line)
                except json.JSONDecodeError:
                    continue
                seen.add(job_key(listing))
                known_urls.append(listing.get("url", ""))

    try:
        total_new = collect_listings(
            lambda listings: save_listings(listings, seen), mode=mode, known_urls=known_urls
        )
    except RuntimeError as error:
        sys.exit(str(error))

    print(f"\nDone. {total_new} new listings saved to {JOBS_FILE}.")


if __name__ == "__main__":
    main()
