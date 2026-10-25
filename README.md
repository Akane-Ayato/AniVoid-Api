# AniVoid API

Our own API layer on top of the **official AniKoto public API** (`anikotoapi.site`).
The official API stays the single source of truth ("engine"); this project adds the endpoints it lacks.

| Endpoint | Source | Notes |
|---|---|---|
| `GET /api/search?keyword=&page=` | anikototv.to scrape | returns `id`, `poster`, `title` |
| `GET /api/schedule?date=YYYY-MM-DD` | anikototv.to scrape | `slug`, `id`, `title`, `japaneseTitle`, `poster`, `time`, `episode_no` (id/poster matched by title, `null`/`""` if unknown) |
| `GET /api/random` | anikototv.to scrape | returns `id`, `title`, `poster`, `type` |
| `GET /api/top-ten` | anikototv.to scrape | `today` / `week` / `month` → `id`, `title`, `rank`, `poster` |
| `GET /api/completed?page=&per_page=` | `data/completed.json` | built from official API, `status = "Finished Airing"` |
| `GET /api/upcoming?page=&per_page=` | `data/upcoming.json` | built from official API, `status = "Not yet aired"` |
| `GET /api/status` | – | last crawl, next scheduled crawl, file sizes |
| `POST /api/admin/refresh` | – | header `X-Admin-Token`, starts a crawl now |
| `GET/HEAD /heartbeat` (alias `/health`), `GET /docs` | – | keep-alive route for UptimeRobot, Swagger UI |

All responses are `{ "success": true, "results": ... }` (errors: `{ "success": false, "message": ... }`).
No creator/credit fields are added anywhere.

## How it works

```
anikotoapi.site/recent-anime ──(weekly crawl, ≤55 req/120s)──► completed.json
                                                              upcoming.json
                                                              catalog.json  (slug → official id)
anikototv.to (search/schedule/random/top-ten HTML) ──► extractors ──► id resolved via catalog.json
```

**Weekly crawl** (`app/crawler.py`): walks `/recent-anime?per_page=100` page by page through one shared sliding-window
rate limiter (default 55 requests / 120 s, safely under the official 60), splits rows by `status`, then builds the
*new* files fully in memory and swaps them in atomically. The API keeps serving the old files meanwhile, and keeps them
if a crawl fails or comes back incomplete (< 90 % of the reported total). Rows are de-duplicated by `id`
(pages can shift while the crawl runs). A full run is ~90 requests → roughly 2–3 minutes.

* On boot: if `completed.json` **and** `upcoming.json` already exist in `DATA_DIR` (e.g. generated locally and uploaded), **no crawl runs**; 
  they are served as they are and the next rebuild happens at the scheduled time. Only if one of them is missing does a first crawl start.
  If `catalog.json` wasn't uploaded it is rebuilt from the two files (new/airing shows are learned on demand). Upload `catalog.json` too for the best id/poster matching.
  (Optional: `STALE_AFTER_DAYS=N` also re-crawls on boot when the last good crawl is older than N days; off by default.)
* Then: every **Sunday 00:00** in `REFRESH_TZ` (set it to your timezone, e.g. `Asia/Kolkata`); the new files land a few
  minutes later. A short app downtime at 00:00 is tolerated (1 h misfire grace).
* Manual: `python -m app.crawler` or `POST /api/admin/refresh`.

**Ids.** The site's pages carry slugs like `one-piece-odmau`, and the official API returns the same slug together with
the numeric `id`. `catalog.json` maps slug → official id, so every endpoint returns the **official** `id`
(search: `animeId` renamed to `id`; top-ten: `id` added, `name` renamed to `title`). If a slug is unknown (brand-new anime)
the newest 300 rows are pulled from the official API (max once per 10 min); search/random fall back to the id scraped
from the page. `catalog.json` also powers a fallback: if the site is blocked (Cloudflare), `/api/search` and `/api/random`
answer from the catalog and set the header `X-Data-Source: local-catalog`.

## Accounts & community (profiles, comments, lists, VP)

Needs a database: **MongoDB** (free Atlas M0 is enough). Without `MONGODB_URI` everything above keeps working and the account
endpoints answer `503 Accounts are not enabled`.

1. Atlas → create a free cluster → *Database Access* user → *Network Access* allow your host (`0.0.0.0/0` for Render) → copy the
   connection string into `MONGODB_URI`.
2. Set `SESSION_SECRET` (`python -c "import secrets;print(secrets.token_hex(32))"`). Changing it signs everybody out.
3. Frontend on Vercel? The browser only talks to the Vercel domain (`api/v1/[...path].js` forwards to this backend), so the session cookie stays
   first-party. Set the same random `PROXY_SECRET` here and on Vercel so the real visitor IP reaches the rate limiter.
