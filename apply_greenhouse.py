"""apply_greenhouse.py: open a Greenhouse application in a browser, fill it from profile.json, and leave submit to you"""

import json
import os
import re
import sys

import requests
from playwright.sync_api import sync_playwright

import find_jobs

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROFILE_FILE = os.path.join(BASE_DIR, "profile.json")
QUESTIONS_API = "https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{job_id}?questions=true"
FORM_URL = "https://job-boards.greenhouse.io/{board}/jobs/{job_id}"
STANDARD_FIELDS = {"first_name", "last_name", "email", "phone", "resume"}
LABEL_RULES = [
    (r"linkedin", "linkedin"),
    (r"github", "github"),
    (r"website|portfolio|personal site", "website"),
    (r"hispanic|latino", "hispanic"),
    (r"gender", "gender"),
    (r"race|ethnic", "race"),
    (r"veteran", "veteran"),
    (r"disabilit", "disability"),
    (r"sponsor", "needs_sponsorship"),
    (r"export control|protected individual|citizen|permanent resident", "citizenship"),
    (r"authori[sz]|legally (eligible|able|permitted)|eligible to work", "authorized_us"),
    (r"in[- ]person|on[- ]?site|relocat", "willing_in_person"),
    (r"return(ing)? to school|continue .*stud", "returning_to_school"),
    (r"school|university|college", "school"),
    (r"degree", "degree"),
    (r"major|field of study|discipline", "major"),
    (r"graduat", "graduation"),
    (r"pronoun", "pronouns"),
    (r"how did you hear", "referral_source"),
    (r"location|city|where are you (based|located)", "location"),
    (r"first name", "first_name"),
    (r"last name", "last_name"),
    (r"e-?mail", "email"),
    (r"phone", "phone"),
]


def parse_url(url):
    match = re.search(r"greenhouse\.io/([^/?#]+)/jobs/(\d+)", url)
    if match:
        return match.group(1), match.group(2)
    board = re.search(r"[?&]for=([^&#]+)", url)
    token = re.search(r"[?&]token=(\d+)", url)
    if board and token:
        return board.group(1), token.group(1)
    sys.exit(f"Not a Greenhouse job URL: {url}")


def profile_key(label):
    for pattern, key in LABEL_RULES:
        if re.search(pattern, label, re.IGNORECASE):
            return key
    return None


def pick_option(options, wanted):
    if not wanted:
        return None
    target = wanted.lower()
    for test in (str.startswith, str.__contains__):
        for option in options:
            if test(option.lower(), target):
                return option
    first_word = target.split()[0]
    for option in options:
        if first_word in option.lower():
            return option
    return None


def ask_grok(api_key, profile, label, options):
    facts = {key: value for key, value in profile.items() if key != "resume" and value is not None}
    if options:
        instruction = "Reply with exactly one of these options, copied verbatim: " + json.dumps(options) + "."
    else:
        instruction = "Reply with the answer only, plain text, first person, under 120 words."
    prompt = (
        "You are filling out a job application for this candidate.\n"
        f"Candidate facts: {json.dumps(facts)}\n"
        f"Question: {label}\n{instruction} "
        "If the question asks for a personal fact that is not in the candidate facts (work authorization, "
        "sponsorship, start date, salary, address, demographics), reply with exactly UNKNOWN."
    )
    response = requests.post(
        find_jobs.GROK_ENDPOINT,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"model": find_jobs.GROK_MODEL, "messages": [{"role": "user", "content": prompt}], "temperature": 0.2},
        timeout=120,
    )
    if response.status_code != 200:
        print(f"  Grok error {response.status_code}")
        return None
    answer = response.json()["choices"][0]["message"]["content"].strip()
    if answer == "UNKNOWN":
        return None
    if options:
        return pick_option(options, answer)
    return answer


