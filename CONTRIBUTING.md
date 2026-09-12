# Contributing

Thanks for your interest! This is a small personal-health project — issues and
pull requests are welcome.

## Getting set up

See the README for full setup. In short:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m pytest backend/tests      # analytics engine tests (no device needed)

(cd frontend && npm install && npm run build)
```

You can develop the whole UI against generated data — set data mode to demo in
`backend/services/wearable/` — without a real device or Google credentials.

## Guidelines

- **Keep the analytics honest.** Scores must degrade gracefully with missing
  data (lower confidence, never guessed values). New scoring behaviour needs a
  test in `backend/tests`.
- **Config over hard-coding.** Weights and thresholds live in
  `backend/config/scores.toml`. Bump `algorithm_version` when a change alters
  historical scores.
- **Run the checks before opening a PR:** `python -m pytest backend/tests` and
  `cd frontend && npx tsc --noEmit`.
- Keep pull requests focused and describe the reasoning.

## Scope

This is not medical software. Please don't add features that present the output
as diagnosis or medical advice — see the disclaimer in the README.
