# job-scraper

Finds software engineering internships and new grad roles, shows them on a web page, and tracks which ones you applied to.

## What it uses

- Firecrawl to search the web and scrape job boards
- Grok (xAI) to pull structured listings out of the search results
- FastAPI for the web app and API
- SQLite for storage
- Fly.io for hosting, with a volume so the database persists

## What it makes

- A list of open roles with an apply link
- An applied list
- A trash list

## Run locally

```
uv sync
uv run uvicorn server:app --reload
```

Needs `FIRECRAWL_API_KEY` and `XAI_API_KEY` in `.env`.
