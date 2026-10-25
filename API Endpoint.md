# AniVoid API: Endpoints & Frontend Integration Guide

Base URL (replace with yours):

```
Local:   http://localhost:8000
Render:  https://<your-service>.onrender.com
```

Interactive docs (Swagger UI) are always available at `/docs`.

> The JSON samples below are **illustrative**: ids, titles and posters are placeholders, only the shapes are exact.

---

## 1. Conventions

| Topic | Behaviour |
|---|---|
| Success | `{ "success": true, "results": ... }` |
| Error | `{ "success": false, "message": "..." }` |
| `id` | Always the **official AniKoto id** (the same `id` the official `anikotoapi.site/series/{id}` endpoint expects) |
| Credits | No creator/credit fields in any response |
| CORS | Controlled by the `CORS_ORIGINS` env var (`*` by default). Set it to your frontend domain in production |
| Caching | Search 5 min, schedule 10 min, top-ten 10 min (server side, configurable). `completed`/`upcoming` come from JSON files rebuilt weekly |

### Status codes

| Code | Meaning |
|---|---|
| 200 | OK |
| 400 | Missing/invalid `keyword` or `date` |
| 401 | Wrong `X-Admin-Token` (admin route only) |
| 422 | Invalid `page` / `per_page` (e.g. `per_page=500`, `page=0`). FastAPI returns `{ "detail": [...] }` here |
| 502 | The source site could not be reached/scraped (and no local fallback available) |
| 503 | `completed.json` / `upcoming.json` not built yet (first crawl still running) |

### Optional response header

`X-Data-Source: local-catalog`: sent by `/api/search` and `/api/random` when the source site was unreachable and the answer came from the local catalog instead. The shape is identical, so the frontend needs no special handling.

---

## 2. Endpoints

### 2.1 `GET /api/search`

Search anime by keyword.

| Param | Type | Required | Notes |
|---|---|---|---|
| `keyword` | string | yes | max 200 chars |
| `page` | int | no | default `1`, 30 results per page |

```
GET /api/search?keyword=solo+leveling&page=1
```

```json
{
  "success": true,
  "results": {
    "totalPages": 1,
    "data": [
      { "id": 6224, "poster": "https://cdn.anipixcdn.co/thumbnail/53adb...png", "title": "Solo Leveling" },
      { "id": 7457, "poster": "https://cdn.anipixcdn.co/thumbnail/4b5ed...jpg", "title": "Solo Leveling Season 2: Arise from the Shadow" }
    ],
    "pagination": {
      "currentPage": 1, "totalPages": 1, "totalItems": 2,
      "itemsPerPage": 30, "hasNext": false, "hasPrev": false
    }
  }
}
```

Errors: `400 {"success":false,"message":"Keyword is required"}`

---

### 2.2 `GET /api/schedule`

Anime airing on a given date.

| Param | Type | Required | Notes |
|---|---|---|---|
| `date` | string | yes | `YYYY-MM-DD` |

```
GET /api/schedule?date=2026-10-24
```

```json
{
  "success": true,
  "results": [
    {
      "slug": "a-wild-last-boss-appeared-season-2",
      "id": 9029,
      "title": "A Wild Last Boss Appeared! Season 2",
      "japaneseTitle": "Yasei no Last Boss ga Arawareta! 2nd Season",
      "poster": "https://cdn.anipixcdn.co/thumbnail/d2c40...jpg",
      "time": "10:00",
      "episode_no": 6
    }
  ]
}
```

Notes for the frontend:
- `id` and `poster` are matched by title. If a show can't be matched, `id` is `null` and `poster` is `""`. Render a placeholder image and don't make that card clickable.
- `time` is passed through as the source site provides it (a plain string). Display it as-is.
- `slug` here is generated from the title, so **don't use it for routing**; use `id`.
- An empty day returns `"results": []`.

Errors: `400` for a missing or malformed date.

---

### 2.3 `GET /api/random`

One random anime. No params. Don't cache this on the frontend.

```json
{
  "success": true,
  "results": {
    "id": 2008,
    "title": "Air: The Movie",
    "poster": "https://cdn.anipixcdn.co/thumbnail/57baf...jpg",
    "type": "Movie"
  }
}
```

