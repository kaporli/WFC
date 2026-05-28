# warframe-planner

Warframe build planner — data pipeline and calc engine.

## Data pipeline

Pulls from WFCD (warframe-items), DE Public Export, and Warframe Wiki Lua modules. Outputs normalized JSON to `data/`.

```bash
cd pipeline && npm install
npm run pipeline run          # incremental (skips if upstream unchanged)
npm run pipeline run --fresh  # force full re-fetch
```

## Engine

Python calc engine reads from `data/`.

```bash
cd engine && uv sync
uv run pytest
```