4. Google sign-in (optional): Google Cloud Console → *APIs & Services → Credentials → OAuth client ID → Web application*, add your site
   origin under *Authorized JavaScript origins*, put the client id in `GOOGLE_CLIENT_ID`. The popup hides the Google button when it is empty.

What it provides: register/login (username + password + server-issued captcha), Google login, profile (bio, avatar, effects, favorites,
privacy), public profiles, comments with replies and votes, anime list (watching / completed / on-hold / dropped / plan-to-watch),
continue-watching sync, watch stats and **Void Points (VP)**: daily check-in streaks, 6 ranks, 11 computed badges and rank-locked avatar effects.

| VP source | Points | Daily cap |
|---|---|---|
| Welcome bonus | 50 | once |
| Daily check-in | 10 + 2 per streak day (max 7) | once |
| Episode watched | 5 | 100 |
| Comment | 3 | 15 |
| First time adding an anime to the list | 2 | 10 |

Ranks: Newcomer 0 · Void Initiate 500 · Shadow Watcher 2,000 · Rift Walker 5,000 · Void Sage 10,000 · Ascended 25,000
(`app/progress.py`, easy to retune).

**Security notes.** Passwords are hashed with scrypt; the session is an HttpOnly, SameSite=Lax signed cookie (password change signs out
other devices); every state-changing call needs the `X-AVTV: 1` header (CSRF guard); captchas are signed, expire after 5 min and are single-use;
login/register/comment/vote endpoints are rate limited per IP/user; links are rejected in bios and comments; the frontend renders all user
text with `textContent`/escaping. Password-only accounts have no recovery (there is no email): tell users to connect Google or keep their password safe.
The rate limiter and captcha cache are in-process, so keep a single worker.

Endpoint reference: `api_endpoints.md` (section 6).

## Run locally

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                   # edit REFRESH_TZ, ADMIN_TOKEN, ...
uvicorn app.main:app --reload --port 8000
```
Open http://localhost:8000/docs. Run the tests (offline): `pip install -r requirements-dev.txt && pytest`.

> Use **one worker** (`--workers 1`): the scheduler and rate limiter live inside the process.

## Docker / VPS

```bash
cp .env.example .env && docker compose up -d --build   # data persists in the api-data volume
```

Without Docker (Ubuntu): copy the project to `/opt/anivoid-api`, create a venv, `pip install -r requirements.txt`, fill `.env`,
then `sudo cp deploy/anivoid-api.service /etc/systemd/system/ && sudo systemctl enable --now anivoid-api`.
Put nginx in front with `deploy/nginx.conf` (+ `certbot --nginx` for HTTPS).

## Render + UptimeRobot

1. Generate the data locally once (`uvicorn app.main:app`, wait for the crawl, or `python -m app.crawler`) so `data/completed.json`,
   `data/upcoming.json` and `data/catalog.json` exist. They are **not** git-ignored: commit them with the repo (or upload them to a disk).
2. Push to GitHub → Render → New → *Blueprint* (uses `render.yaml`, free plan) or a normal Web Service with
   build `pip install -r requirements.txt`, start `uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1 --proxy-headers`.
   Set `REFRESH_TZ` (e.g. `Asia/Kolkata`) and `ADMIN_TOKEN`.
3. On boot it finds the files → no crawl. Every Sunday at the scheduled time it rebuilds them.
4. Keep it awake: UptimeRobot → *Add New Monitor* → type **HTTP(s)**, URL `https://<your-service>.onrender.com/heartbeat`,
   interval 5 minutes. (`/heartbeat` answers both GET and HEAD.) A sleeping free instance would miss the Sunday job.

Free-plan caveat: the filesystem is ephemeral. The Sunday rebuild is served until the instance restarts or redeploys, then it falls back
to the files in the repo, so commit fresh JSON every now and then (or use a paid plan with a persistent disk and set `DATA_DIR` to its mount path).

## Configuration

See `.env.example` — every setting is documented there. The important ones: `REFRESH_TZ`, `ADMIN_TOKEN`, `DATA_DIR`,
`CORS_ORIGINS`, and optionally `SCRAPER_API_KEY` / `FLARESOLVERR_URL` if anikototv.to blocks your server's IP.

## Project layout

```
app/main.py        FastAPI app + endpoints        app/crawler.py   weekly crawl → JSON files
app/extractors.py  search/schedule/random/top-ten  app/catalog.py   slug → id map, local fallbacks
app/scraper.py     mirror fallback + bypass        app/upstream.py  official API client + rate limiter
app/scheduler.py   Sunday job                      app/store.py     atomic JSON files
app/accounts.py    auth, captcha, profile          app/social.py    comments, list, continue, public profiles
app/progress.py    VP, ranks, badges               app/security.py  scrypt, signed tokens, captcha, rate limit
tests/             offline tests (network mocked)  deploy/          systemd + nginx
```

## Credits

Scraping selectors are ported from [Shineii86/AniKotoAPI](https://github.com/Shineii86/AniKotoAPI) (MIT).
