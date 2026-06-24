# GeoSite Advisor — Deployment Guide

> **When to use this:** When you are ready to push the project to a public GitHub repo and/or deploy it to a live server. Run through the checklist in order.

---

## Step 1 — Pre-Flight: Verify What Goes Public

Before any push, confirm this is what git will commit:

```bash
# See exactly what would be pushed (should NOT include data/research/, docs/, weekly_progress/, scripts/)
git status
git diff --cached
```

Run a dry-check to confirm gitignore is working:
```bash
git check-ignore -v data/research/
git check-ignore -v weekly_progress/
git check-ignore -v docs/decisions/
```

All three should return a line showing they are ignored. If any return nothing, the path is NOT being ignored — stop and fix `.gitignore` before proceeding.

---

## Step 2 — Make Sure Public Data Files Are Up to Date

The `data/public/` CSV files must be current before deploying. Check `docs/operations/maintenance.md` for any pending pipeline re-runs.

```bash
# When pipeline scripts exist, run:
# python scripts/export_public.py
# Then verify data/public/ files have recent timestamps
ls -la data/public/
```

Commit the updated public data files if they changed:
```bash
git add data/public/
git commit -m "Update pre-computed public lookup tables"
```

---

## Step 3 — Push to GitHub

```bash
# First time: create the repo on github.com, then:
git remote add origin https://github.com/<your-username>/geosite-advisor.git
git branch -M main
git push -u origin main

# Subsequent pushes:
git push
```

**Confirm on GitHub:** Browse the repo and verify that `data/research/`, `docs/decisions/`, `weekly_progress/`, and `scripts/` folders do NOT appear. Only the public app files and `data/public/` should be visible.

---

## Step 4 — Deploy to a Live Server

**Recommended platform: Railway** (free tier available, GitHub integration, Python/Flask native support)

1. Go to https://railway.app → New Project → Deploy from GitHub repo
2. Railway auto-detects Flask via `requirements.txt` and `app.py`
3. Set environment variables in Railway dashboard:
   - `SECRET_KEY` → generate a random string (e.g., `python -c "import secrets; print(secrets.token_hex(32))"`)
   - `FLASK_DEBUG` → `false`
   - `ENERGYPLUS_DIR` → path where EnergyPlus is installed on the server (if real-time simulation is enabled)
4. Railway assigns a public URL automatically (e.g., `https://geosite-advisor-production.up.railway.app`)

**Alternative: Render** (also free tier, similar process)
- https://render.com → New Web Service → Connect GitHub
- Build command: `pip install -r requirements.txt`
- Start command: `flask run --host=0.0.0.0 --port=$PORT`

**Alternative: Heroku**
- Requires a `Procfile`: `web: flask run --host=0.0.0.0 --port=$PORT`
- `heroku create geosite-advisor && git push heroku main`

---

## Step 5 — Post-Deploy Verification

After deployment, test these manually:

- [ ] `GET /` — home page loads correctly
- [ ] `POST /calculate` with valid inputs — returns a sizing result
- [ ] `GET /references` (when built) — references page loads
- [ ] Direct access to `/data/research/` or `/docs/` — returns 404 or redirect (should NOT expose files)
- [ ] Flask debug mode is OFF (no stack traces visible in browser on errors)

---

## Ongoing: Updating the Live Tool

When you make code changes or update `data/public/` files:

```bash
# 1. Commit changes locally
git add <changed files>
git commit -m "Description of change"

# 2. Push to GitHub (Railway/Render auto-deploys on push)
git push

# 3. Verify the live URL after a minute
```

When only `data/public/` lookup tables change (no code change), update them in place:
```bash
git add data/public/
git commit -m "Refresh pre-computed thermal and load lookup tables"
git push
```

---

## Security Reminders for Production

- `FLASK_DEBUG=false` must be set — debug mode exposes internal code paths
- `SECRET_KEY` must be a strong random value — never the default or a simple string
- No API keys in code — use environment variables only
- The Flask app must not serve files from `data/research/`, `docs/`, or `scripts/` — this is enforced by Flask's routing (only `static/` and explicit routes are served)
