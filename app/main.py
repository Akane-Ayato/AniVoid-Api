import asyncio
import logging
import math
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Header, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import accounts, cache, catalog, crawler, extractors, scheduler, scraper, social, store, upstream, db as database
from .config import settings
from .errors import ApiError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.scheduler = scheduler.start() if settings.enable_scheduler else None
    if crawler.needs_crawl():
        if settings.crawl_on_startup:
            log.info("completed.json / upcoming.json missing -> starting crawl in background")
            crawler.start_background("startup")
    else:
        log.info("existing data files found -> no startup crawl; next rebuild at the scheduled time")
        catalog.seed_if_missing()
    yield
    if app.state.scheduler:
        app.state.scheduler.shutdown(wait=False)
    await asyncio.gather(upstream.close(), scraper.close())


app = FastAPI(title="AniVoid API", version="1.0.0", lifespan=lifespan,
              description="Own API layer on top of the official AniKoto public API.")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
                   allow_headers=["*"], allow_credentials=settings.cors_origins != ["*"])
app.include_router(accounts.router)
app.include_router(social.router)


def fail(status: int, message: str) -> JSONResponse:
    return JSONResponse({"success": False, "message": message}, status_code=status)


@app.exception_handler(ApiError)
async def _api_error(_: Request, e: ApiError):
    return JSONResponse({"success": False, "message": e.message, **e.extra}, status_code=e.status)


@app.exception_handler(RequestValidationError)
async def _validation_error(_: Request, e: RequestValidationError):
    first = e.errors()[0] if e.errors() else {}
    where = ".".join(str(x) for x in first.get("loc", []) if x != "body")
    return JSONResponse({"success": False, "message": f"Invalid input{': ' + where if where else ''}",
                         "detail": jsonable_errors(e.errors())}, status_code=422)


def jsonable_errors(errors):
    return [{"loc": list(x.get("loc", [])), "msg": x.get("msg", ""), "type": x.get("type", "")} for x in errors]


@app.middleware("http")
async def csrf_guard(request: Request, call_next):
    """State-changing calls must carry a custom header (a cross-site form/img can't add it)."""
    if request.method in ("POST", "PUT", "PATCH", "DELETE") and request.url.path.startswith("/api/") \
            and request.url.path != "/api/admin/refresh" and request.headers.get("x-avtv") != "1":
        return fail(403, "Missing X-AVTV header.")
    return await call_next(request)


@app.exception_handler(scraper.ScrapeError)
async def _scrape_error(_: Request, e: scraper.ScrapeError):
    return fail(502, f"Source site unavailable: {e}")


@app.exception_handler(Exception)
async def _unhandled(_: Request, e: Exception):
    log.exception("unhandled error")
    return fail(500, "Internal server error")


# ------------------------------------------------------------------ meta
@app.get("/")
async def root():
    return {
        "name": "AniVoid API",
        "endpoints": {
            "search": "/api/search?keyword=solo+leveling&page=1",
            "schedule": "/api/schedule?date=YYYY-MM-DD",
            "random": "/api/random",
            "top-ten": "/api/top-ten",
            "completed": "/api/completed?page=1&per_page=20",
            "upcoming": "/api/upcoming?page=1&per_page=20",
            "accounts": "/api/config, /api/auth/*, /api/me, /api/comments, /api/list, /api/continue, /api/users/{name}",
            "status": "/api/status",
            "heartbeat": "/heartbeat",
            "docs": "/docs",
        },
    }


