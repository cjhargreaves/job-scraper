# job-scraper

Finds software engineering internships and new grad roles, shows them on a web page, and tracks which ones you applied to.

## What it uses

- Firecrawl to search the web and scrape job boards
- Grok (xAI) to pull structured listings out of the search results
- FastAPI for the web app and API
- SQLite for storage
- Fly.io for hosting, with a volume so the database persists

## What it makes

- A page with a "Find roles" button. Pick summer internship 2027 or new grad 2027, click, and it searches ~120 queries and adds anything new to the database.
- An open roles list with an Apply button per row, plus mark-applied and trash icons.
- An applied page and a trash page. Trashed roles never come back on a rerun.

## Run locally

```
uv sync
uv run uvicorn server:app --reload
```

Needs `FIRECRAWL_API_KEY` and `XAI_API_KEY` in `.env`.

## Deploy

```
fly launch --no-deploy --copy-config
fly volumes create jobs_data --region sjc --size 1
fly secrets set APP_PASSWORD='...' FIRECRAWL_API_KEY='...' XAI_API_KEY='...'
fly deploy
```

The browser prompts for a password. Username is ignored.