---

### 2.4 `GET /api/top-ten`

Top 10 lists for today, this week and this month. No params.

```json
{
  "success": true,
  "results": {
    "today": [
      { "id": 9101, "title": "Wistoria: Wand and Sword Season 2", "rank": 1, "poster": "https://cdn.anipixcdn.co/thumbnail/4739d...jpg" }
    ],
    "week":  [ { "id": 1,    "title": "One Piece", "rank": 1, "poster": "https://..." } ],
    "month": [ { "id": 1,    "title": "One Piece", "rank": 1, "poster": "https://..." } ]
  }
}
```

Notes:
- Each list is ordered by `rank` (1 to 10).
- A list can be empty, and `id` can be `null` for a brand-new title not yet in the catalog (rare; it fixes itself after the next catalog top-up). Guard for it.

---

### 2.5 `GET /api/completed`  and  `GET /api/upcoming`

Paginated lists served from `completed.json` (status *Finished Airing*) and `upcoming.json` (status *Not yet aired*). Rebuilt every Sunday.

| Param | Type | Default | Notes |
|---|---|---|---|
| `page` | int | `1` | `>= 1` |
| `per_page` | int | `20` | `1`–`100` |

```
GET /api/completed?page=1&per_page=24
GET /api/upcoming?page=2&per_page=24
```

```json
{
  "success": true,
  "results": {
    "updated_at": "2026-10-25T00:03:41Z",
    "data": [
      {
        "id": 1234,
        "title": "Example Anime",
        "alternative": "Example Alt Title",
        "titles": "",
        "native": "例",
        "slug": "example-anime-abc12",
        "rating": "PG-13",
        "poster": "https://cdn.anipixcdn.co/thumbnail/...jpg",
        "is_sub": 12,
        "description": "…",
        "aired": "Jan 5, 2024 to Mar 22, 2024",
        "season": "winter",
        "year": 2024,
        "duration": "24 min",
        "status": "Finished Airing",
        "score": "7.56",
        "mal_id": "12345",
        "episodes": "12",
        "ani_id": "67890",
        "source": "manga",
        "s_id": 111111,
        "background_image": "https://...",
        "updated_at": "2026-10-24 13:45:49",
        "next_air_schedule_time": null,
        "next_air_ep": null,
        "terms_by_type": {
          "genre": ["Action", "Fantasy"],
          "producers": ["..."],
          "studios": ["..."],
          "type": ["TV"]
        }
      }
    ],
    "pagination": {
      "currentPage": 1, "totalPages": 120, "totalItems": 2400,
      "itemsPerPage": 20, "hasNext": true, "hasPrev": false
    }
  }
}
```

Each item is the full row from the official `recent-anime` API (same field names), so anything you used from the official list works here too. `503` is returned until the first crawl has produced the files.

---

### 2.6 Utility endpoints

| Endpoint | Purpose |
|---|---|
| `GET` / `HEAD /heartbeat` (alias `/health`) | Keep-alive for UptimeRobot, returns `{"ok":true,"status":"alive","time":"..."}` |
| `GET /api/status` | Last crawl info, next scheduled crawl, catalog size, file sizes |
| `POST /api/admin/refresh` | Start a crawl now. Header `X-Admin-Token: <ADMIN_TOKEN>`. Returns `202` |
| `GET /` | Lists the endpoints |

Don't call `/api/admin/refresh` from the browser; it needs the secret token.

---

## 3. Episodes & streams (official API, not ours)

Our API gives you lists and ids. For **episodes and embed links** use the official endpoint with the same `id`:

```
GET https://anikotoapi.site/series/{id}
-> { anime: {...}, episodes: [ { ..., embed_url: { sub, dub } } ] }
```

Limit: 60 requests per IP per 120 s. If you call it from the browser, that limit applies to **each visitor's IP** (fine). If you call it from your own server, cache results.

---

## 4. Frontend integration examples

### 4.1 Tiny API client (works in any JS/TS frontend)