@app.api_route("/heartbeat", methods=["GET", "HEAD"])
@app.api_route("/health", methods=["GET", "HEAD"])
async def heartbeat():
    """Keep-alive / uptime route. Cheap, no upstream calls. HEAD is supported because UptimeRobot's
    free plan pings with HEAD by default."""
    return {"ok": True, "status": "alive", "time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}


@app.get("/api/status")
async def status():
    job = app.state.scheduler.get_job("weekly-crawl") if app.state.scheduler else None
    files = {}
    for name in (crawler.COMPLETED, crawler.UPCOMING, catalog.FILE):
        p = store.path_of(name)
        files[name] = {"exists": p.exists(), "bytes": p.stat().st_size if p.exists() else 0}
    return {
        "success": True,
        "results": {
            "crawl": crawler.state,
            "next_scheduled_crawl": job.next_run_time.isoformat() if job and job.next_run_time else None,
            "timezone": settings.refresh_tz,
            "catalog_entries": catalog.size(),
            "files": files,
        },
    }


@app.post("/api/admin/refresh")
async def admin_refresh(x_admin_token: str = Header(default="")):
    if not settings.admin_token:
        return fail(404, "Not found")
    if x_admin_token != settings.admin_token:
        return fail(401, "Invalid admin token")
    if crawler._lock.locked():
        return JSONResponse({"success": True, "message": "A crawl is already running"}, status_code=202)
    crawler.start_background("admin")
    return JSONResponse({"success": True, "message": "Crawl started"}, status_code=202)


# ------------------------------------------------------------------ completed / upcoming (from JSON files)
def _paged(filename: str, page: int, per_page: int):
    data = store.read_json(filename)
    if data is None:
        msg = "Data is still being built (first crawl takes a few minutes), try again shortly."
        return fail(503, msg)
    items = data["data"]
    total_pages = max(1, math.ceil(len(items) / per_page))
    chunk = items[(page - 1) * per_page: page * per_page]
    return {
        "success": True,
        "results": {
            "updated_at": data.get("updated_at"),
            "data": chunk,
            "pagination": {"currentPage": page, "totalPages": total_pages, "totalItems": len(items),
                           "itemsPerPage": per_page, "hasNext": page < total_pages, "hasPrev": page > 1},
        },
    }


@app.get("/api/completed")
async def completed(page: int = Query(1, ge=1), per_page: int = Query(20, ge=1, le=100)):
    return _paged(crawler.COMPLETED, page, per_page)


@app.get("/api/upcoming")
async def upcoming(page: int = Query(1, ge=1), per_page: int = Query(20, ge=1, le=100)):
    return _paged(crawler.UPCOMING, page, per_page)


# ------------------------------------------------------------------ scraped endpoints
@app.get("/api/search")
async def search(response: Response, keyword: str = Query("", max_length=200), page: int = Query(1, ge=1)):
    keyword = keyword.strip()
    if not keyword:
        return fail(400, "Keyword is required")
    key = f"search:{keyword.lower()}:{page}"
    if (hit := cache.get(key)) is not None:
        return {"success": True, "results": hit}
    try:
        result = await extractors.search(keyword, page)
    except scraper.ScrapeError:
        if not catalog.size():
            raise
        response.headers["X-Data-Source"] = "local-catalog"  # site blocked -> official-API catalog
        return {"success": True, "results": extractors.search_local(keyword, page)}
    cache.set(key, result, settings.ttl_search)
    return {"success": True, "results": result}


@app.get("/api/schedule")
async def schedule(date: str = Query("")):
    if not date:
        return fail(400, "Date is required (YYYY-MM-DD)")
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        return fail(400, "Date must be in YYYY-MM-DD format")
    key = f"schedule:{date}"
    if (hit := cache.get(key)) is not None:
        return {"success": True, "results": hit}
    result = await extractors.schedule(date)
    cache.set(key, result, settings.ttl_schedule)
    return {"success": True, "results": result}


@app.get("/api/random")
async def random_anime(response: Response):
    try:
        result = await extractors.random_anime()
        if result["id"] is None or not result["title"]:
            raise scraper.ScrapeError("random page could not be parsed")
    except scraper.ScrapeError:
        result = extractors.random_local()
        if result is None:
            raise
        response.headers["X-Data-Source"] = "local-catalog"
    return {"success": True, "results": result}


@app.get("/api/top-ten")
async def top_ten():
    if (hit := cache.get("top-ten")) is not None:
        return {"success": True, "results": hit}
    result = await extractors.top_ten()
    cache.set("top-ten", result, settings.ttl_topten)
    return {"success": True, "results": result}
