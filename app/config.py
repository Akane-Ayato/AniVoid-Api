"""All configuration comes from environment variables (see .env.example)."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    return default if v is None else v.strip().lower() in {"1", "true", "yes", "on"}


def _list(name: str, default: str) -> list[str]:
    return [x.strip().rstrip("/") for x in os.getenv(name, default).split(",") if x.strip()]


class Settings:
    # server
    port = int(os.getenv("PORT", "8000"))
    cors_origins = _list("CORS_ORIGINS", "*")
    admin_token = os.getenv("ADMIN_TOKEN", "").strip()

    # official upstream API
    upstream_base = os.getenv("UPSTREAM_BASE", "https://anikotoapi.site").rstrip("/")
    rate_limit_requests = int(os.getenv("RATE_LIMIT_REQUESTS", "55"))
    rate_limit_window = float(os.getenv("RATE_LIMIT_WINDOW", "120"))
    crawl_per_page = min(int(os.getenv("CRAWL_PER_PAGE", "100")), 100)

    # weekly job
    enable_scheduler = _bool("ENABLE_SCHEDULER", True)
    refresh_tz = os.getenv("REFRESH_TZ", "UTC")
    refresh_day = os.getenv("REFRESH_DAY", "sun")
    refresh_hour = int(os.getenv("REFRESH_HOUR", "0"))
    refresh_minute = int(os.getenv("REFRESH_MINUTE", "0"))
    crawl_on_startup = _bool("CRAWL_ON_STARTUP", True)
    stale_after_days = float(os.getenv("STALE_AFTER_DAYS", "0"))

    # storage
    data_dir = Path(os.getenv("DATA_DIR", "./data")).resolve()
    json_pretty = _bool("JSON_PRETTY", False)

    # site scraping
    site_mirrors = _list(
        "SITE_MIRRORS",
        "https://anikototv.to,https://anikoto.cz,https://anikoto.me,https://anikoto.net,https://anikototv.se",
    )
    scraper_api_key = os.getenv("SCRAPER_API_KEY", "").strip()
    flaresolverr_url = os.getenv("FLARESOLVERR_URL", "").strip().rstrip("/")

    # cache
    ttl_search = int(os.getenv("TTL_SEARCH", "300"))
    ttl_schedule = int(os.getenv("TTL_SCHEDULE", "600"))
    ttl_topten = int(os.getenv("TTL_TOPTEN", "600"))


settings = Settings()