```js
// api.js
const BASE = import.meta.env?.VITE_API_BASE ?? process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

async function request(path, params = {}, { signal } = {}) {
  const qs = new URLSearchParams(
    Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== "")
  ).toString();
  const res = await fetch(`${BASE}${path}${qs ? `?${qs}` : ""}`, { signal });
  const body = await res.json().catch(() => ({}));
  if (!res.ok || body.success === false) {
    const err = new Error(body.message || `Request failed (${res.status})`);
    err.status = res.status;
    throw err;
  }
  return body.results;
}

export const api = {
  search:    (keyword, page = 1, opts) => request("/api/search", { keyword, page }, opts),
  schedule:  (date, opts)              => request("/api/schedule", { date }, opts),
  random:    (opts)                    => request("/api/random", {}, opts),
  topTen:    (opts)                    => request("/api/top-ten", {}, opts),
  completed: (page = 1, per_page = 24) => request("/api/completed", { page, per_page }),
  upcoming:  (page = 1, per_page = 24) => request("/api/upcoming", { page, per_page }),
};
```

`.env` for the frontend:

```
VITE_API_BASE=https://<your-service>.onrender.com        # Vite
NEXT_PUBLIC_API_BASE=https://<your-service>.onrender.com # Next.js
```

### 4.2 Search box with debounce (React)

```jsx
import { useEffect, useState } from "react";
import { api } from "./api";

export function SearchBox() {
  const [q, setQ] = useState("");
  const [items, setItems] = useState([]);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (q.trim().length < 2) return setItems([]);
    const ctrl = new AbortController();
    const t = setTimeout(async () => {
      try {
        const res = await api.search(q.trim(), 1, { signal: ctrl.signal });
        setItems(res.data);
        setError(null);
      } catch (e) {
        if (e.name !== "AbortError") setError(e.message);
      }
    }, 400);                       // debounce
    return () => { clearTimeout(t); ctrl.abort(); };
  }, [q]);

  return (
    <div>
      <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search anime…" />
      {error && <p>{error}</p>}
      <ul>
        {items.map((a) => (
          <li key={a.id}>
            <a href={`/anime/${a.id}`}><img src={a.poster} alt="" width="48" /> {a.title}</a>
          </li>
        ))}
      </ul>
    </div>
  );
}
```

### 4.3 Top-ten tabs (Today / Week / Month)

```jsx
import { useEffect, useState } from "react";
import { api } from "./api";

export function TopTen() {
  const [data, setData] = useState(null);
  const [tab, setTab] = useState("today");

  useEffect(() => { api.topTen().then(setData).catch(console.error); }, []);
  if (!data) return <p>Loading…</p>;

  return (
    <section>
      {["today", "week", "month"].map((t) => (
        <button key={t} onClick={() => setTab(t)} disabled={tab === t}>{t}</button>
      ))}
      <ol>
        {data[tab].map((a) => (
          <li key={a.rank}>
            <span>#{a.rank}</span>
            {a.id ? <a href={`/anime/${a.id}`}>{a.title}</a> : <span>{a.title}</span>} {/* id can be null */}
            <img src={a.poster} alt="" width="40" />
          </li>
        ))}
      </ol>
    </section>
  );
}
```

### 4.4 Schedule day picker

```jsx
import { useEffect, useState } from "react";
import { api } from "./api";

const fmt = (d) => d.toISOString().slice(0, 10);              // YYYY-MM-DD
const FALLBACK = "/placeholder-poster.png";

export function Schedule() {
  const [date, setDate] = useState(fmt(new Date()));
  const [items, setItems] = useState([]);

  useEffect(() => { api.schedule(date).then(setItems).catch(() => setItems([])); }, [date]);

  return (
    <section>
      <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
      {items.length === 0 && <p>Nothing scheduled.</p>}
      {items.map((a) => {
        const card = (
          <>
            <img src={a.poster || FALLBACK} alt="" width="64" />
            <b>{a.title}</b> • EP {a.episode_no} • {a.time}
          </>
        );
        return a.id
          ? <a key={a.slug + a.time} href={`/anime/${a.id}`}>{card}</a>
          : <div key={a.slug + a.time}>{card}</div>;      // unmatched show: not clickable
      })}
    </section>
  );
}
```

`toISOString()` uses UTC; if you want the visitor's local date, build the string from `getFullYear()/getMonth()/getDate()` instead.

### 4.5 "Random anime" button

