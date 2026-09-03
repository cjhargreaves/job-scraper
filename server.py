"""server.py: FastAPI app that runs the internship search and tracks applied roles in SQLite"""

import base64
import json
import os
import secrets
import shutil
import sqlite3
import threading

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import find_jobs

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.environ.get("DB_PATH", os.path.join(BASE_DIR, "jobs.db"))
STATIC_DIR = os.path.join(BASE_DIR, "static")
SEASON = "summer 2027"
APP_PASSWORD = os.environ.get("APP_PASSWORD", "")

app = FastAPI()


@app.middleware("http")
async def require_password(request: Request, call_next):
    if not APP_PASSWORD:
        return await call_next(request)
    header = request.headers.get("authorization", "")
    if header.startswith("Basic "):
        try:
            decoded = base64.b64decode(header[6:]).decode()
            supplied = decoded.split(":", 1)[1] if ":" in decoded else ""
        except (ValueError, UnicodeDecodeError):
            supplied = ""
        if secrets.compare_digest(supplied, APP_PASSWORD):
            return await call_next(request)
    return Response(status_code=401, headers={"WWW-Authenticate": 'Basic realm="internships"'})


search_lock = threading.Lock()
search_state = {"running": False, "log": [], "new_count": 0, "mode": ""}


def connect():
    connection = sqlite3.connect(DB_FILE)
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    local_db = os.path.join(BASE_DIR, "jobs.db")
    if DB_FILE != local_db and not os.path.exists(DB_FILE) and os.path.exists(local_db):
        os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
        shutil.copy(local_db, DB_FILE)
    with connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company TEXT NOT NULL,
                role TEXT NOT NULL,
                location TEXT DEFAULT '',
                url TEXT NOT NULL UNIQUE,
                deadline TEXT DEFAULT '',
                season TEXT DEFAULT '',
                category TEXT DEFAULT 'other',
                kind TEXT NOT NULL DEFAULT 'internship',
                status TEXT NOT NULL DEFAULT 'new',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(jobs)")}
        if "category" not in columns:
            connection.execute("ALTER TABLE jobs ADD COLUMN category TEXT DEFAULT 'other'")
        if "kind" not in columns:
            connection.execute("ALTER TABLE jobs ADD COLUMN kind TEXT NOT NULL DEFAULT 'internship'")
        if "status" not in columns:
            connection.execute("ALTER TABLE jobs ADD COLUMN status TEXT NOT NULL DEFAULT 'new'")
            if "applied" in columns:
                connection.execute("UPDATE jobs SET status = 'applied' WHERE applied = 1")
        count = connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    if count == 0:
        import_jsonl()


def is_season(listing):
    season = str(listing.get("season", "")).strip().lower()
    if season:
        return season == SEASON
    return SEASON in listing.get("role", "").lower()


def import_jsonl():
    if not os.path.exists(find_jobs.JOBS_FILE):
        return
    with open(find_jobs.JOBS_FILE) as jobs_file:
        listings = []
        for line in jobs_file:
            try:
                listings.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    insert_listings([listing for listing in listings if is_season(listing)])


def insert_listings(listings):
    inserted = 0
    with connect() as connection:
        for listing in listings:
            url = listing.get("url", "")
            if not url:
                continue
            cursor = connection.execute(
                "INSERT OR IGNORE INTO jobs (company, role, location, url, deadline, season, kind) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    listing.get("company", ""),
                    listing.get("role", ""),
                    listing.get("location", ""),
                    url,
                    listing.get("deadline", ""),
                    str(listing.get("season", SEASON)).strip().lower(),
                    listing.get("kind", "internship"),
                ),
            )
            inserted += cursor.rowcount
    return inserted


def run_search(mode):
    search_state["log"] = []
    search_state["new_count"] = 0
    search_state["mode"] = mode
    try:
        total = find_jobs.collect_listings(insert_listings, mode=mode, log=search_state["log"].append)
        search_state["new_count"] = total
        search_state["log"].append(f"Done. {total} new listings.")
    except Exception as error:
        search_state["log"].append(f"Error: {error}")
    finally:
        search_state["running"] = False


STATUSES = ("new", "applied", "trashed")


class StatusUpdate(BaseModel):
    status: str


@app.get("/")
def index_page():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/applied")
def applied_page():
    return FileResponse(os.path.join(STATIC_DIR, "applied.html"))


@app.get("/trash")
def trash_page():
    return FileResponse(os.path.join(STATIC_DIR, "trash.html"))


@app.get("/api/jobs")
def list_jobs(status: str | None = None, kind: str | None = None):
    clauses = []
    params = []
    if status is not None:
        clauses.append("status = ?")
        params.append(status)
    if kind:
        clauses.append("kind = ?")
        params.append(kind)
    query = "SELECT * FROM jobs"
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY company ASC, role ASC"
    with connect() as connection:
        rows = connection.execute(query, params).fetchall()
    return [dict(row) for row in rows]


@app.patch("/api/jobs/{job_id}")
def set_status(job_id: int, update: StatusUpdate):
    if update.status not in STATUSES:
        raise HTTPException(status_code=400, detail=f"status must be one of {STATUSES}")
    with connect() as connection:
        cursor = connection.execute("UPDATE jobs SET status = ? WHERE id = ?", (update.status, job_id))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="job not found")
        row = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return dict(row)


@app.post("/api/search")
def start_search(mode: str = "internship"):
    if mode not in find_jobs.MODES:
        raise HTTPException(status_code=400, detail=f"mode must be one of {list(find_jobs.MODES)}")
    with search_lock:
        if search_state["running"]:
            return {"started": False, "running": True}
        search_state["running"] = True
    threading.Thread(target=run_search, args=(mode,), daemon=True).start()
    return {"started": True, "running": True}


@app.get("/api/search/status")
def search_status():
    return search_state


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
init_db()
