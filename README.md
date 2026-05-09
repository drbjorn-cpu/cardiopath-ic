# CardioPath IC — Consolidated Site

Single Streamlit app with auth gate + four tabs:
1. **📊 IC Dashboard** — full investment committee analysis (bid posture, scenarios, snapshot, tornado, growth-exit heatmap, entry-multiple sensitivity)
2. **🎲 Monte Carlo** — probability simulation
3. **🗳️ Cast Vote** — APPROVE / REJECT / REVISIT (≥15% below proposed)
4. **📈 Vote Results** — live tally with decision logic

---

## Quick start (local)

```bash
cd site
pip install -r requirements.txt
streamlit run app.py
```

Open http://localhost:8501. Any non-empty username and password unlocks the app.

---

## Deployment

### Option A — Streamlit Community Cloud (recommended, free) ⭐

```bash
# From the site/ directory
git init
git add .
git commit -m "CardioPath IC site"

# Push to GitHub
gh repo create cardiopath-ic --private --source=. --push

# Then:
# 1. Go to https://share.streamlit.io
# 2. Sign in with the same GitHub account
# 3. New app → repo: <your-username>/cardiopath-ic, file: app.py
# 4. Deploy → public URL like cardiopath-ic.streamlit.app
```

**Pros:** free, designed for Streamlit, auto-redeploys on git push, public URL.
**Cons:** vote storage is per-instance (`votes.json`); resets if app restarts. For long-running classroom use, fine; for permanent record, export the votes CSV at end of session.

### Option B — Vercel (via Docker container)

Vercel does not run Streamlit natively (Vercel uses serverless functions; Streamlit needs a persistent server). The workaround is to deploy a Docker image:

1. Create `Dockerfile` in this directory:
   ```dockerfile
   FROM python:3.11-slim
   WORKDIR /app
   COPY requirements.txt .
   RUN pip install --no-cache-dir -r requirements.txt
   COPY . .
   EXPOSE 8501
   CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
   ```

2. Vercel (paid plan, ~$20/mo) supports container deployments via the [Build Output API](https://vercel.com/docs/build-output-api). Or use a Vercel-compatible alternative:
   - **Fly.io** (free tier) — `fly launch` from this dir
   - **Render.com** (free tier) — connect GitHub repo
   - **Railway** (free tier) — same

3. Cleanest production deploy if Vercel is required: use Vercel for a static landing page that links to the Streamlit Cloud app URL.

### Option C — Hugging Face Spaces

```bash
# Create a Hugging Face Space (Streamlit SDK)
# Push the contents of site/ to the Space's git repo
# Public URL: huggingface.co/spaces/<your-handle>/cardiopath-ic
```

---

## File layout

```
site/
├── app.py                  # Main entry: auth gate + tabs
├── dashboard_tab.py        # IC Dashboard render() function
├── montecarlo_tab.py       # Monte Carlo render() function
├── vote_tab.py             # render_vote() and render_results()
├── verify.py               # LBO model logic (model() + CARDIO config)
├── votes.json              # Vote storage (created on first vote)
├── requirements.txt
└── README.md
```

---

## Login

The login screen accepts **any non-empty username and password** — this is a class capstone exercise, not a production app. The username is captured for the session header but isn't validated.

To customize:
- Edit `app.py` → `_login_form()` to add real auth (hardcoded passwords, OAuth, etc.)
- Or remove the login gate entirely by deleting the `_login_form()` block and the `if not st.session_state.get("authed", False)` guard.

---

## Vote storage and persistence

Votes are written to `votes.json` in this directory on each submission:

```json
[
  {
    "timestamp": "2026-05-09T14:30:00Z",
    "name": "AB",
    "team": "Team 4",
    "vote": "APPROVE",
    "revisit_price": null,
    "comment": "Strong centralized-reading thesis."
  },
  ...
]
```

**Persistence caveats:**
- Streamlit Cloud: persists for the life of the app instance. If the app restarts (rare), votes are lost.
- Vercel container / Fly.io / Render: persists per container; ephemeral on redeploy.
- For permanent record: download the CSV from the Vote Results tab → 🛠 Admin expander → "Download votes CSV"

For production-grade voting that survives redeploys, swap `vote_tab.py`'s file-based storage for a small database (Supabase, Neon, Vercel KV, etc.). Out of scope for this exercise.

---

## Sharing with the IC

After deployment, send the team:

```
Subject: CardioPath IC — vote site

The IC dashboard, Monte Carlo, and live voting are all at:
  https://cardiopath-ic.streamlit.app   (or your deployed URL)

Sign in with any username and password.

Tabs:
- 📊 IC Dashboard — full pitch analysis
- 🎲 Monte Carlo — probability simulation
- 🗳️ Cast Vote — your APPROVE / REJECT / REVISIT
- 📈 Vote Results — live tally and decision

Please cast your vote after the in-class pitch. Tally is live; final results
will be exported and circulated post-session.
```
