# fitbit-air-recovery

**Open-source recovery, strain and sleep analytics for Fitbit Air data.**

Turn your fitness band's data into WHOOP-style daily scores — **Recovery**,
**Strain** and **Sleep** — with transparent, configurable algorithms. Your data
stays on your own machine.

![CI](https://github.com/SAAD-BELBACHA/fitbit-air-recovery/actions/workflows/ci.yml/badge.svg)
![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)

> **Not medical advice.** This is a personal analytics tool, not a medical
> device. Scores and insights are estimates from consumer-wearable data and can
> be wrong. Don't use them to diagnose or treat anything — talk to a
> professional for health decisions.
>
> Not affiliated with, endorsed by, or sponsored by Fitbit or Google. "Fitbit"
> is used only to describe the data source.

---

## What it does

Your band syncs to the **Google Health API**; this app reads from there and
turns raw measurements into explainable daily scores:

- **Recovery (0–100)** — how ready you are, from HRV, resting HR, sleep,
  respiratory rate, skin temperature and SpO₂ deviations vs. your **personal
  baseline**.
- **Strain (0–21)** — cardiovascular load from continuous heart-rate-reserve
  intensity across the whole day.
- **Sleep score (0–100)** — duration, efficiency, consistency and stage quality,
  plus sleep need and sleep debt.
- **Trends & correlations** — normalized multi-metric overlay; correlations are
  only shown once there are enough days (no fake precision).
- **Health monitor & data explorer** — every metric vs. baseline, raw intraday
  heart rate, and honest data-gap visualization.

Every score carries a **data-quality (confidence)** value. Missing sensors lower
confidence — they are never silently replaced with guesses.

## Honest by design

- Baselines need **≥ 7 real days** (target 28); confidence scales with coverage.
- Correlations are hidden below a minimum sample size.
- Raw measurements and derived analytics are stored separately — raw data is
  never overwritten.
- No claims of medical accuracy; insights are observations, not diagnoses.

## Tech

- **Backend:** Python, FastAPI, SQLAlchemy (SQLite), NumPy — the analytics
  engine is fully testable without the UI (`backend/tests`).
- **Frontend:** React, Vite, TypeScript, Tailwind, ECharts.
- **Provider abstraction:** the analytics engine reads from a `WearableProvider`
  (Google Health, or a deterministic demo generator), so it isn't tied to any
  one device or API.

## Quick start

Requires Python 3.12+ and Node 20+.

```bash
# 1. Backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m pytest backend/tests            # optional: run the analytics tests

# 2. Frontend
cd frontend && npm install && cd ..

# 3. Google Health credentials (to read your own data)
cp .env.example .env                       # then fill in your OAuth client
python authorize.py                        # one-time browser sign-in

# 4. Run it (backend on :8000, Vite dev server on :5173)
./run.sh dev                               # then open http://localhost:5173
```

Press **Sync** in the top bar to import your data. The first sync backfills
history; after that it's incremental.

### Google Health setup

1. Enable the **Google Health API** in a Google Cloud project.
2. Create an **OAuth 2.0 Client** (Web application) and add
   `http://localhost:8080/callback` as an authorized redirect URI.
3. Add your own account under **Test users**.
4. Put the client id/secret in `.env` (see `.env.example`).

> While the OAuth consent screen is in *Testing*, refresh tokens expire after
> 7 days — re-run `python authorize.py`. Publishing the app to *Production*
> removes that limit.

## Self-hosting

The app is local-first. To run it as a single server (the backend serves the
built frontend):

```bash
./run.sh serve        # builds the frontend, serves everything on :8000
```

It holds personal health data, so if you expose it beyond localhost, **set a
password** — HTTP Basic auth turns on automatically when `SIGNALS_PASSWORD` is
set — and put it behind HTTPS. A `Dockerfile` is included for containerized
self-hosting; point a persistent volume at `SIGNALS_DATA_DIR` and
`FITBIT_TOKEN_FILE`.

## Project structure

```
backend/
  api/            FastAPI routes
  models/         SQLAlchemy models (raw vs. derived, kept separate)
  services/
    analytics/    baseline · recovery · strain · sleep · insights · scoring
    wearable/     provider abstraction (Google Health + demo)
  config/         scores.toml — all weights & thresholds
  tests/          analytics engine tests
frontend/         React + Vite + ECharts UI
fitbit_mcp/       Google Health client + OAuth (also usable as an MCP server)
```

## Configuration

All scoring weights, thresholds and status bands live in
[`backend/config/scores.toml`](backend/config/scores.toml). Change them without
touching code; bump `algorithm_version` when a change affects historical scores.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). You can develop the whole app against the
built-in demo data — no device or credentials required.

## License

MIT — see [LICENSE](LICENSE).