def plan_answers(questions, profile, grok_key):
    plan = []
    skipped = []
    for question in questions:
        label = question.get("label", "")
        for field in question.get("fields", []):
            name = field["name"]
            kind = field["type"]
            options = [value["label"] for value in field.get("values", [])]
            if kind == "input_hidden":
                continue
            if name == "resume":
                with open(profile["resume"], "rb") as resume_file:
                    upload = {"name": profile["resume_name"], "mimeType": "application/pdf", "buffer": resume_file.read()}
                plan.append((field, upload))
                continue
            if kind == "input_file":
                if question.get("required"):
                    skipped.append(label)
                continue
            key = name if name in STANDARD_FIELDS else profile_key(label)
            wanted = profile.get(key) if key else None
            answer = pick_option(options, wanted) if wanted and options else wanted
            if answer is None and question.get("required") and grok_key and (not key or wanted):
                print(f"  Asking Grok: {label}")
                answer = ask_grok(grok_key, profile, label, options)
            if answer is None:
                if question.get("required"):
                    skipped.append(label)
                continue
            plan.append((field, answer))
    return plan, skipped


def fill_field(page, field, value):
    locator = page.locator(f"[id='{field['name']}']").first
    if field["type"] == "input_file":
        locator.set_input_files(value)
    elif field["type"] in ("input_text", "textarea"):
        locator.fill(value)
    elif locator.evaluate("node => node.tagName") == "SELECT":
        locator.select_option(label=value)
    else:
        locator.click()
        page.keyboard.type(value)
        page.wait_for_timeout(1000)
        page.keyboard.press("Enter")


def page_only_fields(profile):
    month, year = profile["graduation"].split()
    return [
        ("country", "United States"),
        ("school--0", profile["school"]),
        ("degree--0", profile["degree"]),
        ("discipline--0", profile["major"]),
        ("end-month--0", month),
        ("end-year--0", year),
        ("gender", profile["gender"]),
        ("hispanic_ethnicity", profile["hispanic"]),
        ("race", profile["race"]),
        ("veteran_status", profile["veteran"]),
        ("disability_status", profile["disability"]),
    ]


def main():
    if len(sys.argv) < 2:
        sys.exit("Usage: python apply_greenhouse.py <greenhouse job url>")
    board, job_id = parse_url(sys.argv[1])
    with open(PROFILE_FILE) as profile_file:
        profile = json.load(profile_file)
    if not os.path.exists(profile["resume"]):
        sys.exit(f"Resume not found: {profile['resume']}")

    response = requests.get(QUESTIONS_API.format(board=board, job_id=job_id), timeout=30)
    if response.status_code != 200:
        sys.exit(f"Greenhouse API error {response.status_code} for {board}/{job_id}")
    data = response.json()
    print(f"{data.get('title', '')} at {board}")
    questions = data.get("questions", []) + data.get("location_questions", [])
    plan, skipped = plan_answers(questions, profile, find_jobs.load_key("XAI_API_KEY"))

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        page = browser.new_page()
        page.set_default_timeout(5000)
        page.goto(FORM_URL.format(board=board, job_id=job_id))
        page.wait_for_load_state("networkidle")
        filled = 0
        for field, value in plan:
            try:
                fill_field(page, field, value)
                filled += 1
            except Exception as error:
                skipped.append(f"{field['name']} ({type(error).__name__})")
        for name, value in page_only_fields(profile):
            if page.locator(f"[id='{name}']").count() == 0:
                continue
            try:
                fill_field(page, {"name": name, "type": "multi_value_single_select"}, value)
                filled += 1
            except Exception as error:
                skipped.append(f"{name} ({type(error).__name__})")
        print(f"Filled {filled} fields.")
        if skipped:
            print("Fill these yourself:")
            for label in skipped:
                print(f"  - {label}")
        print("Review the form, submit it, then close the browser window.")
        page.wait_for_event("close", timeout=0)
        browser.close()


if __name__ == "__main__":
    main()