```jsx
import { api } from "./api";

export function RandomButton() {
  const go = async () => {
    const a = await api.random();
    window.location.href = `/anime/${a.id}`;
  };
  return <button onClick={go}>🎲 Random anime</button>;
}
```

### 4.6 Completed / Upcoming grid with "Load more"

```jsx
import { useEffect, useState } from "react";
import { api } from "./api";

export function AnimeGrid({ kind = "completed" }) {      // "completed" | "upcoming"
  const [items, setItems] = useState([]);
  const [page, setPage] = useState(1);
  const [hasNext, setHasNext] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    api[kind](page, 24)
      .then((r) => { setItems((prev) => (page === 1 ? r.data : [...prev, ...r.data])); setHasNext(r.pagination.hasNext); })
      .catch((e) => setError(e.status === 503 ? "Data is being prepared, try again in a few minutes." : e.message));
  }, [kind, page]);

  return (
    <>
      {error && <p>{error}</p>}
      <div className="grid">
        {items.map((a) => (
          <a key={a.id} href={`/anime/${a.id}`}>
            <img src={a.poster} alt="" /><span>{a.title}</span>
            <small>{a.terms_by_type?.genre?.join(", ")} • ⭐ {a.score}</small>
          </a>
        ))}
      </div>
      {hasNext && <button onClick={() => setPage((p) => p + 1)}>Load more</button>}
    </>
  );
}
```

### 4.7 Anime detail page: our `id` → official `/series/{id}`

```js
// /anime/[id]: fetch details + episodes from the official API using the id we returned
export async function getSeries(id) {
  const res = await fetch(`https://anikotoapi.site/series/${id}`);
  if (!res.ok) throw new Error("Series not found");
  const { anime, episodes } = await res.json();
  return { anime, episodes };   // episode.embed_url.sub / .dub when available
}
```

### 4.8 Next.js (server-side fetching with revalidation)

```js
// app/page.js (App Router)
const BASE = process.env.NEXT_PUBLIC_API_BASE;

export default async function Home() {
  const res = await fetch(`${BASE}/api/top-ten`, { next: { revalidate: 600 } }); // 10 min
  const { results } = await res.json();
  return <pre>{JSON.stringify(results.today.slice(0, 3), null, 2)}</pre>;
}
```

### 4.9 Plain `fetch` / `curl` quick tests

```bash
curl "https://<your-service>.onrender.com/api/search?keyword=naruto"
curl "https://<your-service>.onrender.com/api/schedule?date=2026-10-24"
curl "https://<your-service>.onrender.com/api/completed?page=1&per_page=5"
curl -I "https://<your-service>.onrender.com/heartbeat"
```

---

## 5. Integration checklist

- [ ] Set `CORS_ORIGINS` on the server to your frontend domain(s).
- [ ] Route detail pages by **`id`** (`/anime/:id`), never by slug.
- [ ] Guard `id: null` (top-ten, schedule) and empty `poster` (schedule): show a placeholder, no link.
- [ ] Handle `503` on completed/upcoming (first crawl still running) and `502` on scraped endpoints (source site down).
- [ ] Debounce search input (300–500 ms) and cancel stale requests.
- [ ] Free Render instances sleep when idle: the first request after a sleep can take ~30–60 s. Keep it awake with an UptimeRobot monitor on `/heartbeat`, and show a loading state in the UI.
- [ ] Episodes and embed links come from the official `GET https://anikotoapi.site/series/{id}` (60 requests / IP / 120 s).

---

## 6. Accounts & community endpoints (new)

