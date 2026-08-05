# Deploying Project Cinderella to Railway

Railway hosts the dashboard and scheduler with a managed Postgres database.
No Docker installation required on your machine — Railway builds everything in the cloud.

---

## Prerequisites

- A [GitHub](https://github.com) account
- A [Railway](https://railway.app) account (free tier works; $5/mo Hobby plan recommended for always-on)

---

## Step 1 — Push the code to GitHub

1. Go to [github.com/new](https://github.com/new) and create a **private** repository named `project-cinderella`.
2. Open **Terminal** (Applications → Utilities → Terminal) and run:

```bash
cd "/Users/carlykleinbart/Library/Application Support/Claude/local-agent-mode-sessions/95411993-c54b-43e4-9af6-d1524d63f8b4/749ff0da-b382-4219-a414-523355d959a1/local_f94af93a-d091-4778-a120-e48e98a56c09/outputs/project-cinderella"

git init
git add .
git commit -m "Initial commit — Project Cinderella"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/project-cinderella.git
git push -u origin main
```

Replace `YOUR_USERNAME` with your GitHub username.

---

## Step 2 — Create a Railway project

1. Go to [railway.app](https://railway.app) and sign in.
2. Click **New Project**.
3. Choose **Deploy from GitHub repo**.
4. Select your `project-cinderella` repo.
5. Railway will detect the Dockerfile and start building. Let it run.

---

## Step 3 — Add a Postgres database

1. Inside your Railway project, click **+ New** → **Database** → **Add PostgreSQL**.
2. Railway creates a Postgres instance and automatically sets `DATABASE_URL` in your project's shared variables. No configuration needed.

---

## Step 4 — Set environment variables

In Railway, click your **dashboard service** → **Variables** tab → **Raw Editor**, and paste:

```
AMAZON_HEADLESS=true
AMAZON_REQUEST_DELAY_MIN=2.0
AMAZON_REQUEST_DELAY_MAX=5.0
AMAZON_MAX_BOOKS_PER_CATEGORY=100
COLLECTION_SCHEDULE=0 6 * * *
LOG_LEVEL=INFO
REPORTS_DIR=/app/reports
GOODREADS_HEADLESS=true
TIKTOK_HEADLESS=true
TIKTOK_MAX_BOOKS=100
```

Optional — add these if you want alerts:
```
ALERT_EMAIL_TO=your@email.com
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your@gmail.com
SMTP_PASSWORD=your_app_password
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
```

Optional — add these if you want Reddit collection:
```
REDDIT_CLIENT_ID=your_client_id
REDDIT_CLIENT_SECRET=your_client_secret
REDDIT_USER_AGENT=cinderella-bot/1.0
```

---

## Step 5 — Configure the dashboard service start command

1. Click your service → **Settings** tab.
2. Under **Deploy** → **Start Command**, enter:
   ```
   python -m scripts.serve
   ```
3. Railway injects `PORT` automatically — no need to specify it.

---

## Step 6 — Run the database migration

1. In your Railway project, click your service → **Settings** → **Deploy** → scroll to **Deploy Triggers**.
2. Alternatively, use the Railway CLI (optional install):
   ```bash
   npm install -g @railway/cli
   railway login
   railway run alembic upgrade head
   ```

**Or without the CLI:** temporarily change the start command to:
```
alembic upgrade head && python -m scripts.serve
```
Deploy once, then change it back to `python -m scripts.serve`. The migration is idempotent — safe to run on every boot if you prefer.

---

## Step 7 — Add the scheduler service

The scheduler runs daily collection separately from the web server.

1. In your Railway project, click **+ New** → **GitHub Repo** → select `project-cinderella` again.
2. This creates a second service from the same repo.
3. Set its **Start Command** to:
   ```
   python -m scripts.scheduler
   ```
4. Copy the same environment variables from Step 4 into this service.
5. In **Settings**, set **Restart Policy** → **Always** (so it restarts if it crashes).

---

## Step 8 — Run the first collection

Once both services are deployed and the migration has run, trigger an initial collection:

**Via Railway CLI:**
```bash
railway run python -m scripts.collect --source amazon --max-books 20
```

**Or:** temporarily set the scheduler service start command to:
```
python -m scripts.collect --source amazon --max-books 20
```
Let it run once (check logs), then restore to `python -m scripts.scheduler`.

---

## Step 9 — Open your dashboard

1. Click your **dashboard service** in Railway.
2. Under **Settings** → **Networking**, click **Generate Domain**.
3. Railway gives you a public URL like `https://project-cinderella-production.up.railway.app`.
4. Open it — your live dashboard with real data.

---

## Ongoing schedule

Once running, the scheduler daemon automatically:

| Time (UTC) | Job |
|---|---|
| 06:00 | Amazon bestseller collection |
| 06:15 | Goodreads enrichment |
| 06:30 | BookTok mentions |
| 06:45 | Reddit mentions |
| 07:00 | Score all books + send alerts |

You can change the base time via the `COLLECTION_SCHEDULE` environment variable (standard cron format).

---

## Cost estimate

| Tier | Cost | Notes |
|---|---|---|
| Free | $0 | Services sleep after inactivity — dashboard may be slow to wake |
| Hobby | $5/mo | Always-on, custom domain, more resources — recommended |

The Postgres database on the Hobby plan is included in the $5.