All of these need the header **`X-AVTV: 1`** on `POST/PUT/PATCH/DELETE`, and use the `avtv_session` cookie (HttpOnly) for the signed-in user. From the browser call them through the Vercel proxy: `fetch("/api/v1/me", { credentials: "same-origin" })` (see the frontend's `assets/site.js` → `AVTV.api()`).
Errors keep the `{ "success": false, "message": "..." }` shape. Validation errors are now `422 { "success": false, "message": "Invalid input: ...", "detail": [...] }`. `401` includes `"auth_required": true`; failed captchas include `"captcha_failed": true`.

| Endpoint | Auth | Purpose |
|---|---|---|
| `GET /api/config` | – | `{accounts: bool, google_client_id}` |
| `GET /api/auth/captcha` | – | `{token, image}`: `image` is an SVG data-URI; the token is single-use, valid 5 min |
| `POST /api/auth/register` | – | `{username, password, confirm?, captcha_token, captcha_answer}` → sets cookie, returns your profile |
| `POST /api/auth/login` | – | `{username (or email), password, captcha_token, captcha_answer}` |
| `POST /api/auth/google` | – | `{credential}` → `{status:"ok", user}` or `{status:"need_username", ticket, email}` |
| `POST /api/auth/google/complete` | – | `{ticket, username}` creates the profile |
| `POST /api/auth/logout` | – | clears the cookie |
| `GET /api/me` | ✔ | your full profile (below) |
| `PATCH /api/me` | ✔ | any of `bio` (plain text, no links), `avatar {bg 0-11, icon, frame}`, `favorites [{id,title,poster}] (max 10)`, `privacy {show_list}` |
| `POST /api/me/password` | ✔ | `{current, new}` (current not needed for Google-only accounts); signs out other devices |
| `POST /api/me/username` | ✔ | `{username, password}` once per 30 days |
| `POST /api/me/checkin` | ✔ | daily VP + streak |
| `GET /api/me/vp` | ✔ | last 50 VP transactions |
| `GET /api/users/{username}` | – | public profile (no email/id; `stats.list_counts` is `null` if the list is private) |
| `GET /api/users/{username}/list?status=` | – | public list (403 when private) |
| `GET /api/comments?anime_id=&page=&per_page=&sort=new\|top` | optional | top-level comments (`my_vote`/`mine` filled when signed in) |
| `GET /api/comments/{id}/replies` | optional | replies, oldest first |
| `POST /api/comments` | ✔ | `{anime_id, text (1-1000), parent_id?}`; replies are one level deep |
| `POST /api/comments/{id}/vote` | ✔ | `{value: 1\|-1\|0}` |
| `DELETE /api/comments/{id}` | ✔ | own comments only |
| `GET /api/list?status=all\|watching\|completed\|on_hold\|dropped\|plan_to_watch` | ✔ | your list + counts |
| `GET/PUT/DELETE /api/list/{anime_id}` | ✔ | read / set `{status, title, poster}` / remove |
| `GET /api/continue` · `PUT /api/continue/{anime_id}` · `DELETE /api/continue/{anime_id}` · `DELETE /api/continue` | ✔ | continue-watching: `PUT {title, poster, episode, audio}` |
| `POST /api/continue/merge` | ✔ | `{items:[{anime_id,title,poster,episode,audio,updated_at(ms)}]}` merges guest history, returns the merged list |
| `POST /api/watch/complete` | ✔ | `{anime_id, episode}`: counts once per episode (stats + VP) |

`GET /api/me` / public profile shape (abridged):

```json
{
  "success": true,
  "results": {
    "id": "…", "username": "alice", "bio": "", "joined": "2026-10-25T06:00:00+00:00",
    "avatar": { "bg": 3, "icon": "initial", "frame": "glow" },
    "vp": 62, "streak": 1,
    "rank": { "index": 0, "title": "Newcomer", "next_title": "Void Initiate", "next_at": 500, "progress": 12.4, "ladder": [ { "title": "Newcomer", "at": 0 } ] },
    "stats": { "episodes": 1, "hours": 0.4, "minutes": 24, "comments": 2, "list_total": 3, "completed": 1,
               "list_counts": { "watching": 1, "completed": 1, "on_hold": 0, "dropped": 0, "plan_to_watch": 1 },
               "best_streak": 1, "days_on_site": 0 },
    "badges": [ { "id": "first_steps", "icon": "👣", "name": "First Steps", "desc": "Create your account", "earned": true } ],
    "favorites": [ { "id": 1234, "title": "Example", "poster": "https://…" } ],
    "privacy": { "show_list": true },
    "has_password": true, "google_linked": false, "email": null, "checked_in_today": true,
    "frames": [ { "key": "sakura", "unlocked": false, "unlock_rank": "Void Initiate" } ]
  }
}
```
(`id`, `email`, `has_password`, `google_linked`, `checked_in_today`, `frames` only appear on `/api/me`.)
