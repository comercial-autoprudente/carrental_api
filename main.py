from __future__ import annotations

def _no_store_json(payload: Dict[str, Any], status_code: int = 200) -> JSONResponse:
    try:
        return JSONResponse(
            payload,
            status_code=status_code,
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )
    except Exception:
        return JSONResponse(payload, status_code=status_code)
def render_with_playwright(url: str) -> str:
    if not _HAS_PLAYWRIGHT:
        return ""

def _is_carjet(u: str) -> bool:
    try:
        from urllib.parse import urlparse as _parse
        return _parse(u).netloc.endswith("carjet.com")
    except Exception:
        return False

def _ensure_settings_table():
    try:
        with _db_lock:
            con = _db_connect()
            try:
                con.execute(
                    "CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT)"
                )
                con.commit()
            finally:
                con.close()
    except Exception:
        pass

def _get_setting(key: str, default: str = "") -> str:
    try:
        _ensure_settings_table()
        with _db_lock:
            con = _db_connect()
            try:
                cur = con.execute("SELECT value FROM app_settings WHERE key=?", (key,))
                r = cur.fetchone()
                return (r[0] if r and r[0] is not None else default)
            finally:
                con.close()
    except Exception:
        return default

def _set_setting(key: str, value: str) -> None:
    try:
        _ensure_settings_table()
        with _db_lock:
            con = _db_connect()
            try:
                con.execute(
                    "INSERT INTO app_settings (key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (key, value),
                )
                con.commit()
            finally:
                con.close()
    except Exception:
        pass

def _get_carjet_adjustment() -> Tuple[float, float]:
    try:
        pct_s = _get_setting("carjet_pct", "")
        off_s = _get_setting("carjet_off", "")
        if pct_s or off_s:
            try:
                return float(pct_s or 0.0), float(off_s or 0.0)
            except Exception:
                pass
        # Fallback to env
        return float(os.getenv("CARJET_PRICE_ADJUSTMENT_PCT", "0") or 0.0), float(os.getenv("CARJET_PRICE_OFFSET_EUR", "0") or 0.0)
    except Exception:
        return 0.0, 0.0

def apply_price_adjustments(items: List[Dict[str, Any]], base_url: str) -> List[Dict[str, Any]]:
    try:
        if not items:
            return items
        if not _is_carjet(base_url):
            return items
        pct, off = _get_carjet_adjustment()
        if pct == 0 and off == 0:
            return items
        out: List[Dict[str, Any]] = []
        for it in items:
            ptxt = str(it.get("price") or "")
            amt = _parse_amount(ptxt)
            if amt is None:
                out.append(it)
                continue
            adj = amt * (1.0 + (pct/100.0)) + off
            it2 = dict(it)
            it2.setdefault("original_price", ptxt)
            it2["price"] = _format_eur(adj)
            it2["currency"] = "EUR"
            out.append(it2)
        return out
    except Exception:
        return items

def scrape_with_playwright(url: str) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    if not _HAS_PLAYWRIGHT:
        return items
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(locale="pt-PT", user_agent="Mozilla/5.0 (compatible; PriceTracker/1.0)")
            try:
                context.add_cookies([
                    {"name": "monedaForzada", "value": "EUR", "domain": ".carjet.com", "path": "/"},
                    {"name": "moneda", "value": "EUR", "domain": ".carjet.com", "path": "/"},
                    {"name": "currency", "value": "EUR", "domain": ".carjet.com", "path": "/"},
                    {"name": "country", "value": "PT", "domain": ".carjet.com", "path": "/"},
                    {"name": "idioma", "value": "PT", "domain": ".carjet.com", "path": "/"},
                    {"name": "lang", "value": "pt", "domain": ".carjet.com", "path": "/"},
                ])
            except Exception:
                pass
            page = context.new_page()
            try:
                page.set_extra_http_headers({"Accept-Language": "pt-PT,pt;q=0.9,en;q=0.8"})
            except Exception:
                pass
            page.goto(url, wait_until="networkidle", timeout=35000)
            try:
                page.wait_for_selector("section.newcarlist article, .newcarlist article, article.car, li.result, li.car, .car-item, .result-row", timeout=15000)
            except Exception:
                pass

            # Query all cards
            handles = page.query_selector_all("section.newcarlist article, .newcarlist article, article.car, li.result, li.car, .car-item, .result-row")
            idx = 0
            for h in handles:
                try:
                    card_text = (h.inner_text() or "").strip()
                except Exception:
                    card_text = ""
                # Extract total price near "Preço por <N> dias" if present
                price_text = ""
                try:
                    # Exact block text often includes this phrase; capture the nearest euro amount after it
                    m = re.search(r"preço\s*por\s*\d+\s*dias[^\n€]*([€\s]*[0-9][0-9\.,]+)\s*€?", card_text, re.I)
                    if m:
                        amt = m.group(1)
                        if "€" not in amt:
                            price_text = (amt.strip() + " €").strip()
                        else:
                            price_text = amt.strip()
                except Exception:
                    price_text = ""
                # Fallback: choose highest amount in the card (avoid per-day by favoring larger value)
                if not price_text:
                    try:
                        euros = re.findall(r"[€\s]*([0-9][0-9\.,\s]*)", card_text)
                        best = None
                        best_v = float("-inf")
                        for t in euros:
                            v = _parse_amount(t)
                            if v is None:
                                continue
                            if v > best_v:
                                best_v = v
                                best = t
                        if best is not None:
                            price_text = f"{best} €"
                    except Exception:
                        pass
                # car name
                car = ""
                try:
                    name_el = h.query_selector(".veh-name, .vehicle-name, .model, .titleCar, .title, h3, h2")
                    if name_el:
                        car = (name_el.inner_text() or "").strip()
                except Exception:
                    pass
                # supplier
                supplier = ""
                try:
                    # Try logo alt text
                    im = h.query_selector("img[alt*='logo'], img[alt*='Logo'], img[src*='logo_']")
                    if im:
                        supplier = (im.get_attribute("alt") or "").strip()
                    if not supplier:
                        sup_el = h.query_selector(".supplier, .vendor, .partner, [class*='supplier'], [class*='vendor']")
                        supplier = (sup_el.inner_text() or "").strip() if sup_el else ""
                except Exception:
                    pass
                # category (best effort)
                category = ""
                try:
                    cat_el = h.query_selector(".category, .group, .vehicle-category, [class*='category'], [class*='group']")
                    category = (cat_el.inner_text() or "").strip() if cat_el else ""
                except Exception:
                    pass
                # link
                link = ""
                try:
                    a = h.query_selector("a[href]")
                    if a:
                        href = a.get_attribute("href") or ""
                        if href and not href.lower().startswith("javascript"):
                            from urllib.parse import urljoin as _urljoin
                            link = _urljoin(url, href)
                except Exception:
                    pass
                # Only add if we have a price
                if price_text:
                    items.append({
                        "id": idx,
                        "car": car,
                        "supplier": supplier,
                        "price": price_text,
                        "currency": "",
                        "category": category,
                        "transmission": "",
                        "photo": "",
                        "link": link or url,
                    })
                    idx += 1
            context.close()
            browser.close()
    except Exception:
        return items
    return items

import os
import secrets
import re
from urllib.parse import urljoin
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timezone, timedelta
import traceback as _tb

from fastapi import FastAPI, Request, Form, Depends, HTTPException, UploadFile, File
from fastapi.responses import RedirectResponse, JSONResponse, HTMLResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from urllib.parse import urlencode, quote_plus
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from starlette.status import HTTP_303_SEE_OTHER
from dotenv import load_dotenv
import requests
import asyncio
from bs4 import BeautifulSoup
import sqlite3
from threading import Lock
import time
import io
import hashlib
import smtplib
from email.message import EmailMessage
from fastapi import Query
try:
    import httpx  # type: ignore
    _HTTPX_CLIENT = httpx.Client(timeout=httpx.Timeout(10.0, connect=4.0), headers={"Connection": "keep-alive"})
    _HTTPX_ASYNC: Optional["httpx.AsyncClient"] = httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=4.0), headers={"Connection": "keep-alive"})
except Exception:
    _HTTPX_CLIENT = None
    _HTTPX_ASYNC = None
try:
    from playwright.sync_api import sync_playwright  # type: ignore
    _HAS_PLAYWRIGHT = True
except Exception:
    _HAS_PLAYWRIGHT = False
# Rollback mode: always disable Playwright paths
_HAS_PLAYWRIGHT = False

load_dotenv()

APP_PASSWORD = os.getenv("APP_PASSWORD", "change_me")
SECRET_KEY = os.getenv("SECRET_KEY", secrets.token_urlsafe(32))
TARGET_URL = os.getenv("TARGET_URL", "https://example.com")
SCRAPER_SERVICE = os.getenv("SCRAPER_SERVICE", "")
SCRAPER_API_KEY = os.getenv("SCRAPER_API_KEY", "")
SCRAPER_COUNTRY = os.getenv("SCRAPER_COUNTRY", "").strip()
APP_USERNAME = os.getenv("APP_USERNAME", "user")
USE_PLAYWRIGHT = False
CARJET_PRICE_ADJUSTMENT_PCT = float(os.getenv("CARJET_PRICE_ADJUSTMENT_PCT", "0") or 0)
CARJET_PRICE_OFFSET_EUR = float(os.getenv("CARJET_PRICE_OFFSET_EUR", "0") or 0)
AUDIT_RETENTION_DAYS = int(os.getenv("AUDIT_RETENTION_DAYS", "90") or 90)
IMAGE_CACHE_DAYS = int(os.getenv("IMAGE_CACHE_DAYS", "365") or 365)
PRICES_CACHE_TTL_SECONDS = int(os.getenv("PRICES_CACHE_TTL_SECONDS", "300") or 300)
BULK_CONCURRENCY = int(os.getenv("BULK_CONCURRENCY", "6") or 6)
BULK_MAX_RETRIES = int(os.getenv("BULK_MAX_RETRIES", "2") or 2)
GLOBAL_FETCH_RPS = float(os.getenv("GLOBAL_FETCH_RPS", "5") or 5.0)

# --- Precompiled regexes for parser performance ---
AUTO_RX = re.compile(r"\b(auto|automatic|automatico|automático|automatik|aut\.|a/t|at|dsg|cvt|bva|tiptronic|steptronic|s\s*tronic|multidrive|multitronic|eat|eat6|eat8)\b", re.I)
BG_IMAGE_RX = re.compile(r"background-image\s*:\s*url\(([^)]+)\)", re.I)
LOGO_CODE_RX = re.compile(r"/logo_([A-Za-z0-9]+)\.", re.I)
CAR_CODE_RX = re.compile(r"car_([A-Za-z0-9]+)\.jpg", re.I)
OBJ_RX = re.compile(r"\{[^{}]*\"priceStr\"\s*:\s*\"[^\"]+\"[^{}]*\"id\"\s*:\s*\"[^\"]+\"[^{}]*\}", re.S)
DATAMAP_RX = re.compile(r"var\s+dataMap\s*=\s*(\[.*?\]);", re.S)

app = FastAPI(title="Rental Price Tracker")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, same_site="lax")
app.add_middleware(GZipMiddleware, minimum_size=500)

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    # Redirect to login on unauthorized/forbidden
    if exc.status_code in (401, 403):
        return RedirectResponse(url="/login", status_code=HTTP_303_SEE_OTHER)

# --- Admin: Test email ---
@app.get("/admin/test-email", response_class=HTMLResponse)
async def admin_test_email_page(request: Request):
    try:
        require_admin(request)
    except HTTPException:
        return RedirectResponse(url="/login", status_code=HTTP_303_SEE_OTHER)
    return templates.TemplateResponse("admin_test_email.html", {"request": request, "error": None, "ok": False})

@app.post("/admin/test-email", response_class=HTMLResponse)
async def admin_test_email_send(request: Request, to: str = Form("")):
    try:
        require_admin(request)
    except HTTPException:
        return RedirectResponse(url="/login", status_code=HTTP_303_SEE_OTHER)
    err = None
    try:
        _send_creds_email((to or "").strip(), "test.user", "Temp1234!")
    except Exception as e:
        err = str(e)
    ok = err is None
    return templates.TemplateResponse("admin_test_email.html", {"request": request, "error": err, "ok": ok})

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    try:
        (DEBUG_DIR / "last_exception.txt").write_text(_tb.format_exc(), encoding="utf-8")
    except Exception:
        pass
    # Ensure a valid response is always returned to Starlette
    return JSONResponse({"ok": False, "error": "Server error"}, status_code=500)

# --- Prices response cache (memory) ---
_PRICES_CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}

async def _compute_prices_for(url: str) -> Dict[str, Any]:
    headers = {"User-Agent": "Mozilla/5.0 (compatible; PriceTracker/1.0)"}
    # Use async fetch to avoid blocking and improve concurrency
    r = await async_fetch_with_optional_proxy(url, headers=headers)
    r.raise_for_status()
    html = r.text
    # Parse HTML off the main loop
    items = await asyncio.to_thread(parse_prices, html, url)
    items = convert_items_gbp_to_eur(items)
    items = apply_price_adjustments(items, url)
    # schedule image prefetch (best-effort)
    try:
        img_urls: List[str] = []
        for it in items:
            u = (it.get("photo") or "").strip()
            if u and (u.startswith("http://") or u.startswith("https://")):
                img_urls.append(u)
        if img_urls:
            asyncio.create_task(_prefetch_many(img_urls[:12]))
            asyncio.create_task(_delayed_prefetch(img_urls[12:64], 1.5))
    except Exception:
        pass
    return {"ok": True, "count": len(items), "items": items}

def _cache_get(url: str) -> Optional[Dict[str, Any]]:
    try:
        ts, payload = _PRICES_CACHE.get(url, (0.0, None))
        if not payload:
            return None
        age = time.time() - ts
        if age <= PRICES_CACHE_TTL_SECONDS:
            return payload
        return None
    except Exception:
        return None

def _cache_set(url: str, payload: Dict[str, Any]):
    try:
        _PRICES_CACHE[url] = (time.time(), payload)
    except Exception:
        pass

async def _refresh_prices_background(url: str):
    try:
        data = await _compute_prices_for(url)
        _cache_set(url, data)
    except Exception:
        pass
    return JSONResponse({"ok": False, "error": "Server error"}, status_code=500)

# --- Image cache proxy and retention ---
def _ext_from_content_type(ct: str) -> str:
    ct = (ct or "").lower()
    if "jpeg" in ct: return ".jpg"
    if "png" in ct: return ".png"
    if "webp" in ct: return ".webp"
    if "gif" in ct: return ".gif"
    if "svg" in ct: return ".svg"
    return ".bin"

def _guess_ext_from_url(u: str) -> str:
    try:
        p = u.split("?")[0]
        for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg"):
            if p.lower().endswith(ext):
                return ".jpg" if ext == ".jpeg" else ext
    except Exception:
        pass
    return ""

def _cache_path_for(url: str) -> Path:
    import hashlib
    h = hashlib.sha256(url.encode("utf-8")).hexdigest()
    return CACHE_CARS_DIR / h

def _serve_file(fp: Path, content_type: str = "application/octet-stream"):
    try:
        data = fp.read_bytes()
    except Exception:
        raise HTTPException(status_code=404, detail="Not found")
    headers = {"Cache-Control": f"public, max-age={IMAGE_CACHE_DAYS*86400}"}
    return Response(content=data, media_type=content_type or "application/octet-stream", headers=headers)

@app.get("/img")
async def img_proxy(request: Request, src: str):
    try:
        if not src or not (src.startswith("http://") or src.startswith("https://")):
            raise HTTPException(status_code=400, detail="Invalid src")
        key = _cache_path_for(src)
        meta = key.with_suffix(".meta")
        # Serve from cache if present
        if key.exists():
            try:
                now = time.time(); os.utime(key, (now, now));
                if meta.exists(): os.utime(meta, (now, now))
            except Exception:
                pass
            ct = "application/octet-stream"
            try:
                if meta.exists():
                    ct = (meta.read_text(encoding="utf-8").strip() or ct)
            except Exception:
                pass
            return _serve_file(key, ct)

        # On HEAD requests, don't fetch body, just forward and prime headers
        if request.method == "HEAD":
            import httpx
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                hr = await client.head(src)
            if hr.status_code != 200:
                raise HTTPException(status_code=404, detail="Upstream not found")
            headers = {"Cache-Control": f"public, max-age={IMAGE_CACHE_DAYS*86400}"}
            return Response(status_code=200, headers=headers)

        # Fetch from origin using requests for broader SSL compatibility, then cache
        import requests as _rq
        try:
            rr = _rq.get(src, timeout=15, headers={"User-Agent": "PriceTracker/1.0"})
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Upstream error: {type(e).__name__}")
        if rr.status_code != 200 or not rr.content:
            raise HTTPException(status_code=404, detail="Upstream not found")
        ct = rr.headers.get("content-type", "application/octet-stream")
        try:
            with key.open("wb") as f:
                f.write(rr.content)
            meta.write_text(ct, encoding="utf-8")
        except Exception:
            pass
        headers = {"Cache-Control": f"public, max-age={IMAGE_CACHE_DAYS*86400}"}
        return Response(content=rr.content, media_type=ct or "application/octet-stream", headers=headers)
    except HTTPException:
        raise
    except Exception as e:
        try:
            (DEBUG_DIR / "img_error.txt").write_text(f"{type(e).__name__}: {e}\n", encoding="utf-8")
        except Exception:
            pass
        raise HTTPException(status_code=500, detail="Image fetch error")

def cleanup_image_cache():
    try:
        cutoff = time.time() - IMAGE_CACHE_DAYS*86400
        for fp in CACHE_CARS_DIR.glob("*"):
            try:
                if fp.is_file():
                    st = fp.stat()
                    if max(st.st_mtime, st.st_atime) < cutoff:
                        fp.unlink(missing_ok=True)
            except Exception:
                continue
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

static_dir = BASE_DIR / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
# Persistent image cache under DATA_DIR
CACHE_CARS_DIR = Path(os.environ.get("CACHE_IMAGES_DIR", str(Path(os.environ.get("DATA_DIR", str(BASE_DIR))) / "cars")))
CACHE_CARS_DIR.mkdir(parents=True, exist_ok=True)
# Persisted uploads live under DATA_DIR and are served at /uploads
UPLOADS_ROOT = Path(os.environ.get("UPLOADS_ROOT", str(Path(os.environ.get("DATA_DIR", str(BASE_DIR))) / "uploads")))
UPLOADS_ROOT.mkdir(parents=True, exist_ok=True)
try:
    app.mount("/uploads", StaticFiles(directory=str(UPLOADS_ROOT)), name="uploads")
except Exception:
    pass
UPLOADS_DIR = UPLOADS_ROOT / "profiles"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

# --- Background image prefetch ---
async def _prefetch_image(url: str):
    try:
        if not url or not (url.startswith("http://") or url.startswith("https://")):
            return
        key = _cache_path_for(url)
        if key.exists() and key.stat().st_size > 0:
            # already cached
            try:
                now = time.time(); os.utime(key, (now, now))
            except Exception:
                pass
            return
        import httpx
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            r = await client.get(url)
            if r.status_code != 200 or not r.content:
                return
            try:
                with key.open("wb") as f:
                    f.write(r.content)
            except Exception:
                pass
    except Exception:
        pass

async def _prefetch_many(urls: List[str]):
    try:
        tasks = [asyncio.create_task(_prefetch_image(u)) for u in urls if isinstance(u, str) and u]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    except Exception:
        pass

async def _delayed_prefetch(urls: List[str], delay_seconds: float = 1.5):
    try:
        await asyncio.sleep(delay_seconds)
        await _prefetch_many(urls)
    except Exception:
        pass

# --- Icon fallbacks to avoid 404s ---
@app.get("/favicon.ico")
async def favicon_redirect():
    return RedirectResponse(url="/static/autoprudente-favicon.png?v=2", status_code=HTTP_303_SEE_OTHER)

@app.get("/apple-touch-icon.png")
async def apple_touch_icon_redirect():
    return RedirectResponse(url="/static/autoprudente-favicon.png?v=2", status_code=HTTP_303_SEE_OTHER)

@app.get("/apple-touch-icon-precomposed.png")
async def apple_touch_icon_pre_redirect():
    return RedirectResponse(url="/static/autoprudente-favicon.png?v=2", status_code=HTTP_303_SEE_OTHER)

@app.get("/static/ap-favicon.png")
async def static_ap_favicon_redirect():
    return RedirectResponse(url="/static/autoprudente-favicon.png?v=2", status_code=HTTP_303_SEE_OTHER)

DATA_DIR = Path(os.environ.get("DATA_DIR", str(BASE_DIR)))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "data.db"
_db_lock = Lock()
DEBUG_DIR = Path(os.environ.get("DEBUG_DIR", BASE_DIR / "static" / "debug"))
DEBUG_DIR.mkdir(parents=True, exist_ok=True)

# --- Admin/Users: DB helpers ---
def _db_connect():
    return sqlite3.connect(str(DB_PATH))

def _ensure_users_table():
    with _db_lock:
        con = _db_connect()
        try:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT UNIQUE NOT NULL,
                  password_hash TEXT NOT NULL,
                  first_name TEXT,
                  last_name TEXT,
                  mobile TEXT,
                  email TEXT,
                  profile_picture_path TEXT,
                  is_admin INTEGER DEFAULT 0,
                  enabled INTEGER DEFAULT 1,
                  created_at TEXT
                );
                """
            )
            con.commit()
        finally:
            con.close()

def _get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    try:
        with _db_lock:
            con = _db_connect()
            try:
                cur = con.execute("SELECT id, username, first_name, last_name, email, mobile, profile_picture_path, is_admin, enabled FROM users WHERE username=?", (username,))
                r = cur.fetchone()
                if not r:
                    return None
                return {
                    "id": r[0],
                    "username": r[1],
                    "first_name": r[2] or "",
                    "last_name": r[3] or "",
                    "email": r[4] or "",
                    "mobile": r[5] or "",
                    "profile_picture_path": r[6] or "",
                    "is_admin": bool(r[7]),
                    "enabled": bool(r[8]),
                }
            finally:
                con.close()
    except Exception:
        return None

# --- Activity Log ---
def _ensure_activity_table():
    with _db_lock:
        con = _db_connect()
        try:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS activity_log (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  ts_utc TEXT NOT NULL,
                  username TEXT,
                  action TEXT NOT NULL,
                  details TEXT,
                  ip TEXT,
                  user_agent TEXT
                );
                """
            )
            con.commit()
        finally:
            con.close()

def log_activity(request: Request, action: str, details: str = "", username: Optional[str] = None):
    try:
        _ensure_activity_table()
    except Exception:
        pass
    # best-effort metadata
    try:
        ip = request.client.host if request and request.client else None
    except Exception:
        ip = None
    ua = request.headers.get("user-agent", "") if request else ""
    user = username or (request.session.get("username") if request and request.session else None)
    try:
        with _db_lock:
            con = _db_connect()
            try:
                con.execute(
                    "INSERT INTO activity_log (ts_utc, username, action, details, ip, user_agent) VALUES (?,?,?,?,?,?)",
                    (datetime.now(timezone.utc).isoformat(), user, action, details, ip or "", ua[:300])
                )
                con.commit()
            finally:
                con.close()
    except Exception:
        pass
    pass

def cleanup_activity_retention():
    try:
        _ensure_activity_table()
        if AUDIT_RETENTION_DAYS <= 0:
            return
        cutoff = datetime.now(timezone.utc).timestamp() - AUDIT_RETENTION_DAYS*86400
        # Compare lexicographically on ISO timestamps by computing a boundary
        cutoff_iso = datetime.utcfromtimestamp(cutoff).replace(tzinfo=timezone.utc).isoformat()
        with _db_lock:
            con = _db_connect()
            try:
                con.execute("DELETE FROM activity_log WHERE ts_utc < ?", (cutoff_iso,))
                con.commit()
            finally:
                con.close()
    except Exception:
        pass

def _hash_password(pw: str, salt: str = ""):  # basic salted sha256
    if not salt:
        salt = secrets.token_hex(8)
    digest = hashlib.sha256((salt + ":" + pw).encode("utf-8")).hexdigest()
    return f"sha256:{salt}:{digest}"

def _verify_password(pw: str, stored: str) -> bool:
    try:
        algo, salt, digest = stored.split(":", 2)
        if algo != "sha256":
            return False
        test = hashlib.sha256((salt + ":" + pw).encode("utf-8")).hexdigest()
        return secrets.compare_digest(test, digest)
    except Exception:
        return False

def _send_creds_email(to_email: str, username: str, password: str):
    host = os.getenv("SMTP_HOST", "").strip()
    port = int(os.getenv("SMTP_PORT", "587") or 587)
    user = os.getenv("SMTP_USERNAME", "").strip()
    pwd = os.getenv("SMTP_PASSWORD", "").strip()
    from_addr = os.getenv("SMTP_FROM", "no-reply@example.com").strip()
    use_tls = str(os.getenv("SMTP_TLS", "true")).lower() in ("1", "true", "yes", "y", "on")
    if not host or not to_email:
        try:
            (DEBUG_DIR / "mail_error.txt").write_text("Missing SMTP_HOST or recipient\n", encoding="utf-8")
        except Exception:
            pass
        return
    msg = EmailMessage()
    msg["Subject"] = "Your Car Rental Tracker account"
    msg["From"] = from_addr
    msg["To"] = to_email
    # Plain text
    msg.set_content(
        f"Hello,\n\nYour account was created.\n\nUsername: {username}\nPassword: {password}\n\nLogin: https://cartracker-6twv.onrender.com\n\nPlease change your password after first login."
    )
    # Simple branded HTML
    html = f"""
    <!doctype html>
    <html>
      <body style="margin:0;padding:0;background:#f8fafc;font-family:system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f8fafc;padding:24px 0;">
          <tr>
            <td align="center">
              <table role="presentation" width="560" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:10px;overflow:hidden;border:1px solid #e5e7eb;">
                <tr>
                  <td style="background:#009cb6;padding:16px 20px;">
                    <img src="https://cartracker-6twv.onrender.com/static/ap-heather.png" alt="Car Rental Tracker" style="height:40px;display:block" />
                  </td>
                </tr>
                <tr>
                  <td style="padding:20px 20px 8px 20px;color:#111827;font-size:16px;">Hello,</td>
                </tr>
                <tr>
                  <td style="padding:0 20px 16px 20px;color:#111827;font-size:16px;">Your account was created.</td>
                </tr>
                <tr>
                  <td style="padding:0 20px 16px 20px;color:#111827;font-size:14px;line-height:1.6;">
                    <div><strong>Username:</strong> {username}</div>
                    <div><strong>Password:</strong> {password}</div>
                  </td>
                </tr>
                <tr>
                  <td align="center" style="padding:8px 20px 24px 20px;">
                    <a href="https://cartracker-6twv.onrender.com/login" style="display:inline-block;background:#009cb6;color:#ffffff;text-decoration:none;padding:10px 16px;border-radius:8px;font-size:14px;">Login</a>
                  </td>
                </tr>
                <tr>
                  <td style="padding:0 20px 24px 20px;color:#6b7280;font-size:12px;">Please change your password after first login.</td>
                </tr>
              </table>
            </td>
          </tr>
        </table>
      </body>
    </html>
    """
    msg.add_alternative(html, subtype="html")
    try:
        if use_tls:
            with smtplib.SMTP(host, port, timeout=15) as s:
                s.starttls()
                if user and pwd:
                    s.login(user, pwd)
                s.send_message(msg)
        else:
            with smtplib.SMTP_SSL(host, port, timeout=15) as s:
                if user and pwd:
                    s.login(user, pwd)
                s.send_message(msg)
    except Exception as e:
        try:
            (DEBUG_DIR / "mail_error.txt").write_text(f"{type(e).__name__}: {e}\n", encoding="utf-8")
        except Exception:
            pass

# Simple FX cache to avoid repeated HTTP calls
_FX_CACHE: Dict[str, Tuple[float, float]] = {}  # key "GBP->EUR" -> (rate, ts)
_URL_CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}  # key normalized URL -> (ts, response payload)

# Ensure users table and seed initial admin on startup
try:
    _ensure_users_table()
    with _db_lock:
        con = _db_connect()
        try:
            cur = con.execute("SELECT id FROM users WHERE username=?", (APP_USERNAME,))
            row = cur.fetchone()
            if not row:
                pw_hash = _hash_password(APP_PASSWORD)
                con.execute(
                    "INSERT INTO users (username, password_hash, first_name, last_name, email, is_admin, enabled, created_at) VALUES (?,?,?,?,?,?,?,?)",
                    (APP_USERNAME, pw_hash, "", "", "", 1, 1, time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()))
                )
                con.commit()
        finally:
            con.close()
except Exception:
    pass

def _fx_rate_gbp_eur(timeout: float = 5.0) -> float:
    key = "GBP->EUR"
    now = time.time()
    cached = _FX_CACHE.get(key)
    if cached and now - cached[1] < 3600:
        return cached[0]
    try:
        r = requests.get(
            "https://api.exchangerate.host/latest",
            params={"base": "GBP", "symbols": "EUR"},
            timeout=timeout,
        )
        if r.status_code == 200:
            data = r.json()
            rate = float(data.get("rates", {}).get("EUR") or 0)
            if rate > 0:
                _FX_CACHE[key] = (rate, now)
                return rate
    except Exception:
        pass
    # conservative fallback
    return cached[0] if cached else 1.16

def _parse_amount(s: str) -> Optional[float]:
    try:
        m = re.search(r"([0-9][0-9\.,\s]*)", s or "")
        if not m:
            return None
        num = m.group(1).replace("\u00a0", "").replace(" ", "")
        has_comma = "," in num
        has_dot = "." in num
        if has_comma and has_dot:
            num = num.replace(".", "").replace(",", ".")
        elif has_comma and not has_dot:
            num = num.replace(",", ".")
        else:
            parts = num.split(".")
            if len(parts) > 2:
                num = "".join(parts)
        v = float(num)
        return v
    except Exception:
        return None

def _format_eur(v: float) -> str:
    try:
        s = f"{v:,.2f}"
        s = s.replace(",", "_").replace(".", ",").replace("_", ".")
        return f"{s} €"
    except Exception:
        return f"{v:.2f} €"

def convert_items_gbp_to_eur(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rate = _fx_rate_gbp_eur()
    out = []
    for it in items or []:
        price_txt = it.get("price") or ""
        if "£" in price_txt or re.search(r"\bGBP\b", price_txt, re.I):
            amt = _parse_amount(price_txt)
            if amt is not None:
                eur = amt * rate
                it = dict(it)
                it["price"] = _format_eur(eur)
                it["currency"] = "EUR"
        out.append(it)
    return out

# CarJet destination codes we target
LOCATION_CODES = {
    "albufeira": "ABF01",
    "albufeira cidade": "ABF01",
    "faro airport": "FAO02",
    "faro aeroporto": "FAO02",
    "aeroporto de faro": "FAO02",
}

def init_db():
    with _db_lock:
        conn = sqlite3.connect(DB_PATH)
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS price_snapshots (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  ts TEXT NOT NULL,
                  location TEXT NOT NULL,
                  pickup_date TEXT NOT NULL,
                  pickup_time TEXT NOT NULL,
                  days INTEGER NOT NULL,
                  supplier TEXT,
                  car TEXT,
                  price_text TEXT,
                  price_num REAL,
                  currency TEXT,
                  link TEXT
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_q ON price_snapshots(location, days, ts)")
        finally:
            conn.commit()
            conn.close()

init_db()


IDLE_TIMEOUT_SECONDS = 30 * 60  # 30 minutes

@app.get("/healthz")
async def healthz():
    return JSONResponse({"ok": True})

def require_auth(request: Request):
    if not request.session.get("auth", False):
        raise HTTPException(status_code=401, detail="Unauthorized")
    # Enforce inactivity timeout
    try:
        now = int(datetime.now(timezone.utc).timestamp())
        last = int(request.session.get("last_active_ts", 0))
        if last and now - last > IDLE_TIMEOUT_SECONDS:
            request.session.clear()
            raise HTTPException(status_code=401, detail="Session expired")
        # update last activity timestamp
        request.session["last_active_ts"] = now
    except Exception:
        # if any parsing error, refresh the timestamp anyway
        request.session["last_active_ts"] = int(datetime.now(timezone.utc).timestamp())

def require_admin(request: Request):
    require_auth(request)
    if not request.session.get("is_admin", False):
        raise HTTPException(status_code=403, detail="Forbidden")

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if request.session.get("auth"):
        return RedirectResponse(url="/", status_code=HTTP_303_SEE_OTHER)
    return templates.TemplateResponse("login.html", {"request": request, "error": None})

@app.post("/login")
async def login_action(request: Request, username: str = Form(...), password: str = Form(...)):
    try:
        u = (username or "").strip()
        p = (password or "").strip()
        try:
            with (DEBUG_DIR / "login_trace.txt").open("a", encoding="utf-8") as f:
                f.write(f"attempt {datetime.now(timezone.utc).isoformat()} user={u}\n")
        except Exception:
            pass
        # Check DB users
        is_admin_flag = False
        ok = False
        try:
            with _db_lock:
                con = _db_connect()
                try:
                    cur = con.execute("SELECT id, password_hash, is_admin, enabled FROM users WHERE username=?", (u,))
                    row = cur.fetchone()
                    if row and row[3]:
                        ok = _verify_password(p, row[1])
                        is_admin_flag = bool(row[2])
                finally:
                    con.close()
        except Exception:
            ok = False
        # Fallback to env user for safety
        if not ok and u == APP_USERNAME and p == APP_PASSWORD:
            ok = True
            is_admin_flag = True
        if ok:
            request.session["auth"] = True
            request.session["username"] = u
            request.session["is_admin"] = bool(is_admin_flag)
            request.session["last_active_ts"] = int(datetime.now(timezone.utc).timestamp())
            log_activity(request, "login_success", details="", username=u)
            try:
                with (DEBUG_DIR / "login_trace.txt").open("a", encoding="utf-8") as f:
                    f.write(f"success {datetime.now(timezone.utc).isoformat()} user={u}\n")
            except Exception:
                pass
            return RedirectResponse(url="/", status_code=HTTP_303_SEE_OTHER)
        try:
            with (DEBUG_DIR / "login_trace.txt").open("a", encoding="utf-8") as f:
                f.write(f"invalid {datetime.now(timezone.utc).isoformat()} user={u}\n")
        except Exception:
            pass
        log_activity(request, "login_failure", details="", username=u)
        return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid credentials"})
    except Exception:
        try:
            (DEBUG_DIR / "login_error.txt").write_text(_tb.format_exc(), encoding="utf-8")
        except Exception:
            pass
        log_activity(request, "login_exception", details="see login_error.txt")
        return templates.TemplateResponse("login.html", {"request": request, "error": "Login failed. Please try again."})

@app.post("/logout")
async def logout_action(request: Request):
    try:
        log_activity(request, "logout")
    except Exception:
        pass
    request.session.clear()
    return RedirectResponse(url="/login", status_code=HTTP_303_SEE_OTHER)


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    try:
        require_auth(request)
    except HTTPException:
        return RedirectResponse(url="/login", status_code=HTTP_303_SEE_OTHER)
    # load current user profile for greeting
    user_ctx = None
    try:
        uname = request.session.get("username")
        if uname:
            user_ctx = _get_user_by_username(uname)
    except Exception:
        user_ctx = None
    return templates.TemplateResponse("index.html", {"request": request, "current_user": user_ctx})

@app.get("/admin")
async def admin_root():
    return RedirectResponse(url="/admin/users", status_code=HTTP_303_SEE_OTHER)

# --- Admin: environment summary and adjustment preview ---
@app.get("/admin/env-summary")
async def admin_env_summary(request: Request):
    try:
        require_admin(request)
    except HTTPException:
        return RedirectResponse(url="/login", status_code=HTTP_303_SEE_OTHER)
    try:
        cj_pct, cj_off = _get_carjet_adjustment()
        data = {
            "CARJET_PRICE_ADJUSTMENT_PCT": cj_pct,
            "CARJET_PRICE_OFFSET_EUR": cj_off,
            "PRICES_CACHE_TTL_SECONDS": PRICES_CACHE_TTL_SECONDS,
            "BULK_CONCURRENCY": BULK_CONCURRENCY,
            "BULK_MAX_RETRIES": BULK_MAX_RETRIES,
            "GLOBAL_FETCH_RPS": GLOBAL_FETCH_RPS,
        }
        return JSONResponse({"ok": True, "env": data})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

@app.get("/admin/adjust-preview")
async def admin_adjust_preview(request: Request, price: str, url: str):
    try:
        require_admin(request)
    except HTTPException:
        return RedirectResponse(url="/login", status_code=HTTP_303_SEE_OTHER)
    try:
        # determine if adjustment applies
        is_cj = False
        try:
            from urllib.parse import urlparse as _parse
            is_cj = _parse(url).netloc.endswith("carjet.com")
        except Exception:
            is_cj = False
        pct, off = _get_carjet_adjustment()
        amt = _parse_amount(price)
        if amt is None:
            return JSONResponse({"ok": False, "error": "Invalid price format"}, status_code=400)
        adjusted = amt
        if is_cj and (pct != 0 or off != 0):
            adjusted = amt * (1.0 + (pct/100.0)) + off
        return _no_store_json({
            "ok": True,
            "input": {"price": price, "url": url},
            "env": {"pct": pct, "offset": off},
            "is_carjet": is_cj,
            "amount": amt,
            "adjusted_amount": adjusted,
            "adjusted_price": _format_eur(adjusted),
        })
    except Exception as e:
        return _no_store_json({"ok": False, "error": str(e)}, status_code=500)

@app.get("/admin/settings", response_class=HTMLResponse)
async def admin_settings_page(request: Request):
    try:
        require_admin(request)
    except HTTPException:
        return RedirectResponse(url="/login", status_code=HTTP_303_SEE_OTHER)
    cj_pct, cj_off = _get_carjet_adjustment()
    return templates.TemplateResponse("admin_settings.html", {"request": request, "carjet_pct": cj_pct, "carjet_off": cj_off, "saved": False, "error": None})

@app.post("/admin/settings", response_class=HTMLResponse)
async def admin_settings_save(request: Request, carjet_pct: str = Form(""), carjet_off: str = Form("")):
    try:
        require_admin(request)
    except HTTPException:
        return RedirectResponse(url="/login", status_code=HTTP_303_SEE_OTHER)
    err = None
    try:
        pct_val = float((carjet_pct or "0").replace(",", "."))
        off_val = float((carjet_off or "0").replace(",", "."))
        _set_setting("carjet_pct", str(pct_val))
        _set_setting("carjet_off", str(off_val))
        cj_pct, cj_off = pct_val, off_val
    except Exception as e:
        err = str(e)
        cj_pct, cj_off = _get_carjet_adjustment()
    return templates.TemplateResponse("admin_settings.html", {"request": request, "carjet_pct": cj_pct, "carjet_off": cj_off, "saved": err is None, "error": err})

@app.post("/admin/users/{user_id}/toggle-enabled")
async def admin_users_toggle_enabled(request: Request, user_id: int):
    try:
        require_admin(request)
    except HTTPException:
        return RedirectResponse(url="/login", status_code=HTTP_303_SEE_OTHER)
    with _db_lock:
        con = _db_connect()
        try:
            cur = con.execute("SELECT enabled FROM users WHERE id=?", (user_id,))
            r = cur.fetchone()
            if not r:
                raise HTTPException(status_code=404, detail="Not found")
            new_val = 0 if int(r[0] or 0) else 1
            con.execute("UPDATE users SET enabled=? WHERE id=?", (new_val, user_id))
            con.commit()
        finally:
            con.close()
    try:
        log_activity(request, "admin_edit_user", details=f"user_id={user_id}")
    except Exception:
        pass
    return RedirectResponse(url="/admin/users", status_code=HTTP_303_SEE_OTHER)

@app.post("/admin/users/{user_id}/reset-password")
async def admin_users_reset_password(request: Request, user_id: int):
    try:
        require_admin(request)
    except HTTPException:
        return RedirectResponse(url="/login", status_code=HTTP_303_SEE_OTHER)
    gen_pw = secrets.token_urlsafe(8)
    pw_hash = _hash_password(gen_pw)
    to_email = None
    username = None
    with _db_lock:
        con = _db_connect()
        try:
            cur = con.execute("SELECT username, email FROM users WHERE id=?", (user_id,))
            r = cur.fetchone()
            if not r:
                raise HTTPException(status_code=404, detail="Not found")
            username = r[0]
            to_email = (r[1] or "").strip()
            con.execute("UPDATE users SET password_hash=? WHERE id=?", (pw_hash, user_id))
            con.commit()
        finally:
            con.close()
    try:
        if to_email:
            _send_creds_email(to_email, username or "", gen_pw)
    except Exception:
        pass
    try:
        log_activity(request, "admin_reset_password", details=f"user_id={user_id}")
    except Exception:
        pass
    return RedirectResponse(url="/admin/users", status_code=HTTP_303_SEE_OTHER)

@app.get("/admin/users/{user_id}/edit", response_class=HTMLResponse)
async def admin_users_edit(request: Request, user_id: int):
    try:
        require_admin(request)
    except HTTPException:
        return RedirectResponse(url="/login", status_code=HTTP_303_SEE_OTHER)
    with _db_lock:
        con = _db_connect()
        try:
            cur = con.execute("SELECT id, username, first_name, last_name, email, mobile, profile_picture_path, is_admin, enabled FROM users WHERE id=?", (user_id,))
            r = cur.fetchone()
            if not r:
                raise HTTPException(status_code=404, detail="Not found")
            u = {
                "id": r[0], "username": r[1], "first_name": r[2] or "", "last_name": r[3] or "",
                "email": r[4] or "", "mobile": r[5] or "", "profile_picture_path": r[6] or "",
                "is_admin": bool(r[7]), "enabled": bool(r[8])
            }
        finally:
            con.close()
    return templates.TemplateResponse("admin_edit_user.html", {"request": request, "u": u, "error": None})

@app.post("/admin/users/{user_id}/edit")
async def admin_users_edit_post(
    request: Request,
    user_id: int,
    first_name: str = Form(""),
    last_name: str = Form(""),
    mobile: str = Form(""),
    email: str = Form(""),
    is_admin: str = Form("0"),
    enabled: str = Form("1"),
    new_password: str = Form(""),
    picture: Optional[UploadFile] = File(None),
):
    try:
        require_admin(request)
    except HTTPException:
        return RedirectResponse(url="/login", status_code=HTTP_303_SEE_OTHER)
    pic_path = None
    if picture and picture.filename:
        safe_name = f"{int(time.time())}_{os.path.basename(picture.filename)}".replace("..", ".")
        dest = UPLOADS_DIR / safe_name
        data = await picture.read()
        dest.write_bytes(data)
        pic_path = f"/uploads/profiles/{safe_name}"
    with _db_lock:
        con = _db_connect()
        try:
            if pic_path:
                con.execute(
                    "UPDATE users SET first_name=?, last_name=?, mobile=?, email=?, profile_picture_path=?, is_admin=?, enabled=? WHERE id=?",
                    (first_name, last_name, mobile, email, pic_path, 1 if is_admin in ("1","true","on") else 0, 1 if enabled in ("1","true","on") else 0, user_id)
                )
            else:
                con.execute(
                    "UPDATE users SET first_name=?, last_name=?, mobile=?, email=?, is_admin=?, enabled=? WHERE id=?",
                    (first_name, last_name, mobile, email, 1 if is_admin in ("1","true","on") else 0, 1 if enabled in ("1","true","on") else 0, user_id)
                )
            # Optional password change
            if new_password and new_password.strip():
                pw_hash = _hash_password(new_password.strip())
                con.execute("UPDATE users SET password_hash=? WHERE id=?", (pw_hash, user_id))
            con.commit()
        finally:
            con.close()
    return RedirectResponse(url="/admin/users", status_code=HTTP_303_SEE_OTHER)

@app.post("/admin/users/{user_id}/delete")
async def admin_users_delete(request: Request, user_id: int):
    try:
        require_admin(request)
    except HTTPException:
        return RedirectResponse(url="/login", status_code=HTTP_303_SEE_OTHER)
    # prevent deleting self
    current_username = request.session.get("username")
    with _db_lock:
        con = _db_connect()
        try:
            cur = con.execute("SELECT username FROM users WHERE id=?", (user_id,))
            r = cur.fetchone()
            if not r:
                raise HTTPException(status_code=404, detail="Not found")
            if r[0] == current_username:
                raise HTTPException(status_code=400, detail="Cannot delete own account")
            con.execute("DELETE FROM users WHERE id=?", (user_id,))
            con.commit()
        finally:
            con.close()
    return RedirectResponse(url="/admin/users", status_code=HTTP_303_SEE_OTHER)

# --- Admin UI ---
@app.get("/admin/users", response_class=HTMLResponse)
async def admin_users(request: Request):
    try:
        require_admin(request)
    except HTTPException:
        return RedirectResponse(url="/login", status_code=HTTP_303_SEE_OTHER)
    users = []
    try:
        with _db_lock:
            con = _db_connect()
            try:
                cur = con.execute("SELECT id, username, first_name, last_name, email, mobile, is_admin, enabled FROM users ORDER BY id DESC")
                for r in cur.fetchall():
                    users.append({
                        "id": r[0], "username": r[1], "first_name": r[2] or "", "last_name": r[3] or "",
                        "email": r[4] or "", "mobile": r[5] or "", "is_admin": bool(r[6]), "enabled": bool(r[7])
                    })
            finally:
                con.close()
    except Exception:
        return JSONResponse({"ok": False, "error": "Failed to load users"}, status_code=500)
    return templates.TemplateResponse("admin_users.html", {"request": request, "users": users})


@app.get("/admin/users/new", response_class=HTMLResponse)
async def admin_users_new(request: Request):
    try:
        require_admin(request)
    except HTTPException:
        return RedirectResponse(url="/login", status_code=HTTP_303_SEE_OTHER)
    return templates.TemplateResponse("admin_new_user.html", {"request": request, "error": None})

@app.post("/admin/users/new")
async def admin_users_new_post(
    request: Request,
    username: str = Form(...),
    first_name: str = Form(""),
    last_name: str = Form(""),
    mobile: str = Form(""),
    email: str = Form(""),
    is_admin: str = Form("0"),
    picture: Optional[UploadFile] = File(None),
):
    try:
        require_admin(request)
    except HTTPException:
        return RedirectResponse(url="/login", status_code=HTTP_303_SEE_OTHER)
    u = (username or "").strip()
    if not u:
        return templates.TemplateResponse("admin_new_user.html", {"request": request, "error": "Username required"})
    # generate password
    gen_pw = secrets.token_urlsafe(8)
    pw_hash = _hash_password(gen_pw)
    pic_path = None
    if picture and picture.filename:
        safe_name = f"{int(time.time())}_{os.path.basename(picture.filename)}".replace("..", ".")
        dest = UPLOADS_DIR / safe_name
        data = await picture.read()
        dest.write_bytes(data)
        pic_path = f"/uploads/profiles/{safe_name}"
    with _db_lock:
        con = _db_connect()
        try:
            con.execute(
                "INSERT INTO users (username, password_hash, first_name, last_name, mobile, email, profile_picture_path, is_admin, enabled, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (u, pw_hash, first_name, last_name, mobile, email, pic_path or "", 1 if (is_admin in ("1","true","on")) else 0, 1, time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()))
            )
            con.commit()
        except sqlite3.IntegrityError:
            return templates.TemplateResponse("admin_new_user.html", {"request": request, "error": "Username already exists"})
        finally:
            con.close()
    # send email if provided
    if email:
        _send_creds_email(email, u, gen_pw)
    try:
        log_activity(request, "admin_create_user", details=f"username={u}")
    except Exception:
        pass
    return RedirectResponse(url="/admin/users", status_code=HTTP_303_SEE_OTHER)


@app.get("/api/prices")
async def get_prices(request: Request):
    require_auth(request)
    url = request.query_params.get("url") or TARGET_URL
    # Serve from cache if fresh
    cached = _cache_get(url)
    if cached:
        # also refresh in background to keep fresh
        asyncio.create_task(_refresh_prices_background(url))
        return JSONResponse(cached)
    # If we have stale data (beyond TTL) we could still serve it while refreshing. For simplicity, compute now.
    try:
        data = await _compute_prices_for(url)
        _cache_set(url, data)
        return JSONResponse(data)
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

@app.post("/api/track-by-params")
async def track_by_params(request: Request):
    try:
        require_auth(request)
    except HTTPException:
        return JSONResponse({"ok": False, "error": "Unauthorized"}, status_code=401)
    try:
        body = await request.json()
    except Exception:
        body = {}
    location = str(body.get("location") or "").strip()
    start_date = str(body.get("start_date") or "").strip()
    start_time = str(body.get("start_time") or "10:00").strip() or "10:00"
    end_date_in = str(body.get("end_date") or "").strip()
    end_time = str(body.get("end_time") or "10:00").strip() or "10:00"
    # days is optional if end_date provided
    try:
        days = int(body.get("days") or 0)
    except Exception:
        days = 0
    lang = str(body.get("lang") or "pt").strip() or "pt"
    currency = str(body.get("currency") or "EUR").strip() or "EUR"
    if not location or not start_date:
        return _no_store_json({"ok": False, "error": "Missing location or start_date"}, status_code=400)
    try:
        # Build start datetime with provided time
        start_dt = datetime.fromisoformat(f"{start_date}T{start_time}")
    except Exception:
        return _no_store_json({"ok": False, "error": "Invalid start_date (YYYY-MM-DD)"}, status_code=400)
    # Determine end datetime
    if end_date_in:
        try:
            end_dt = datetime.fromisoformat(f"{end_date_in}T{end_time}")
        except Exception:
            return _no_store_json({"ok": False, "error": "Invalid end_date (YYYY-MM-DD)"}, status_code=400)
        if end_dt <= start_dt:
            return _no_store_json({"ok": False, "error": "end_date/time must be after start"}, status_code=400)
        days = max(1, (end_dt - start_dt).days)
    else:
        if days <= 0:
            return _no_store_json({"ok": False, "error": "Missing days or end_date"}, status_code=400)
        end_dt = start_dt + timedelta(days=days)
    try:
        html = try_direct_carjet(location, start_dt, end_dt, lang=lang, currency=currency)
        # DEBUG: persist fetched HTML for troubleshooting
        try:
            _stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            _loc_tag = re.sub(r"[^a-z0-9]+", "-", (location or "").lower())
            (_fp := (DEBUG_DIR / f"track_params-{_loc_tag}-{start_dt.date()}-{days}d-{_stamp}.html")).write_text(html or "", encoding="utf-8")
        except Exception:
            pass
        if not html:
            return _no_store_json({"ok": False, "error": "Upstream fetch failed"}, status_code=502)
        base = f"https://www.carjet.com/do/list/{lang}"
        items = parse_prices(html, base)
        items = convert_items_gbp_to_eur(items)
        items = apply_price_adjustments(items, base)
        # DEBUG: write a compact summary JSON (count and first 5 items)
        try:
            import json as _json
            _sum = {
                "ts": _stamp,
                "location": location,
                "start": start_dt.isoformat(),
                "end": end_dt.isoformat(),
                "days": days,
                "count": len(items or []),
                "preview": (items or [])[:5],
            }
            (DEBUG_DIR / f"track_params-summary-{_loc_tag}-{_stamp}.json").write_text(_json.dumps(_sum, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
        return _no_store_json({
            "ok": True,
            "items": items,
            "location": location,
            "start_date": start_dt.date().isoformat(),
            "start_time": start_dt.strftime("%H:%M"),
            "end_date": end_dt.date().isoformat(),
            "end_time": end_dt.strftime("%H:%M"),
            "days": days,
        })
    except Exception as e:
        return _no_store_json({"ok": False, "error": str(e)}, status_code=500)

@app.get("/ph")
async def placeholder_image(car: str = "Car"):
    try:
        label = (car or "Car").strip()
        if len(label) > 32:
            label = label[:32] + "…"
        # Teal background (#009cb6) to match site, white centered text
        svg = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="320" height="180" viewBox="0 0 320 180" role="img">
  <rect width="320" height="180" fill="#009cb6"/>
  <text x="160" y="90" fill="#ffffff" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,Helvetica,Arial,sans-serif" font-size="18" text-anchor="middle" dominant-baseline="middle">{label}</text>
  <text x="160" y="160" fill="rgba(255,255,255,0.7)" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,Helvetica,Arial,sans-serif" font-size="12" text-anchor="middle">Image unavailable</text>
</svg>'''
        resp = Response(content=svg, media_type="image/svg+xml; charset=utf-8")
        resp.headers["Cache-Control"] = "public, max-age=86400"
        return resp
    except Exception:
        return Response(status_code=500)

def _normalize_model_for_image(name: str) -> str:
    s = (name or "").lower()
    s = re.sub(r"\b(auto|automatic|manual|station\s*wagon|estate|sw|variant|break|tourer|grandtour|grand\s*tour|kombi|sportbreak|sport\s*brake|st)\b", "", s)
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    # common brand/model reorderings are left as-is
    return " ".join(s.split())

def _build_commons_query(name: str) -> str:
    key = _normalize_model_for_image(name)
    # bias towards car photos
    return f"{key} car"

def _save_cache_image(key: str, content: bytes, ext: str) -> Path:
    p = CACHE_CARS_DIR / f"{key}{ext}"
    with open(p, "wb") as f:
        f.write(content)
    return p

def _find_cached_image(key: str) -> Optional[Path]:
    for ext in (".jpg", ".jpeg", ".png", ".webp"):
        p = CACHE_CARS_DIR / f"{key}{ext}"
        if p.exists() and p.stat().st_size > 0:
            return p
    return None

@app.get("/imglookup")
async def img_lookup(car: str):
    try:
        car = car or "Car"
        key = _normalize_model_for_image(car).replace(" ", "-")
        cached = _find_cached_image(key)
        if cached:
            ct = "image/jpeg"
            if cached.suffix == ".png": ct = "image/png"
            elif cached.suffix == ".webp": ct = "image/webp"
            with open(cached, "rb") as f:
                b = f.read()
            resp = Response(content=b, media_type=ct)
            resp.headers["Cache-Control"] = "public, max-age=86400"
            return resp

        # Wikimedia Commons API search for files
        import json as _json
        api = "https://commons.wikimedia.org/w/api.php"
        params = {
            "action": "query",
            "format": "json",
            "prop": "imageinfo",
            "generator": "search",
            "gsrsearch": _build_commons_query(car),
            "gsrlimit": "5",
            "gsrnamespace": "6",  # File namespace
            "iiprop": "url|mime",
            "iiurlwidth": "480",
            "origin": "*",
        }
        r = requests.get(api, params=params, timeout=10, headers={"User-Agent": "PriceTracker/1.0"})
        url = None
        mime = None
        if r.ok:
            data = r.json()
            pages = (data.get("query", {}) or {}).get("pages", {})
            for _, pg in pages.items():
                ii = (pg.get("imageinfo") or [{}])[0]
                url = ii.get("thumburl") or ii.get("url")
                mime = ii.get("mime") or "image/jpeg"
                if url:
                    break
        if url:
            ir = requests.get(url, timeout=10, headers={"User-Agent": "PriceTracker/1.0"})
            if ir.ok and ir.content:
                ext = ".jpg"
                if (mime or "").endswith("png"): ext = ".png"
                elif (mime or "").endswith("webp"): ext = ".webp"
                path = _save_cache_image(key, ir.content, ext)
                resp = Response(content=ir.content, media_type=mime or "image/jpeg")
                resp.headers["Cache-Control"] = "public, max-age=86400"
                return resp
        # Fallback to placeholder
        return await placeholder_image(car)
    except Exception:
        return await placeholder_image(car)

@app.get("/api/debug_direct")
async def debug_direct(request: Request):
    params = request.query_params
    location = params.get("location", "Albufeira")
    pickup_date = params.get("date")
    pickup_time = params.get("time", "10:00")
    days = int(params.get("days", 1))
    lang = params.get("lang", "pt")
    currency = params.get("currency", "EUR")
    if not pickup_date:
        return JSONResponse({"ok": False, "error": "Missing date (YYYY-MM-DD)"}, status_code=400)

    try:
        from datetime import datetime, timedelta
        start_dt = datetime.fromisoformat(pickup_date + "T" + pickup_time)
        end_dt = start_dt + timedelta(days=days)
        html = try_direct_carjet(location, start_dt, end_dt, lang=lang, currency=currency)
        if not html:
            return JSONResponse({"ok": False, "error": "Empty HTML from direct POST"}, status_code=500)

        # Save to debug file
        from datetime import datetime as _dt
        stamp = _dt.utcnow().strftime("%Y%m%dT%H%M%S")
        filename = f"debug-direct-{location.replace(' ', '-')}-{pickup_date}-{days}d.html"
        out_path = DEBUG_DIR / filename
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(html)

        # Quick selector counts
        soup = BeautifulSoup(html, "lxml")
        # Price-like selector counts and inline dataMap presence
        counts = {
            ".price": len(soup.select(".price")),
            ".amount": len(soup.select(".amount")),
            "[class*='price']": len(soup.select("[class*='price']")),
            "a[href]": len(soup.select("a[href]")),
        }
        try:
            import json as _json
            m = re.search(r"var\s+dataMap\s*=\s*(\[.*?\]);", html, re.S)
            if m:
                arr = _json.loads(m.group(1))
                counts["has_dataMap"] = True
                counts["dataMap_len"] = len(arr)
            else:
                counts["has_dataMap"] = False
                counts["dataMap_len"] = 0
        except Exception:
            counts["has_dataMap"] = False
            counts["dataMap_len"] = 0
        return JSONResponse({
            "ok": True,
            "url": f"https://www.carjet.com/do/list/{lang} (direct)",
            "debug_file": f"/static/debug/{filename}",
            "counts": counts,
        })
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


def parse_prices(html: str, base_url: str) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, "lxml")
    items: List[Dict[str, Any]] = []
    # Flattened page text to infer context-specific categories (e.g., automatic families)
    try:
        _page_text = soup.get_text(" ", strip=True).lower()
    except Exception:
        _page_text = ""

    # Helper: detect automatic transmission markers from name or card text or explicit label
    def _is_auto_flag(name_lc: str, card_text_lc: str, trans_label: str) -> bool:
        try:
            if (trans_label or '').lower() == 'automatic':
                return True
            return bool(AUTO_RX.search(name_lc or '') or AUTO_RX.search(card_text_lc or ''))
        except Exception:
            return False

    # Blocklist of car models to exclude
    _blocked_models = [
        "Mercedes S Class Auto",
        "MG ZS Auto",
        "Mercedes CLA Coupe Auto",
        "Mercedes A Class",
        "Mercedes A Class Auto",
        "BMW 1 Series Auto",
        "BMW 3 Series SW Auto",
        "Volvo V60 Auto",
        "Volvo XC40 Auto",
        "Mercedes C Class Auto",
        "Tesla Model 3 Auto",
        "Electric",
        "BMW 2 Series Gran Coupe Auto",
        "Mercedes C Class SW Auto",
        "Mercedes E Class Auto",
        "Mercedes E Class SW Auto",
        "BMW 5 Series SW Auto",
        "BMW X1 Auto",
        "Mercedes CLE Coupe Auto",
        "Volkswagen T-Roc Cabrio",
        "Mercedes GLA Auto",
        "Volvo XC60 Auto",
        "Volvo EX30 Auto",
        "BMW 3 Series Auto",
        "Volvo V60 4x4 Auto",
        "Hybrid",
        "Mazda MX5 Cabrio Auto",
        "Mercedes CLA Auto",
    ]

    def _norm_text(s: str) -> str:
        s = (s or "").strip().lower()
        # remove duplicate spaces and commas spacing
        s = " ".join(s.replace(",", " ").split())
        return s

    _blocked_norm = set(_norm_text(x) for x in _blocked_models)

    def _is_blocked_model(name: str) -> bool:
        n = _norm_text(name)
        if not n:
            return False
        if n in _blocked_norm:
            return True
        # Regex-based strong match on key model families and powertrains
        patterns = [
            r"\bmercedes\s+s\s*class\b",
            r"\bmercedes\s+cla\b",
            r"\bmercedes\s+cle\b",
            r"\bmercedes\s+a\s*class\b",
            r"\bmercedes\s+c\s*class\b",
            r"\bmercedes\s+e\s*class\b",
            r"\bmercedes\s+gla\b",
            r"\bbmw\s+1\s*series\b",
            r"\bbmw\s+2\s*series\b",
            r"\bbmw\s+3\s*series\b",
            r"\bbmw\s+5\s*series\b",
            r"\bbmw\s*x1\b",
            r"\bvolvo\s+v60\b",
            r"\bvolvo\s+xc40\b",
            r"\bvolvo\s+xc60\b",
            r"\bvolvo\s+ex30\b",
            r"\btesla\s+model\s*3\b",
            r"\bmg\s+zs\b",
            r"\bmazda\s+mx5\b",
            r"\bvolkswagen\s+t-roc\b",
            r"\belectric\b",
            r"\bhybrid\b",
        ]
        import re as _re
        for p in patterns:
            if _re.search(p, n):
                return True
        # also check if any blocked long phrase is contained in name
        for b in _blocked_norm:
            if len(b) >= 6 and b in n:
                return True
        return False

    # --- Photo cache helpers (SQLite) ---
    def _photo_db_path() -> str:
        try:
            from pathlib import Path
            return str((Path(__file__).resolve().parent / "car_images.db"))
        except Exception:
            return "car_images.db"

    def _get_conn():
        try:
            import sqlite3
            return sqlite3.connect(_photo_db_path())
        except Exception:
            return None

    def _init_photos_table():
        conn = _get_conn()
        if not conn:
            return
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS car_images (
                    model_key TEXT PRIMARY KEY,
                    photo_url TEXT,
                    updated_at TEXT
                )
                """
            )
            conn.commit()
        except Exception:
            pass
        finally:
            try:
                conn.close()
            except Exception:
                pass
            # FINAL SAFEGUARD: If Clio wagon fell into D/E2, flip to J2/L2
            try:
                _nm = (car_name or '').lower()
                _txt_final = ''
                try:
                    _txt_final = card.get_text(' ', strip=True).lower()
                except Exception:
                    _txt_final = ''
                if re.search(r"\brenault\s*clio\b", _nm) and re.search(r"\b(sw|st|sport\s*tourer|tourer|break|estate|kombi|grandtour|grand\s*tour|sporter|wagon)\b", _nm):
                    if _is_auto_flag(_nm, _txt_final, transmission_label):
                        category = 'Station Wagon Automatic'
                    else:
                        category = 'Estate/Station Wagon'
            except Exception:
                pass

    def _normalize_model_key(name: str) -> str:
        s = (name or "").strip().lower()
        for w in ("suv", "economy", "mini", "estate", "station wagon", "premium", "7 seater", "9 seater"):
            if s.endswith(" " + w):
                s = s[: -len(w) - 1].strip()
        s = " ".join(s.split())
        return s

    def _cache_get_photo(key: str) -> str:
        conn = _get_conn()
        if not conn:
            return ""
        try:
            cur = conn.execute("SELECT photo_url FROM car_images WHERE model_key = ?", (key,))
            row = cur.fetchone()
            return row[0] if row and row[0] else ""
        except Exception:
            return ""
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def _cache_set_photo(key: str, url: str):
        if not (key and url):
            return
        _init_photos_table()
        conn = _get_conn()
        if not conn:
            return
        try:
            from datetime import datetime as _dt
            conn.execute(
                "INSERT INTO car_images (model_key, photo_url, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(model_key) DO UPDATE SET photo_url=excluded.photo_url, updated_at=excluded.updated_at",
                (key, url, _dt.utcnow().isoformat(timespec="seconds"))
            )
            conn.commit()
        except Exception:
            pass
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def map_grupo(grupo: str) -> str:
        if not grupo:
            return ""
        g = str(grupo).upper()
        # N-codes examples
        if g.startswith("N"):
            if g == "N07":
                return "7 Seater"
            if g.startswith("N09") or g == "N9" or g == "N90" or g == "N099":
                return "9 Seater"
            return "People Carrier"
        # S-codes: estate/station wagon
        if g.startswith("S"):
            return "Estate/Station Wagon"
        # A-codes: automatic variants; infer base from page context
        if g.startswith("A"):
            txt = _page_text
            if any(k in txt for k in ("estate", "station wagon", "estatecars", "carrinha")):
                return "Estate/Station Wagon"
            if "suv" in txt:
                return "SUV"
            if any(k in txt for k in ("7 lugares", "7 seats", "7 seater")):
                return "7 Seater"
            if any(k in txt for k in ("9 lugares", "9 seats", "9 seater")):
                return "9 Seater"
            if any(k in txt for k in ("mini", "pequeno")):
                return "Mini"
            if any(k in txt for k in ("economy", "económico", "economico")):
                return "Economy"
            # Fallback: treat as Economy automatic if no context hints
            return "Economy"
        # F/M codes frequently used for SUVs in provided samples
        if g.startswith("F"):
            return "SUV"
        if g.startswith("M"):
            # People carriers: infer 7 vs 9 seater from page text
            txt = _page_text
            if any(k in txt for k in ("9 lugares", "9 seats", "9 seater")):
                return "9 Seater"
            return "7 Seater"
        # Premium families observed as J/L in samples
        if g.startswith("J"):
            return "Premium"
        if g.startswith("L"):
            return "Premium"
        # C-codes numeric mapping
        if g.startswith("C"):
            try:
                n = int(g[1:])
            except Exception:
                return g
            if 1 <= n <= 4:
                return "Mini"
            if 5 <= n <= 9:
                return "Economy"
            if 10 <= n <= 19:
                return "Compact"
            if 20 <= n <= 29:
                return "Intermediate"
            if 30 <= n <= 39:
                return "Standard"
            if 40 <= n <= 49:
                return "Full-size"
            if 60 <= n <= 69:
                return "SUV"
            return g
        return g

    # Transmission label from global radio (if present)
    transmission_label = ""
    try:
        t_inp = soup.select_one("input[name='frmTrans'][checked]")
        if t_inp and t_inp.has_attr("value"):
            v = (t_inp.get("value") or "").lower()
            if v == "au":
                transmission_label = "Automatic"
            elif v == "mn":
                transmission_label = "Manual"
            elif v == "el":
                transmission_label = "Electric"
    except Exception:
        pass
    # Fallback: infer from 'Filtros utilizados anteriormente' section
    if not transmission_label:
        try:
            used = soup.select_one("#filterUsed")
            if used:
                txt = used.get_text(" ", strip=True).lower()
                if "autom" in txt:
                    transmission_label = "Automatic"
                elif "manual" in txt:
                    transmission_label = "Manual"
                elif "electr" in txt:
                    transmission_label = "Electric"
        except Exception:
            pass

    # Fast path for CarJet: collect provider summaries but do not return early; we'll prefer detailed items
    summary_items: List[Dict[str, Any]] = []
    try:
        # 0) Generic object matcher as a fallback to capture provider blobs even if array/var name changes
        raw_objs = OBJ_RX.findall(html)
        if raw_objs:
            import json as _json
            supplier_alias = {
                "AUP": "Auto Prudente Rent a Car",
                "SXT": "Sixt",
                "ECR": "Europcar",
                "KED": "Keddy by Europcar",
                "EPI": "EPI",
                "ALM": "Alamo",
                "AVX": "Avis",
                "BGX": "Budget",
                "ENT": "Enterprise",
                "DTG": "Dollar",
                "FLZ": "Flizzr",
                "DTG1": "Rentacar",
                "DGT1": "Rentacar",
                "EU2": "Goldcar Non-Refundable",
                "EUR": "Goldcar",
                "EUK": "Goldcar Key'n Go",
                "GMO": "Green Motion",
                "GMO1": "Green Motion",
                "SAD": "Drivalia",
                "DOH": "Drive on Holidays",
                "D4F": "Drive4Fun",
                "DVM": "Drive4Move",
                "CAE": "Cael",
                "CEN": "Centauro",
                "ABB": "Abbycar",
                "ABB1": "Abbycar Non-Refundable",
                "BSD": "Best Deal",
                "ATR": "Autorent",
                "AUU": "Auto Union",
                "THR": "Thrifty",
                "HER": "Hertz",
                "LOC": "Million",
            }
            idx = 0
            for s in raw_objs:
                try:
                    d = _json.loads(s)
                except Exception:
                    continue
                price_text = d.get("priceStr") or ""
                if not price_text:
                    continue
                supplier_code = (d.get("id") or "").strip()
                supplier = supplier_alias.get(supplier_code, supplier_code)
                grupo = d.get("grupoVeh") or ""
                category_h = map_grupo(grupo)
                display_category = category_h or grupo
                if transmission_label == "Automatic":
                    if display_category in ("Mini", "Economy", "SUV", "Estate/Station Wagon", "7 Seater"):
                        if display_category == "Estate/Station Wagon":
                            display_category = "Station Wagon Automatic"
                        elif display_category == "7 Seater":
                            display_category = "7 Seater Automatic"
                        else:
                            display_category = f"{display_category} Automatic"
                # Best-effort photo from grupoVeh code
                photo_url = ""
                try:
                    if grupo:
                        photo_url = urljoin(base_url, f"/cdn/img/cars/S/car_{grupo}.jpg")
                except Exception:
                    photo_url = ""
                summary_items.append({
                    "id": idx,
                    "car": "",
                    "supplier": supplier,
                    "price": price_text,
                    "currency": "",
                    "category": display_category,
                    "category_code": grupo,
                    "transmission": transmission_label,
                    "photo": photo_url,
                    "link": base_url,
                })
                idx += 1
            # do not return yet; prefer detailed rows

        m = DATAMAP_RX.search(html)
        if m:
            import json
            arr = json.loads(m.group(1))
            supplier_alias = {
                "AUP": "Auto Prudente Rent a Car",
                "SXT": "Sixt",
                "ECR": "Europcar",
                "KED": "Keddy by Europcar",
                "EPI": "EPI",
                "ALM": "Alamo",
                "AVX": "Avis",
                "BGX": "Budget",
                "ENT": "Enterprise",
                "DTG": "Dollar",
                "FLZ": "Flizzr",
                "EU2": "Goldcar Non-Refundable",
                "EUR": "Goldcar",
                "EUK": "Goldcar Key'n Go",
                "GMO": "Green Motion",
                "GMO1": "Green Motion",
                "SAD": "Drivalia",
                "DOH": "Drive on Holidays",
                "D4F": "Drive4Fun",
                "DVM": "Drive4Move",
                "CAE": "Cael",
                "CEN": "Centauro",
                "ABB": "Abbycar",
                "ABB1": "Abbycar Non-Refundable",
                "BSD": "Best Deal",
                "ATR": "Autorent",
                "AUU": "Auto Union",
            }
            idx = 0
            for it in arr:
                supplier_code = (it.get("id") or "").strip()
                # Additional inline overrides
                if supplier_code in ("DTG1", "DGT1"):
                    supplier = "Rentacar"
                else:
                    supplier = supplier_alias.get(supplier_code, supplier_code)
                price_text = it.get("priceStr") or ""
                if not price_text:
                    continue
                grupo = it.get("grupoVeh") or ""
                category_h = map_grupo(grupo)
                display_category = category_h or grupo
                if transmission_label == "Automatic":
                    if display_category in ("Mini", "Economy", "SUV", "Estate/Station Wagon", "7 Seater"):
                        if display_category == "Estate/Station Wagon":
                            display_category = "Station Wagon Automatic"
                        elif display_category == "7 Seater":
                            display_category = "7 Seater Automatic"
                        else:
                            display_category = f"{display_category} Automatic"
                summary_items.append({
                    "id": idx,
                    "car": "",
                    "supplier": supplier,
                    "price": price_text,
                    "currency": "",
                    "category": display_category,
                    "category_code": grupo,
                    "transmission": transmission_label,
                    "link": base_url,
                })
                idx += 1
            # do not return yet; prefer detailed rows
    except Exception:
        pass

    # Pass 2: try to parse explicit car cards/rows from the HTML (preferred over regex)
    try:
        cards = soup.select("section.newcarlist article, .newcarlist article, article.car, li.result, li.car, .car-item, .result-row")
        idx = 0
        for card in cards:
            # price (broaden selectors and do not require explicit currency symbol)
            let_price = card.select_one(".price, .amount, [class*='price'], .nfoPriceDest, .nfoPrice, [data-price]")
            price_text = (let_price.get_text(strip=True) if let_price else "") or (card.get("data-price") or "")
            if not price_text:
                continue
            # car/model
            name_el = card.select_one(
                ".veh-name, .vehicle-name, .model, .titleCar, .title, h3, h2, [class*='veh-name'], [class*='vehicle-name'], [class*='model']"
            )
            car_name = name_el.get_text(strip=True) if name_el else ""
            if not car_name:
                # try common data attributes
                for attr in ("data-model", "data-vehicle", "data-name", "aria-label", "title"):
                    v = (card.get(attr) or "").strip()
                    if v:
                        car_name = v
                        break
            # supplier: try to extract provider code from logo_XXX.* in img src, then map via alias
            supplier = ""
            try:
                supplier_alias = {
                    "AUP": "Auto Prudente Rent a Car",
                    "SXT": "Sixt",
                    "ECR": "Europcar",
                    "KED": "Keddy by Europcar",
                    "EPI": "EPI",
                    "ALM": "Alamo",
                    "AVX": "Avis",
                    "BGX": "Budget",
                    "ENT": "Enterprise",
                    "DTG": "Dollar",
                    "DTG1": "Rentacar",
                    "DGT1": "Rentacar",
                    "FLZ": "Flizzr",
                    "EU2": "Goldcar Non-Refundable",
                    "EUR": "Goldcar",
                    "EUK": "Goldcar Key'n Go",
                    "GMO": "Green Motion",
                    "GMO1": "Green Motion",
                    "SAD": "Drivalia",
                    "DOH": "Drive on Holidays",
                    "D4F": "Drive4Fun",
                    "DVM": "Drive4Move",
                    "CAE": "Cael",
                    "CEN": "Centauro",
                    "ABB": "Abbycar",
                    "ABB1": "Abbycar Non-Refundable",
                    "BSD": "Best Deal",
                    "ATR": "Autorent",
                    "AUU": "Auto Union",
                    "THR": "Thrifty",
                    "HER": "Hertz",
                    "LOC": "Million",
                }
                code = ""
                for im in card.select("img[src]"):
                    src = im.get("src") or ""
                    mcode = LOGO_CODE_RX.search(src)
                    if mcode:
                        code = (mcode.group(1) or "").upper()
                        break
                if code:
                    supplier = supplier_alias.get(code, code)
                if not supplier:
                    # textual fallback but avoid using car name
                    supplier_el = card.select_one(".supplier, .vendor, .partner, [class*='supplier'], [class*='vendor']")
                    txt = supplier_el.get_text(strip=True) if supplier_el else ""
                    if txt and txt.lower() != (car_name or "").lower():
                        supplier = txt
            except Exception:
                pass
            # photo: pick an image that is not a provider logo
            photo = ""
            try:
                # prefer <picture> sources
                picture_src = None
                for src_el in card.select("picture source[srcset], img[srcset], picture source[data-srcset], img[data-srcset]"):
                    sset = (src_el.get("srcset") or src_el.get("data-srcset") or "").strip()
                    if sset:
                        # pick the first candidate (split by comma for multiple entries, then URL before whitespace)
                        first_entry = sset.split(',')[0].strip()
                        picture_src = first_entry.split()[0]
                        if picture_src:
                            break
                imgs = card.select("img")
                for im in imgs:
                    src = picture_src or (
                        im.get("src") or im.get("data-src") or im.get("data-original") or im.get("data-lazy") or im.get("data-lazy-src") or ""
                    ).strip()
                    if not src:
                        continue
                    # skip logos and icons
                    if re.search(r"logo_", src, re.I):
                        continue
                    if src.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.gif')):
                        # make absolute if needed
                        try:
                            from urllib.parse import urljoin
                            photo = urljoin(base_url, src)
                        except Exception:
                            photo = src
                        # use alt/title as car_name fallback
                        if not car_name:
                            alt_t = (im.get("alt") or im.get("title") or "").strip()
                            if alt_t:
                                car_name = alt_t
                        break
                # Also check inline background-image on card and descendants
                if not photo:
                    style_el = card.get("style") or ""
                    m_bg = BG_IMAGE_RX.search(style_el)
                    if m_bg:
                        raw = m_bg.group(1).strip().strip('\"\'')
                        try:
                            from urllib.parse import urljoin
                            photo = urljoin(base_url, f"/img?src={raw}")
                        except Exception:
                            photo = f"/img?src={raw}"
                if not photo:
                    for child in card.find_all(True):
                        st = child.get("style") or ""
                        m2 = BG_IMAGE_RX.search(st)
                        if m2:
                            raw = m2.group(1).strip().strip('\"\'')
                            try:
                                from urllib.parse import urljoin
                                photo = urljoin(base_url, f"/img?src={raw}")
                            except Exception:
                                photo = f"/img?src={raw}"
                            if photo:
                                break
                # As a final fallback, synthesize from any car_[gV].jpg reference inside this card
                if not photo:
                    html_block = str(card)
                    m_car = CAR_CODE_RX.search(html_block)
                    if m_car:
                        code = m_car.group(1)
                        try:
                            from urllib.parse import urljoin
                            photo = urljoin(base_url, f"/cdn/img/cars/S/car_{code}.jpg")
                        except Exception:
                            photo = f"/cdn/img/cars/S/car_{code}.jpg"
            except Exception:
                pass
            # category
            cat_el = card.select_one(".category, .group, .vehicle-category, [class*='category'], [class*='group'], [class*='categoria'], [class*='grupo']")
            category = cat_el.get_text(strip=True) if cat_el else ""
            # Canonicalize category to expected groups
            def _canon(cat: str) -> str:
                c = (cat or "").strip().lower()
                if not c:
                    return ""
                if "estate" in c or "station" in c or "carrinha" in c:
                    return "Estate/Station Wagon"
                if "suv" in c:
                    return "SUV"
                if "premium" in c or "lux" in c:
                    return "Premium"
                if "7" in c and ("lugar" in c or "lugares" in c or "seater" in c or "seats" in c):
                    return "7 Seater"
                if "9" in c and ("lugar" in c or "lugares" in c or "seater" in c or "seats" in c):
                    return "9 Seater"
                if "econom" in c:
                    return "Economy"
                if "mini" in c or "small" in c or "pequeno" in c:
                    return "Mini"
                return cat
            category = _canon(category)
            if not category:
                # Infer from CARD context if label missing to avoid page-wide bias
                try:
                    local_txt = card.get_text(" ", strip=True).lower()
                except Exception:
                    local_txt = ""
                if any(k in local_txt for k in ("estate", "station wagon", "estatecars", "carrinha")):
                    category = "Estate/Station Wagon"
                elif "suv" in local_txt:
                    category = "SUV"
                elif any(k in local_txt for k in ("7 lugares", "7 seats", "7 seater")):
                    category = "7 Seater"
                elif any(k in local_txt for k in ("9 lugares", "9 seats", "9 seater")):
                    category = "9 Seater"
                elif any(k in local_txt for k in ("mini", "pequeno")):
                    category = "Mini"
                elif any(k in local_txt for k in ("economy", "económico", "economico")):
                    category = "Economy"
                # As a last resort, try to infer from car name trailing token
                if not category and car_name:
                    tail = (car_name.split()[-1] or "").lower()
                    tail_map = {
                        "suv": "SUV",
                        "economy": "Economy",
                        "mini": "Mini",
                        "wagon": "Estate/Station Wagon",
                        "estate": "Estate/Station Wagon",
                        "premium": "Premium",
                        "7": "7 Seater",
                        "7-seater": "7 Seater",
                        "9": "9 Seater",
                        "9-seater": "9 Seater",
                    }
                    category = tail_map.get(tail, category)
            # If car_name still empty, heuristically derive from local text by removing category tokens and prices
            if not car_name:
                try:
                    local_txt_full = card.get_text(" \n", strip=True)
                    lines = [l.strip() for l in local_txt_full.split("\n") if l.strip()]
                    # remove lines that are price-like
                    price_like = re.compile(r"(€|EUR|GBP|\£|\d+[\.,]\d{2})", re.I)
                    candidates = [l for l in lines if not price_like.search(l)]
                    if candidates:
                        car_name = candidates[0]
                        # strip trailing category word if present
                        if category and car_name.lower().endswith(category.lower()):
                            car_name = car_name[: -len(category)].strip()
                except Exception:
                    pass
            # Fiat 500 Cabrio -> Group G (Premium)
            try:
                _cn_lower = (car_name or "").lower()
                if re.search(r"\bfiat\s*500\b.*\b(cabrio|convertible|cabriolet)\b", _cn_lower):
                    category = "Premium"
            except Exception:
                pass
            # Mini cabrio variants -> Group G (Premium)
            try:
                _cn_lower = (car_name or "").lower()
                if re.search(r"\bmini\s+(one|cooper)\b.*\b(cabrio|convertible|cabriolet)\b", _cn_lower):
                    category = "Premium"
            except Exception:
                pass
            # Specific model mappings to requested groups
            try:
                cn = (car_name or "").lower()
                # Mini Countryman (incl. Cooper Countryman): E2 if Auto, else D (Economy)
                if re.search(r"\bmini\s+(cooper\s+)?countryman\b", cn):
                    if _is_auto_flag(cn, _page_text, transmission_label):
                        category = "Economy Automatic"
                    else:
                        category = "Economy"
                # Peugeot 108 Cabrio -> G (Premium)
                if re.search(r"\bpeugeot\s*108\b.*\b(cabrio|convertible|cabriolet)\b", cn):
                    category = "Premium"
                # Fiat 500 Auto -> E1 (Mini Automatic) unless Cabrio already handled
                if re.search(r"\bfiat\s*500\b.*\b(auto|automatic)\b", cn) and not re.search(r"\b(cabrio|convertible|cabriolet)\b", cn):
                    category = "Mini Automatic"
                # Citroen C3 Auto -> E2 (Economy Automatic)
                if re.search(r"\bcitro[eë]n\s*c3\b.*\b(auto|automatic)\b", cn) and not re.search(r"\bc3\s*aircross\b", cn):
                    category = "Economy Automatic"
                # Citroen C3 (non-Aircross, non-Auto) -> D (Economy)
                if re.search(r"\bcitro[eë]n\s*c3\b", cn) and not re.search(r"\b(auto|automatic)\b", cn) and not re.search(r"\bc3\s*aircross\b", cn):
                    category = "Economy"
                # Citroen C3 Aircross Auto -> L1 (SUV Automatic)
                if re.search(r"\bcitro[eë]n\s*c3\s*aircross\b.*\b(auto|automatic)\b", cn):
                    category = "SUV Automatic"
                # Toyota Aygo X -> F (SUV)
                if re.search(r"\btoyota\s*aygo\s*x\b", cn):
                    category = "SUV"
                # Fiat 500L -> J1 (Crossover)
                if re.search(r"\bfiat\s*500l\b", cn):
                    category = "Crossover"
                # Renault Clio SW/estate variants -> J2 (Estate/Station Wagon); autos will be L2 via suffix
                if re.search(r"\brenault\s*clio\b", cn) and re.search(r"\b(sw|st|sport\s*tourer|tourer|break|estate|kombi|grandtour|grand\s*tour|sporter|wagon)\b", cn):
                    category = "Estate/Station Wagon"
                # Group J1 (Crossover) models
                j1_patterns = [
                    r"\bkia\s*sportage\b",
                    r"\bnissan\s*qashqai\b",
                    r"\b(skoda|škoda)\s*kamiq\b",
                    r"\bhyundai\s*tucson\b",
                    r"\bseat\s*ateca\b",
                    r"\bmazda\s*cx[- ]?3\b",
                    r"\bpeugeot\s*5008\b",
                    r"\bpeugeot\s*3008\b",
                    r"\bpeugeot\s*2008\b",
                    r"\brenault\s*austral\b",
                    r"\btoyota\s*hilux\b.*\b4x4\b",
                ]
                if any(re.search(p, cn) for p in j1_patterns):
                    category = "Crossover"
                # Peugeot 308 base -> J1; 308 SW: Auto -> L2, else J2
                if re.search(r"\bpeugeot\s*308\b", cn):
                    if re.search(r"\bsw\b", cn):
                        if _is_auto_flag(cn, _page_text, transmission_label):
                            category = "Station Wagon Automatic"
                        else:
                            category = "Estate/Station Wagon"
                    else:
                        category = "Crossover"
                # VW Golf SW/Variant: Auto -> L2, else J2
                if re.search(r"\b(vw|volkswagen)\s*golf\b", cn) and re.search(r"\b(sw|variant)\b", cn):
                    if _is_auto_flag(cn, _page_text, transmission_label):
                        category = "Station Wagon Automatic"
                    else:
                        category = "Estate/Station Wagon"
                # VW Passat: base & Variant -> J2; Auto -> L2
                if re.search(r"\b(vw|volkswagen)\s*passat\b", cn):
                    if _is_auto_flag(cn, _page_text, transmission_label):
                        category = "Station Wagon Automatic"
                    else:
                        category = "Estate/Station Wagon"
                # Seat Leon SW/ST/Variant/Estate: Auto -> L2, else J2
                if re.search(r"\bseat\s*leon\b", cn) and re.search(r"\b(sw|st|variant|sport\s*tourer|sportstourer|estate)\b", cn):
                    if _is_auto_flag(cn, _page_text, transmission_label):
                        category = "Station Wagon Automatic"
                    else:
                        category = "Estate/Station Wagon"
                # Skoda Scala: base -> J2; Auto -> L2
                if re.search(r"\b(skoda|škoda)\s*scala\b", cn):
                    if _is_auto_flag(cn, _page_text, transmission_label):
                        category = "Station Wagon Automatic"
                    else:
                        category = "Estate/Station Wagon"
                # Seat Arona -> F (SUV) regardless of transmission
                if re.search(r"\bseat\s*arona\b", cn):
                    category = "SUV"
                # Hyundai Kona/Kauai -> F (SUV) regardless of transmission
                if re.search(r"\bhyundai\s*(kona|kauai)\b", cn):
                    category = "SUV"
                # Skoda Octavia -> J2 (Station Wagon)
                if re.search(r"\b(skoda|škoda)\s*octavia\b", cn):
                    category = "Estate/Station Wagon"
                # Toyota Corolla SW/TS/Touring Sports: Auto -> L2 else J2
                if re.search(r"\btoyota\s*corolla\b", cn) and re.search(r"\b(sw|ts|touring\s*sports?|sport\s*touring|estate|wagon)\b", cn):
                    if _is_auto_flag(cn, _page_text, transmission_label):
                        category = "Station Wagon Automatic"
                    else:
                        category = "Estate/Station Wagon"
                # Toyota Corolla base (non-wagon) Auto -> E2
                if re.search(r"\btoyota\s*corolla\b", cn) and not re.search(r"\b(sw|ts|touring\s*sports?|sport\s*touring|estate|wagon)\b", cn):
                    if _is_auto_flag(cn, _page_text, transmission_label):
                        category = "Economy Automatic"
                # Peugeot 508 -> J2; Auto -> L2 (Station Wagon Automatic)
                if re.search(r"\bpeugeot\s*508\b", cn):
                    if _is_auto_flag(cn, _page_text, transmission_label):
                        category = "Station Wagon Automatic"
                    else:
                        category = "Estate/Station Wagon"
                # Hyundai i30 -> J2; Auto -> L2
                if re.search(r"\bhyundai\s*i30\b", cn):
                    if _is_auto_flag(cn, _page_text, transmission_label):
                        category = "Station Wagon Automatic"
                    else:
                        category = "Estate/Station Wagon"
                # Cupra Formentor Auto -> L1
                if re.search(r"\bcupra\s*formentor\b", cn) and _is_auto_flag(cn, _page_text, transmission_label):
                    category = "SUV Automatic"
                # Renault Megane Sedan Auto -> L2
                if re.search(r"\brenault\s*megane\b", cn) and re.search(r"\bsedan\b", cn) and _is_auto_flag(cn, _page_text, transmission_label):
                    category = "Station Wagon Automatic"
                # Renault Megane SW/Estate/Wagon: J2; Auto -> L2
                if re.search(r"\brenault\s*megane\b", cn) and re.search(r"\b(sw|estate|wagon|sport\s*tourer|sport\s*tourismo|tourer)\b", cn):
                    if _is_auto_flag(cn, _page_text, transmission_label):
                        category = "Station Wagon Automatic"
                    else:
                        category = "Estate/Station Wagon"
                # Cupra Leon SW Auto -> L2
                if re.search(r"\bcupra\s*leon\b", cn) and re.search(r"\b(sw|st|sport\s*tourer|sportstourer|estate|variant)\b", cn) and _is_auto_flag(cn, _page_text, transmission_label):
                    category = "Station Wagon Automatic"
                # Toyota Yaris Cross Auto -> L1
                if re.search(r"\btoyota\s*yaris\s*cross\b", cn) and _is_auto_flag(cn, _page_text, transmission_label):
                    category = "SUV Automatic"
                # Nissan Juke -> F (SUV) regardless of transmission
                if re.search(r"\bnissan\s*juke\b", cn):
                    category = "SUV"
                # Toyota Yaris Auto -> E1
                if re.search(r"\btoyota\s*yaris\b", cn) and _is_auto_flag(cn, _page_text, transmission_label):
                    category = "Mini Automatic"
                # Kia Picanto Auto -> E1
                if re.search(r"\bkia\s*picanto\b", cn) and _is_auto_flag(cn, _page_text, transmission_label):
                    category = "Mini Automatic"
                # VW Taigo -> F (SUV) regardless of transmission
                if re.search(r"\b(vw|volkswagen)\s*taigo\b", cn):
                    category = "SUV"
                # Mitsubishi Spacestar Auto -> E1
                if re.search(r"\bmitsubishi\s*space\s*star|spacestar\b", cn) and _is_auto_flag(cn, _page_text, transmission_label):
                    category = "Mini Automatic"
                # Renault Megane Auto -> E2 (use card-level text)
                if re.search(r"\brenault\s*megane\b", cn):
                    _ct = ""
                    try:
                        _ct = card.get_text(" ", strip=True).lower()
                    except Exception:
                        _ct = ""
                    if _is_auto_flag(cn, _ct, transmission_label):
                        category = "Economy Automatic"
                # Ford Puma -> F (SUV) regardless of transmission
                if re.search(r"\bford\s*puma\b", cn):
                    category = "SUV"
                # Citroen C5 Aircross Auto -> L1
                if re.search(r"\bcitro[eë]n\s*c5\s*aircross\b", cn) and _is_auto_flag(cn, _page_text, transmission_label):
                    category = "SUV Automatic"
                # Toyota C-HR Auto -> L1
                if re.search(r"\btoyota\s*c[-\s]?hr\b|\btoyota\s*chr\b", cn) and _is_auto_flag(cn, _page_text, transmission_label):
                    category = "SUV Automatic"
                # Kia Stonic -> F (SUV) regardless of transmission
                if re.search(r"\bkia\s*stonic\b", cn):
                    category = "SUV"
                # Ford EcoSport -> F (SUV) regardless of transmission
                if re.search(r"\bford\s*eco\s*sport\b|\bford\s*ecosport\b", cn):
                    category = "SUV"
                # Opel/Vauxhall Crossland X -> F (SUV); Auto remains L1 via final if needed
                if re.search(r"\b(opel|vauxhall)\s*crossland\s*x?\b", cn):
                    category = "SUV"
                # Ford Focus SW/Estate/Wagon variants: J2; Auto -> L2
                if re.search(r"\bford\s*focus\b", cn) and re.search(r"\b(sw|estate|wagon|turnier|kombi|sportbreak|sport\s*brake|tourer|touring)\b", cn):
                    if _is_auto_flag(cn, _page_text, transmission_label):
                        category = "Station Wagon Automatic"
                    else:
                        category = "Estate/Station Wagon"
                # Ford Focus base (non-wagon): D or E2
                if re.search(r"\bford\s*focus\b", cn) and not re.search(r"\b(sw|estate|wagon)\b", cn):
                    if _is_auto_flag(cn, _page_text, transmission_label):
                        category = "Economy Automatic"
                    else:
                        category = "Economy"
                # Seat Leon base (non-wagon): D or E2 (use card-level text)
                if re.search(r"\bseat\s*leon\b", cn) and not re.search(r"\b(sw|st|variant|sport\s*tourer|sportstourer|estate|wagon)\b", cn):
                    _ct = ""
                    try:
                        _ct = card.get_text(" ", strip=True).lower()
                    except Exception:
                        _ct = ""
                    if _is_auto_flag(cn, _ct, transmission_label):
                        category = "Economy Automatic"
                    else:
                        category = "Economy"
                # Kia Ceed base (non-wagon): D or E2
                if re.search(r"\bkia\s*ceed\b", cn) and not re.search(r"\b(sw|estate|wagon|sportswagon|sports\s*wagon)\b", cn):
                    if _is_auto_flag(cn, _page_text, transmission_label):
                        category = "Economy Automatic"
                    else:
                        category = "Economy"
                # Opel/Vauxhall Astra: base & SW -> J2; Auto -> L2
                if re.search(r"\b(opel|vauxhall)\s*astra\b", cn):
                    if _is_auto_flag(cn, _page_text, transmission_label):
                        category = "Station Wagon Automatic"
                    else:
                        category = "Estate/Station Wagon"
                # VW T-Cross Auto -> L1 (unchanged)
                if re.search(r"\b(vw|volkswagen)\s*t[-\s]?cross\b", cn) and _is_auto_flag(cn, _page_text, transmission_label):
                    category = "SUV Automatic"
                # VW Golf Auto (hatch) -> E2 (use card-level text)
                if re.search(r"\b(vw|volkswagen)\s*golf\b", cn) and not re.search(r"\b(sw|variant|estate|wagon)\b", cn):
                    _ct = ""
                    try:
                        _ct = card.get_text(" ", strip=True).lower()
                    except Exception:
                        _ct = ""
                    if _is_auto_flag(cn, _ct, transmission_label):
                        category = "Economy Automatic"
                # Dacia Jogger -> M1 (7 Seater); automatic will auto-suffix to M2 later
                if re.search(r"\bdacia\s*jogger\b", cn):
                    category = "7 Seater"
                # Fiat 500X -> J1 (Crossover); Auto -> L1
                if re.search(r"\bfiat\s*500x\b", cn):
                    if _is_auto_flag(cn, _page_text, transmission_label):
                        category = "SUV Automatic"
                    else:
                        category = "Crossover"
                # VW Beetle Cabrio -> G (Premium)
                if re.search(r"\b(vw|volkswagen)\s*beetle\b.*\b(cabrio|convertible|cabriolet)\b", cn):
                    category = "Premium"
                # Group L1 (SUV Automatic) for specific models when Automatic is detected (including acronyms)
                try:
                    _card_txt = ""
                    try:
                        _card_txt = card.get_text(" ", strip=True).lower()
                    except Exception:
                        _card_txt = ""
                    is_auto = _is_auto_flag(cn, _card_txt, transmission_label)
                    # Only keep intended L1 autos; others remain F per latest rules
                    is_l1_model = (
                        re.search(r"\bpeugeot\s*(3008|2008|5008)\b", cn) or
                        re.search(r"\bnissan\s*qashqai\b", cn) or
                        re.search(r"\b(skoda|škoda)\s*kamiq\b", cn) or
                        re.search(r"\bcitro[eë]n\s*c4\b", cn) or
                        re.search(r"\b(vw|volkswagen)\s*tiguan\b", cn) or
                        re.search(r"\bds(\s*automobiles)?\s*4\b", cn) or
                        re.search(r"\b(skoda|škoda)\s*karoq\b", cn) or
                        re.search(r"\bford\s*kuga\b", cn) or
                        re.search(r"\bjeep\s*renegade\b", cn) or
                        re.search(r"\brenault\s*arkana\b", cn) or
                        re.search(r"\btoyota\s*rav\s*4\b|\brav4\b", cn) or
                        re.search(r"\bcupra\s*formentor\b", cn) or
                        re.search(r"\btoyota\s*yaris\s*cross\b", cn) or
                        re.search(r"\bcitro[eë]n\s*c5\s*aircross\b", cn) or
                        re.search(r"\btoyota\s*c[-\s]?hr\b|\btoyota\s*chr\b", cn) or
                        re.search(r"\b(vw|volkswagen)\s*t[-\s]?cross\b", cn) or
                        re.search(r"\bfiat\s*500x\b", cn)
                    )
                    if is_auto and is_l1_model:
                        category = "SUV Automatic"
                except Exception:
                    pass
                # Citroen C4 Picasso (non-Grand) -> M1 (7 Seater). Auto will suffix to M2 later
                if re.search(r"\bcitro[eë]n\s*c4\s*picasso\b", cn) and not re.search(r"\bgrand\b", cn):
                    category = "7 Seater"
                # Citroen Grand C4 Picasso/Grand Spacetourer -> M1 base; auto will suffix to M2
                if re.search(r"\bcitro[eë]n\s*c4\s*(grand\s*picasso|grand\s*spacetourer|grand\s*space\s*tourer)\b", cn):
                    category = "7 Seater"
            except Exception:
                pass
            # Group D (Economy) models; Auto -> Economy Automatic (use card-level text for auto detection)
            d_models = [
                r"dacia\s+sandero",
                r"peugeot\s*208",
                r"opel\s*corsa",
                r"seat\s*ibiza",
                r"seat\s*leon",
                r"kia\s*ceed",
                r"(vw|volkswagen)\s*polo",
                r"renault\s*clio",
                r"ford\s*fiesta",
                r"ford\s*focus",
                r"hyundai\s*i20",
                r"nissan\s*micra",
                r"audi\s*a1",
            ]
            if any(re.search(p, cn) for p in d_models):
                _ct = ""
                try:
                    _ct = card.get_text(" ", strip=True).lower()
                except Exception:
                    _ct = ""
                if _is_auto_flag(cn, _ct, transmission_label):
                    category = "Economy Automatic"
                else:
                    category = "Economy"
            # Force B1 mapping for specific models the user provided (non-Auto/Non-Cabrio, base Mini only)
            try:
                _b1_models = [
                    "fiat 500", "peugeot 108", "opel adam",
                    "toyota aygo", "volkswagen up", "vw up", "ford ka", "renault twingo",
                    "citroen c1", "citroën c1", "kia picanto"
                ]
                _cn = (car_name or "").lower()
                if any(m in _cn for m in _b1_models):
                    # do not apply B1 if auto/automatic (multi-language/abbrev) or cabrio/convertible/cabriolet
                    if (not _is_auto_flag(_cn, _page_text, transmission_label)) and not re.search(r"\b(cabrio|convertible|cabriolet)\b", _cn, re.I):
                        # exclude variants that map elsewhere: 500X/500L, Aygo X, Aircross
                        if not re.search(r"\b(500x|500l|aygo\s*x|aircross|countryman)\b", _cn):
                            # and only when category is not already a non-Mini mapping
                            if category in ("", "Mini"):
                                category = "Mini 4 Doors"
            except Exception:
                pass
            # Refine Mini into 'Mini 4 Doors' when doors info is present
            try:
                if category == "Mini":
                    _lt = ""
                    try:
                        _lt = card.get_text(" ", strip=True).lower()
                    except Exception:
                        _lt = ""
                    _cn = (car_name or "").lower()
                    four_pat = re.compile(r"\b(4\s*(doors?|portas|p)|4p|4-door|4-portas)\b", re.I)
                    if four_pat.search(_lt) or four_pat.search(_cn):
                        category = "Mini 4 Doors"
            except Exception:
                pass
            # link
            link = url_from_row(card, base_url) or base_url
            # Photo cache: upsert or read from cache based on model key
            try:
                if car_name:
                    _key = _normalize_model_key(car_name)
                    if photo:
                        _cache_set_photo(_key, photo)
                    else:
                        cached_photo = _cache_get_photo(_key)
                        if cached_photo:
                            photo = cached_photo
            except Exception:
                pass
            # Crossover override when car name is present (exclude C4 Picasso/Grand Spacetourer)
            try:
                _car_lc = (car_name or "").lower()
                is_c4_picasso_like = re.search(r"\bc4\s*(picasso|grand\s*spacetourer|grand\s*space\s*tourer)\b", _car_lc)
                if re.search(r"\b(peugeot\s*2008|peugeot\s*3008|citro[eë]n\s*c4)\b", _car_lc, re.I) and not is_c4_picasso_like:
                    category = "Crossover"
            except Exception:
                pass
            # Automatic suffix for selected groups
            try:
                if transmission_label == "Automatic" and category in ("Mini", "Economy", "SUV", "Estate/Station Wagon", "7 Seater"):
                    if category == "Estate/Station Wagon":
                        category = "Station Wagon Automatic"
                    elif category == "7 Seater":
                        category = "7 Seater Automatic"
                    else:
                        category = f"{category} Automatic"
            except Exception:
                pass
            # FINAL OVERRIDE: Ensure Group D/E2 models are correctly placed (Peugeot 208, Opel Corsa, Seat Ibiza, VW Polo, Renault Clio, Ford Fiesta, Nissan Micra, Hyundai i20, Audi A1)
            try:
                cn2 = (car_name or "").lower()
                d_models_final = [
                    r"\bpeugeot\s*208\b",
                    r"\bopel\s*corsa\b",
                    r"\bseat\s*ibiza\b",
                    r"\bseat\s*leon\b",
                    r"\bkia\s*ceed\b",
                    r"\b(vw|volkswagen)\s*polo\b",
                    r"\bcitro[eë]n\s*c3\b",
                    r"\brenault\s*clio\b",
                    r"\bford\s*fiesta\b",
                    r"\bford\s*focus\b",
                    r"\bnissan\s*micra\b",
                    r"\bhyundai\s*i20\b",
                    r"\baudi\s*a1\b",
                    r"\bdacia\s*sandero\b",
                ]
                # do not override if we already mapped to protected groups (wagon/crossover/suv)
                is_protected = category in ("Estate/Station Wagon", "Station Wagon Automatic", "Crossover", "SUV", "SUV Automatic")
                if (not is_protected) and any(re.search(p, cn2) for p in d_models_final):
                    if _is_auto_flag(cn2, _txt, transmission_label):
                        category = "Economy Automatic"
                    else:
                        category = "Economy"
            except Exception:
                pass
            # FINAL MANUAL OVERRIDE for D models: if manual is explicit, force D
            try:
                cn2b = (car_name or "").lower()
                is_d_family = any(re.search(p, cn2b) for p in [
                    r"\bpeugeot\s*208\b", r"\bopel\s*corsa\b", r"\bseat\s*ibiza\b",
                    r"\bseat\s*leon\b", r"\b(vw|volkswagen)\s*golf\b", r"\b(vw|volkswagen)\s*polo\b",
                    r"\brenault\s*clio\b", r"\bford\s*fiesta\b", r"\bnissan\s*micra\b",
                    r"\bhyundai\s*i20\b", r"\baudi\s*a1\b", r"\bdacia\s*sandero\b", r"\brenault\s*megane\b",
                ])
                # re-evaluate card text for manual marker
                _txt2 = ""
                try:
                    _txt2 = card.get_text(" ", strip=True).lower()
                except Exception:
                    _txt2 = ""
                is_manual = (str(transmission_label or '').lower() == 'manual') or bool(re.search(r"\bmanual\b", _txt2))
                if is_d_family and is_manual and category not in ("Estate/Station Wagon", "Station Wagon Automatic"):
                    category = "Economy"
            except Exception:
                pass
            # FINAL L2/J2 OVERRIDE: enforce wagons to wagon groups; autos -> L2
            try:
                cnf = (car_name or "").lower()
                _txt = ""
                try:
                    _txt = card.get_text(" ", strip=True).lower()
                except Exception:
                    _txt = ""
                # Renault Clio SW: force to wagon groups
                if re.search(r"\brenault\s*clio\b", cnf) and re.search(r"\b(sw|st|sport\s*tourer|tourer|break|estate|kombi|grandtour|grand\s*tour|sporter|wagon)\b", cnf):
                    if _is_auto_flag(cnf, _txt, transmission_label):
                        category = "Station Wagon Automatic"
                    else:
                        category = "Estate/Station Wagon"
                cn3 = (car_name or "").lower()
                is_auto_any = _is_auto_flag(cn3, _txt, transmission_label)
                l1_model = (
                    re.search(r"\bpeugeot\s*(3008|2008|5008)\b", cn3) or
                    re.search(r"\bnissan\s*qashqai\b", cn3) or
                # ... (rest of the code remains the same)
                    re.search(r"\b(skoda|škoda)\s*kamiq\b", cn3) or
                    re.search(r"\bcitro[eë]n\s*c4\b", cn3) or
                    re.search(r"\b(vw|volkswagen)\s*tiguan\b", cn3) or
                    re.search(r"\bds(\s*automobiles)?\s*4\b", cn3) or
                    re.search(r"\b(skoda|škoda)\s*karoq\b", cn3) or
                    re.search(r"\bford\s*kuga\b", cn3) or
                    re.search(r"\bjeep\s*renegade\b", cn3) or
                    re.search(r"\brenault\s*arkana\b", cn3) or
                    re.search(r"\btoyota\s*rav\s*4\b|\brav4\b", cn3) or
                    re.search(r"\bcupra\s*formentor\b", cn3) or
                    re.search(r"\btoyota\s*yaris\s*cross\b", cn3) or
                    re.search(r"\bcitro[eë]n\s*c5\s*aircross\b", cn3) or
                    re.search(r"\btoyota\s*c[-\s]?hr\b|\btoyota\s*chr\b", cn3) or
                    re.search(r"\b(vw|volkswagen)\s*t[-\s]?cross\b", cn3) or
                    re.search(r"\bfiat\s*500x\b", cn3)
                )
                # don't override M2 or wagons
                is_m2 = category == "7 Seater Automatic" or re.search(r"\bc4\s*(picasso|grand\s*spacetourer|grand\s*space\s*tourer)\b", cn3)
                is_wagon = category in ("Estate/Station Wagon", "Station Wagon Automatic")
                if is_auto_any and l1_model and (not is_m2) and (not is_wagon):
                    category = "SUV Automatic"
            except Exception:
                pass
            # FINAL L2/J2 OVERRIDE: 308 SW and Scala to wagon groups; autos -> L2
            try:
                cnf = (car_name or "").lower()
                if re.search(r"\bford\s*focus\b", cnf) and re.search(r"\b(sw|estate|wagon|turnier|kombi|sportbreak|sport\s*brake|tourer|touring)\b", cnf):
                    if _is_auto_flag(cnf, _txt, transmission_label):
                        category = "Station Wagon Automatic"
                    else:
                        category = "Estate/Station Wagon"
                if re.search(r"\b(vw|volkswagen)\s*golf\b", cnf) and re.search(r"\b(sw|variant)\b", cnf):
                    if _is_auto_flag(cnf, _txt, transmission_label):
                        category = "Station Wagon Automatic"
                    else:
                        category = "Estate/Station Wagon"
                if re.search(r"\bfiat\s*500l\b", cnf):
                    if _is_auto_flag(cnf, _txt, transmission_label):
                        category = "Station Wagon Automatic"
                    else:
                        category = "Estate/Station Wagon"
                if re.search(r"\b(vw|volkswagen)\s*passat\b", cnf):
                    if _is_auto_flag(cnf, _txt, transmission_label):
                        category = "Station Wagon Automatic"
                    else:
                        category = "Estate/Station Wagon"
                if re.search(r"\bpeugeot\s*508\b", cnf):
                    if _is_auto_flag(cnf, _txt, transmission_label):
                        category = "Station Wagon Automatic"
                    else:
                        category = "Estate/Station Wagon"
                if re.search(r"\bhyundai\s*i30\b", cnf):
                    if _is_auto_flag(cnf, _txt, transmission_label):
                        category = "Station Wagon Automatic"
                    else:
                        category = "Estate/Station Wagon"
                if re.search(r"\btoyota\s*corolla\b", cnf) and re.search(r"\b(sw|ts|touring\s*sports?|sport\s*touring|estate|wagon)\b", cnf):
                    if _is_auto_flag(cnf, _txt, transmission_label):
                        category = "Station Wagon Automatic"
                    else:
                        category = "Estate/Station Wagon"
                # Enforce E2 for Toyota Corolla base Auto
                if re.search(r"\btoyota\s*corolla\b", cnf) and not re.search(r"\b(sw|ts|touring\s*sports?|sport\s*touring|estate|wagon)\b", cnf):
                    if _is_auto_flag(cnf, _txt, transmission_label):
                        category = "Economy Automatic"
                if re.search(r"\bseat\s*leon\b", cnf) and re.search(r"\b(sw|st|variant|sport\s*tourer|sportstourer|estate)\b", cnf):
                    if _is_auto_flag(cnf, _txt, transmission_label):
                        category = "Station Wagon Automatic"
                    else:
                        category = "Estate/Station Wagon"
                if re.search(r"\b(skoda|škoda)\s*scala\b", cnf):
                    if _is_auto_flag(cnf, _txt, transmission_label):
                        category = "Station Wagon Automatic"
                    else:
                        category = "Estate/Station Wagon"
                if re.search(r"\bford\s*focus\b", cnf) and re.search(r"\b(sw|estate|wagon)\b", cnf) and _is_auto_flag(cnf, _txt, transmission_label):
                    category = "Station Wagon Automatic"
                if re.search(r"\b(opel|vauxhall)\s*astra\b", cnf):
                    if _is_auto_flag(cnf, _txt, transmission_label):
                        category = "Station Wagon Automatic"
                    else:
                        category = "Estate/Station Wagon"
                if re.search(r"\brenault\s*megane\b", cnf) and re.search(r"\bsedan\b", cnf) and _is_auto_flag(cnf, _txt, transmission_label):
                    category = "Station Wagon Automatic"
                if re.search(r"\brenault\s*megane\b", cnf) and re.search(r"\b(sw|estate|wagon|sport\s*tourer|sport\s*tourismo|tourer)\b", cnf):
                    if _is_auto_flag(cnf, _txt, transmission_label):
                        category = "Station Wagon Automatic"
                    else:
                        category = "Estate/Station Wagon"
            except Exception:
                pass
            # FINAL M2 OVERRIDE: common 7-seater autos -> 7 Seater Automatic (wins over J1/D)
            try:
                cn4 = (car_name or "").lower()
                m2_patterns = [
                    r"\bcitro[eë]n\s*c4\s*(picasso|grand\s*spacetourer|grand\s*space\s*tourer)\b",
                    r"\bcitro[eë]n\s*grand\s*picasso\b",
                    r"\brenault\s*grand\s*sc[eé]nic\b",
                    r"\bmercedes\s*glb\b.*\b(7\s*seater|7\s*lugares|7p|7\s*seats)\b",
                    r"\b(vw|volkswagen)\s*multivan\b",
                    r"\bpeugeot\s*rifter\b",
                ]
                if any(re.search(p, cn4) for p in m2_patterns) and _is_auto_flag(cn4, _txt, transmission_label):
                    category = "7 Seater Automatic"
            except Exception:
                pass
            # FINAL E1 OVERRIDE: Toyota Aygo Auto -> Mini Automatic (avoid uncategorized)
            try:
                cn5 = (car_name or "").lower()
                if re.search(r"\btoyota\s*aygo\b", cn5) and _is_auto_flag(cn5, _txt, transmission_label):
                    category = "Mini Automatic"
                if re.search(r"\bkia\s*picanto\b", cn5) and _is_auto_flag(cn5, _txt, transmission_label):
                    category = "Mini Automatic"
            except Exception:
                pass
            # FINAL B1 OVERRIDE: base mini models -> 'Mini 4 Doors' (when not auto/cabrio/special variants)
            try:
                b1_list = [
                    r"\bfiat\s*500\b",
                    r"\bcitro[eë]n\s*c1\b",
                    r"\bpeugeot\s*108\b",
                    r"\bopel\s*adam\b",
                    r"\btoyota\s*aygo\b",
                    r"\b(vw|volkswagen)\s*up\b",
                    r"\bford\s*ka\b",
                    r"\brenault\s*twingo\b",
                    r"\bkia\s*picanto\b",
                ]
                _name = (car_name or "").lower()
                if any(re.search(p, _name) for p in b1_list):
                    # do not apply if this is a D/E2 economy model (protect Group D)
                    d_guard = [
                        r"\bpeugeot\s*208\b", r"\bopel\s*corsa\b", r"\bseat\s*ibiza\b",
                        r"\b(vw|volkswagen)\s*polo\b", r"\bcitro[eë]n\s*c3\b", r"\brenault\s*clio\b",
                        r"\bford\s*fiesta\b", r"\bnissan\s*micra\b", r"\bhyundai\s*i20\b", r"\baudi\s*a1\b",
                        r"\bdacia\s*sandero\b"
                    ]
                    if any(re.search(p, _name) for p in d_guard):
                        raise Exception("skip B1 for D/E2 models")
                    # exclude autos and cabrio and special variants
                    if (not _is_auto_flag(_name, _txt, transmission_label)) \
                        and not re.search(r"\b(cabrio|convertible|cabriolet)\b", _name) \
                        and not re.search(r"\b(500x|500l|aygo\s*x|aircross|countryman)\b", _name):
                        category = "Mini 4 Doors"
            except Exception:
                pass
            # Skip blocked models
            if car_name and _is_blocked_model(car_name):
                continue
            items.append({
                "id": idx,
                "car": car_name,
                "supplier": supplier,
                "price": price_text,
                "currency": "",
                "category": category,
                "transmission": transmission_label,
                "photo": photo,
                "link": link,
            })
            idx += 1
        if items:
            return items
    except Exception:
        pass

    # Require an explicit currency marker to avoid capturing ratings/ages
    price_regex = re.compile(r"(?:€\s*\d{1,4}(?:[\.,]\d{3})*(?:[\.,]\d{2})?|\bEUR\s*\d{1,4}(?:[\.,]\d{3})*(?:[\.,]\d{2})?)", re.I)

    # Basic category keyword list (EN + PT)
    CATEGORY_KEYWORDS = [
        "mini","economy","compact","intermediate","standard","full-size","full size","suv","premium","luxury","van","estate","convertible","people carrier","minivan","midsize",
        "mini","económico","económico","compacto","intermédio","padrão","familiar","suv","premium","luxo","carrinha","descapotável","monovolume","médio"
    ]

    candidates = []
    for el in soup.find_all(text=price_regex):
        try:
            txt = el.strip()
        except Exception:
            continue
        if not txt or len(txt) > 50:
            continue
        node = el if hasattr(el, 'parent') else None
        if not node:
            continue
        # climb up to find a reasonable container (card/row)
        container = node.parent
        depth = 0
        while container and depth < 6 and container.name not in ("tr", "li", "article", "section", "div"):
            container = container.parent
            depth += 1
        if not container:
            container = node.parent
        candidates.append((container, txt))

    seen = set()
    for idx, (container, price_text) in enumerate(candidates):
        # car/model
        name_el = container.select_one(".car, .vehicle, .model, .title, .name, .veh-name, [class*='model'], [class*='vehicle']")
        car_name = name_el.get_text(strip=True) if name_el else ""
        # supplier: try explicit, else alt/title of images within container
        supplier_el = container.select_one(".supplier, .vendor, .partner, [class*='supplier'], [class*='vendor']")
        supplier = supplier_el.get_text(strip=True) if supplier_el else ""
        if not supplier:
            img = container.select_one("img[alt], img[title]")
            if img:
                supplier = img.get("alt") or img.get("title") or ""
        # category/group: try explicit labels then keyword search in container text
        cat_el = container.select_one(".category, .group, .vehicle-category, [class*='category'], [class*='group'], [class*='categoria'], [class*='grupo']")
        category = cat_el.get_text(strip=True) if cat_el else ""
        if not category:
            try:
                text = container.get_text(" ", strip=True).lower()
                match = next((kw for kw in CATEGORY_KEYWORDS if kw.lower() in text), "")
                category = match.title() if match else ""
            except Exception:
                category = ""
        # Crossover override based on model name (when available)
        try:
            _car_lc = (car_name or "").lower()
            if re.search(r"\b(peugeot\s*2008|peugeot\s*3008|citro[eë]n\s*c4)\b", _car_lc, re.I):
                category = "Crossover"
        except Exception:
            pass

        # link
        link = url_from_row(container, base_url) or base_url

        key = (supplier, car_name, price_text)
        if key in seen:
            continue
        seen.add(key)

        # detect currency symbol present in the text
        curr = "EUR" if re.search(r"EUR", price_text, re.I) else ("EUR" if "€" in price_text else "")
        items.append({
            "id": idx,
            "car": car_name,
            "supplier": supplier,
            "price": price_text,
            "currency": curr,
            "category": category,
            "transmission": transmission_label,
            "link": link,
        })
        if len(items) >= 50:
            break
    # If no detailed items parsed, fall back to provider summaries to ensure prices are shown
    if not items and summary_items:
        items = summary_items
    # Ensure photos when grupo/category_code is known
    try:
        for it in items:
            if (not it.get("photo")) and it.get("category_code"):
                cc = it.get("category_code")
                it["photo"] = urljoin(base_url, f"/cdn/img/cars/S/car_{cc}.jpg")
    except Exception:
        pass
    return items


def url_from_row(row, base_url: str) -> str:
    a = row.select_one("a[href]")
    if a and a.has_attr("href"):
        href = a["href"]
        if href and not href.lower().startswith("javascript") and href != "#":
            return urljoin(base_url, href)
    for attr in ["data-href", "data-url", "data-link"]:
        el = row.select_one(f"*[{attr}]")
        if el and el.has_attr(attr):
            return urljoin(base_url, el[attr])
    clickable = row.select_one("*[onclick]")
    if clickable and clickable.has_attr("onclick"):
        m = re.search(r"https?://[^'\"]+", clickable["onclick"])  
        if m:
            return m.group(0)
    return ""


def try_direct_carjet(location_name: str, start_dt, end_dt, lang: str = "pt", currency: str = "EUR") -> str:
    try:
        sess = requests.Session()
        ua = {
            "User-Agent": "Mozilla/5.0 (compatible; PriceTracker/1.0)",
            "Accept-Language": "pt-PT,pt;q=0.9,en;q=0.6",
            "X-Forwarded-For": "185.23.160.1",
            "Referer": "https://www.carjet.com/do/list/pt",
        }
        lang = (lang or "pt").lower()
        # Pre-seed cookies to bias locale
        try:
            sess.cookies.set("monedaForzada", currency)
            sess.cookies.set("moneda", currency)
            sess.cookies.set("currency", currency)
            sess.cookies.set("idioma", lang.upper())
            sess.cookies.set("lang", lang)
            sess.cookies.set("country", "PT")
        except Exception:
            pass

        # 1) GET locale homepage to mint session and try to capture s/b tokens
        if lang == "pt":
            home_path = "aluguel-carros/index.htm"
        elif lang == "es":
            home_path = "alquiler-coches/index.htm"
        elif lang == "fr":
            home_path = "location-voitures/index.htm"
        elif lang == "de":
            home_path = "mietwagen/index.htm"
        elif lang == "it":
            home_path = "autonoleggio/index.htm"
        elif lang == "nl":
            home_path = "autohuur/index.htm"
        else:
            home_path = "index.htm"
        home_url = f"https://www.carjet.com/{home_path}"
        home = sess.get(home_url, headers=ua, timeout=20)
        s_token = None
        b_token = None
        try:
            m = re.search(r"[?&]s=([A-Za-z0-9]+)", home.text)
            if m:
                s_token = m.group(1)
            m = re.search(r"[?&]b=([A-Za-z0-9]+)", home.text)
            if m:
                b_token = m.group(1)
        except Exception:
            pass

        # 2) Prefer submitting the actual homepage form with all hidden fields preserved
        try:
            soup = BeautifulSoup(home.text, "lxml")
            form = soup.select_one("form[name='menu_tarifas'], form#booking_form")
            if form:
                action = form.get("action") or f"/do/list/{lang}"
                post_url = action if action.startswith("http") else requests.compat.urljoin(home_url, action)
                payload: Dict[str, Any] = {}
                # include all inputs
                for inp in form.select("input[name]"):
                    name = inp.get("name")
                    if not name:
                        continue
                    val = inp.get("value", "")
                    payload[name] = val
                # include selects
                for sel in form.select("select[name]"):
                    name = sel.get("name")
                    if not name:
                        continue
                    # take selected option or first
                    opt = sel.select_one("option[selected]") or sel.select_one("option")
                    payload[name] = opt.get("value") if opt else ""

                # override with our values
                override = build_carjet_form(location_name, start_dt, end_dt, lang=lang, currency=currency)
                payload.update({k: v for k, v in override.items() if v is not None})
                if s_token:
                    payload["s"] = s_token
                if b_token:
                    payload["b"] = b_token

                headers = {
                    "User-Agent": ua["User-Agent"],
                    "Origin": "https://www.carjet.com",
                    "Referer": home_url,
                }
                resp = sess.post(post_url, data=payload, headers=headers, timeout=25)
                if resp.status_code == 200 and resp.text:
                    return resp.text
        except Exception:
            pass

        # 3) Fallback: POST to /do/list/{lang} with our constructed payload
        data = build_carjet_form(location_name, start_dt, end_dt, lang=lang, currency=currency)
        if s_token:
            data["s"] = s_token
        if b_token:
            data["b"] = b_token

        headers = {
            "User-Agent": ua["User-Agent"],
            "Origin": "https://www.carjet.com",
            "Referer": home_url,
            "Accept-Language": ua.get("Accept-Language", "pt-PT,pt;q=0.9,en;q=0.6"),
            "X-Forwarded-For": ua.get("X-Forwarded-For", "185.23.160.1"),
        }
        url = f"https://www.carjet.com/do/list/{lang}"
        resp = sess.post(url, data=data, headers=headers, timeout=25)
        if resp.status_code == 200 and resp.text:
            # Detect if we were redirected to a generic homepage (wrong locale)
            homepage_like = False
            try:
                homepage_like = bool(re.search(r'hrental_pagetype"\s*:\s*"home"', resp.text) or re.search(r'data-steplist="home"', resp.text))
            except Exception:
                homepage_like = False
            if not homepage_like:
                return resp.text
            # Fallback path observed on results pages: modalFilter.asp then carList.asp
            try:
                mf_url = f"https://www.carjet.com/modalFilter.asp"
                # Minimal payload aligning with page
                mf_payload = {
                    "frmDestino": data.get("frmDestino") or data.get("dst_id") or data.get("pickupId") or "",
                    "frmFechaRecogida": f"{start_dt.strftime('%d/%m/%Y')} {start_dt.strftime('%H:%M')}",
                    "frmFechaDevolucion": f"{end_dt.strftime('%d/%m/%Y')} {end_dt.strftime('%H:%M')}",
                    "idioma": lang.upper(),
                    "frmMoneda": currency,
                    "frmTipoVeh": "CAR",
                }
                _ = sess.post(mf_url, data=mf_payload, headers=headers, timeout=20)
            except Exception:
                pass
            try:
                # Keep session tokens if available
                _q = f"idioma={lang.upper()}&case=2"
                if s_token:
                    _q += f"&s={s_token}"
                if b_token:
                    _q += f"&b={b_token}"
                cl_url = f"https://www.carjet.com/carList.asp?{_q}"
                rlist = sess.get(cl_url, headers=headers, timeout=25)
                if rlist.status_code == 200 and rlist.text:
                    return rlist.text
            except Exception:
                pass

        # If not OK or homepage detected, retry with PT-Portugal homepage and forced params on POST URL
        try:
            # Visit PT-Portugal homepage spelling (aluguer vs aluguel)
            home_url_ptpt = "https://www.carjet.com/aluguer-carros/index.htm"
            _ = sess.get(home_url_ptpt, headers=ua, timeout=20)
            headers2 = dict(headers)
            post_url2 = f"https://www.carjet.com/do/list/{lang}?idioma=PT&moneda=EUR&currency=EUR"
            resp2 = sess.post(post_url2, data=data, headers=headers2, timeout=25)
            if resp2.status_code == 200 and resp2.text:
                try:
                    if re.search(r'hrental_pagetype\"\s*:\s*\"home\"', resp2.text) or re.search(r'data-steplist=\"home\"', resp2.text):
                        pass
                    else:
                        return resp2.text
                except Exception:
                    return resp2.text
        except Exception:
            pass
    except Exception:
        pass
    return ""


def build_carjet_form(location_name: str, start_dt, end_dt, lang: str = "pt", currency: str = "EUR") -> Dict[str, Any]:
    # Build server-expected fields; include hidden destination IDs when possible
    pickup_dmY = start_dt.strftime("%d/%m/%Y")
    dropoff_dmY = end_dt.strftime("%d/%m/%Y")
    pickup_HM = start_dt.strftime("%H:%M")
    dropoff_HM = end_dt.strftime("%H:%M")
    code = LOCATION_CODES.get((location_name or "").lower(), "")
    form = {
        # free text
        "pickup": location_name,
        "dropoff": location_name,
        # hidden ids (best effort)
        "pickupId": code,
        "dst_id": code,
        "zoneCode": code,
        # dates
        "fechaRecogida": pickup_dmY,
        "fechaEntrega": dropoff_dmY,
        # times
        "fechaRecogidaSelHour": pickup_HM,
        "fechaEntregaSelHour": dropoff_HM,
        # locale hints
        "idioma": lang.upper(),
        "moneda": currency,
        "chkOneWay": "SI",
        # fields observed on list page (robustness)
        "frmDestino": code or "",
        "frmFechaRecogida": f"{pickup_dmY} {pickup_HM}",
        "frmFechaDevolucion": f"{dropoff_dmY} {dropoff_HM}",
        "frmMoneda": currency,
        "frmTipoVeh": "CAR",
    }
    return form


def fetch_with_optional_proxy(url: str, headers: Dict[str, str]):
    # Default locale headers if not provided
    try:
        headers = dict(headers or {})
        headers.setdefault("Accept-Language", "pt-PT,pt;q=0.9,en;q=0.6")
        headers.setdefault("X-Forwarded-For", "185.23.160.1")
    except Exception:
        pass
    # Prefer direct fetch with EUR cookies for CarJet to reduce latency and avoid geolocation flips
    try:
        from urllib.parse import urlparse as _urlparse
        pr = _urlparse(url)
        if pr.netloc.endswith("carjet.com"):
            h2 = dict(headers or {})
            h2["Cookie"] = "monedaForzada=EUR; moneda=EUR; currency=EUR; country=PT; idioma=PT; lang=pt"
            if _HTTPX_CLIENT:
                return _HTTPX_CLIENT.get(url, headers=h2)
            return requests.get(url, headers=h2, timeout=20)
    except Exception:
        pass
    if SCRAPER_SERVICE.lower() == "scrapeops" and SCRAPER_API_KEY:
        try:
            params = {
                "api_key": SCRAPER_API_KEY,
                "url": url,
                "render_js": "true",
            }
            if SCRAPER_COUNTRY:
                params["country"] = SCRAPER_COUNTRY
            r = requests.get("https://proxy.scrapeops.io/v1/", params=params, headers=headers, timeout=30)
            if r.status_code in (401, 403):
                # Fallback to direct if proxy is unauthorized/forbidden
                if _HTTPX_CLIENT:
                    return _HTTPX_CLIENT.get(url, headers=headers)
                return requests.get(url, headers=headers, timeout=6)
            return r
        except Exception:
            # Fallback to direct on any proxy error
            if _HTTPX_CLIENT:
                return _HTTPX_CLIENT.get(url, headers=headers)
            return requests.get(url, headers=headers, timeout=10)
    if _HTTPX_CLIENT:
        return _HTTPX_CLIENT.get(url, headers=headers)
    return requests.get(url, headers=headers, timeout=20)


async def async_fetch_with_optional_proxy(url: str, headers: Dict[str, str]):
    try:
        headers = dict(headers or {})
        headers.setdefault("Accept-Language", "pt-PT,pt;q=0.9,en;q=0.6")
        headers.setdefault("X-Forwarded-For", "185.23.160.1")
    except Exception:
        pass
    # Prefer direct CarJet with PT/EUR cookies
    try:
        from urllib.parse import urlparse as _urlparse
        pr = _urlparse(url)
        if pr.netloc.endswith("carjet.com"):
            h2 = dict(headers or {})
            h2["Cookie"] = "monedaForzada=EUR; moneda=EUR; currency=EUR; country=PT; idioma=PT; lang=pt"
            if _HTTPX_ASYNC:
                return await _HTTPX_ASYNC.get(url, headers=h2)
            # fallback to sync in thread
            return await asyncio.to_thread(requests.get, url, headers=h2, timeout=6)
    except Exception:
        pass
    if SCRAPER_SERVICE.lower() == "scrapeops" and SCRAPER_API_KEY:
        try:
            params = {
                "api_key": SCRAPER_API_KEY,
                "url": url,
                "render_js": "true",
            }
            if SCRAPER_COUNTRY:
                params["country"] = SCRAPER_COUNTRY
            # httpx doesn't proxy this conveniently; use requests in a thread
            r = await asyncio.to_thread(requests.get, "https://proxy.scrapeops.io/v1/", params=params, headers=headers, timeout=6)
        except TypeError:
            # Fallback: direct fetch
            if _HTTPX_ASYNC:
                return await _HTTPX_ASYNC.get(url, headers=headers)
            return await asyncio.to_thread(requests.get, url, headers=headers, timeout=6)
        try:
            if r.status_code in (401, 403):
                if _HTTPX_ASYNC:
                    return await _HTTPX_ASYNC.get(url, headers=headers)
                return await asyncio.to_thread(requests.get, url, headers=headers, timeout=6)
            return r
        except Exception:
            if _HTTPX_ASYNC:
                return await _HTTPX_ASYNC.get(url, headers=headers)
            return await asyncio.to_thread(requests.get, url, headers=headers, timeout=6)
    if _HTTPX_ASYNC:
        return await _HTTPX_ASYNC.get(url, headers=headers)
    return await asyncio.to_thread(requests.get, url, headers=headers, timeout=20)


def post_with_optional_proxy(url: str, data: Dict[str, Any], headers: Dict[str, str]):
    # Default locale headers if not provided
    try:
        headers = dict(headers or {})
        headers.setdefault("Accept-Language", "pt-PT,pt;q=0.9,en;q=0.6")
        headers.setdefault("X-Forwarded-For", "185.23.160.1")
    except Exception:
        pass
    if SCRAPER_SERVICE.lower() == "scrapeops" and SCRAPER_API_KEY:
        try:
            params = {
                "api_key": SCRAPER_API_KEY,
                "url": url,
                "render_js": "true",
            }
            if SCRAPER_COUNTRY:
                params["country"] = SCRAPER_COUNTRY
            r = requests.post("https://proxy.scrapeops.io/v1/", params=params, headers=headers, data=data, timeout=30)
            if r.status_code in (401, 403):
                if _HTTPX_CLIENT:
                    return _HTTPX_CLIENT.post(url, headers=headers, data=data)
                return requests.post(url, headers=headers, data=data, timeout=20)
            return r
        except Exception:
            if _HTTPX_CLIENT:
                return _HTTPX_CLIENT.post(url, headers=headers, data=data)
            return requests.post(url, headers=headers, data=data, timeout=20)
    if _HTTPX_CLIENT:
        return _HTTPX_CLIENT.post(url, headers=headers, data=data)
    return requests.post(url, headers=headers, data=data, timeout=20)


@app.post("/api/bulk-prices")
async def bulk_prices(request: Request):
    require_auth(request)
    body = await request.json()
    locations: List[Dict[str, Any]] = body.get("locations", [])
    supplier_priority: Optional[str] = body.get("supplier_priority")
    durations = body.get("durations", [1,2,3,4,5,6,7,8,9,14,22,31,60])

    results: List[Dict[str, Any]] = []
    headers = {"User-Agent": "Mozilla/5.0 (compatible; PriceTracker/1.0)"}

    # Global simple rate limiter (shared across requests)
    _RL_LOCK = getattr(bulk_prices, "_RL_LOCK", None)
    if _RL_LOCK is None:
        _RL_LOCK = asyncio.Lock()
        setattr(bulk_prices, "_RL_LOCK", _RL_LOCK)
    _RL_LAST = getattr(bulk_prices, "_RL_LAST", 0.0)
    _RL_MIN_INTERVAL = 1.0 / GLOBAL_FETCH_RPS if GLOBAL_FETCH_RPS and GLOBAL_FETCH_RPS > 0 else 0.0

    async def _rate_limit_tick():
        nonlocal _RL_LAST
        if _RL_MIN_INTERVAL <= 0:
            return
        async with _RL_LOCK:
            now = time.time()
            wait = _RL_MIN_INTERVAL - (now - _RL_LAST)
            if wait > 0:
                await asyncio.sleep(wait)
                now = time.time()
            _RL_LAST = now
            setattr(bulk_prices, "_RL_LAST", _RL_LAST)

    async def _fetch_parse(url: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        # Retry up to 2 attempts for transient failures
        attempts = 0
        last_exc: Optional[Exception] = None
        while attempts < BULK_MAX_RETRIES:
            attempts += 1
            t0 = time.time()
            try:
                await _rate_limit_tick()
                r = await async_fetch_with_optional_proxy(url, headers=headers)
                r.raise_for_status()
                html = r.text
                t_fetch = int((time.time() - t0) * 1000)
                t1 = time.time()
                items = await asyncio.to_thread(parse_prices, html, url)
                items = convert_items_gbp_to_eur(items)
                items = apply_price_adjustments(items, url)
                items = normalize_and_sort(items, supplier_priority)
                t_parse = int((time.time() - t1) * 1000)
                # best-effort timing log
                try:
                    with open(DEBUG_DIR / "perf_bulk.txt", "a", encoding="utf-8") as _fp:
                        _fp.write(f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} fetch_ms={t_fetch} parse_ms={t_parse} attempts={attempts} url={url[:180]}\n")
                except Exception:
                    pass
                return items, {"fetch_ms": t_fetch, "parse_ms": t_parse, "attempts": attempts}
            except Exception as e:
                last_exc = e
                await asyncio.sleep(0.3 * attempts)
        raise last_exc  # type: ignore

    for loc in locations:
        name = loc.get("name", "")
        urls: List[str] = loc.get("urls", [])
        loc_block = {"location": name, "durations": []}
        # Cap concurrency to avoid overloading Render (CPU/net)
        sem = asyncio.Semaphore(BULK_CONCURRENCY)
        async def _worker(index: int, url: str, days: int):
            async with sem:
                try:
                    items, timing = await _fetch_parse(url)
                    return {"days": days, "count": len(items), "items": items, "timing": timing}
                except Exception as e:
                    return {"days": days, "error": str(e), "items": [], "timing": {"attempts": BULK_MAX_RETRIES}}

        tasks = []
        for idx, url in enumerate(urls):
            days = durations[idx] if idx < len(durations) else None
            if not url or days is None:
                continue
            tasks.append(_worker(idx, url, days))
        if tasks:
            loc_block["durations"] = await asyncio.gather(*tasks)
        results.append(loc_block)
    return JSONResponse({"ok": True, "results": results})


@app.post("/api/track-by-url")
async def track_by_url(request: Request):
    try:
        if not bool(str(os.getenv("DEV_NO_AUTH", "")).strip().lower() in ("1","true","yes","on")):
            require_auth(request)
    except Exception:
        require_auth(request)
    body = await request.json()
    location: str = body.get("location") or ""
    pickup_date: str = body.get("pickupDate") or ""
    pickup_time: str = body.get("pickupTime", "10:00")  # HH:mm
    days: Optional[int] = body.get("days")
    url: str = body.get("url") or ""
    no_cache: bool = bool(body.get("noCache", False))
    currency: str = body.get("currency", "")
    if not url:
        return _no_store_json({"ok": False, "error": "url is required"}, status_code=400)

    try:
        from datetime import datetime
        start_dt: Optional[datetime] = None
        if pickup_date:
            try:
                start_dt = datetime.fromisoformat(pickup_date + "T" + pickup_time)
            except Exception:
                start_dt = None
        # 0) 60s in-memory cache by normalized URL
        try:
            from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode
            pr0 = urlparse(url)
            qd = dict(parse_qsl(pr0.query, keep_blank_values=True))
            # normalize currency/lang params position for stable key
            norm_q = urlencode(sorted(qd.items()))
            norm_url = urlunparse((pr0.scheme, pr0.netloc, pr0.path, pr0.params, norm_q, pr0.fragment))
        except Exception:
            norm_url = url
        now_ts = time.time()
        cached = _URL_CACHE.get(norm_url)
        if (not no_cache) and cached and (now_ts - cached[0] < 60):
            payload = dict(cached[1])
            # Avoid serving cached empty results
            if payload.get("items"):
                return _no_store_json(payload)
        headers = {
            # Desktop Chrome UA improves CarJet behavior on Render/mobile
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            "Accept-Language": "pt-PT,pt;q=0.9,en;q=0.8",
            "Referer": "https://www.carjet.com/do/list/pt",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Cache-Control": "no-cache",
            "sec-ch-ua": '"Chromium";v="123", "Not:A-Brand";v="8"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"',
        }

        # Fast path when running locally or when FAST_MODE=true: single direct fetch, no retries
        try:
            IS_RENDER = bool(os.getenv("RENDER") or os.getenv("RENDER_EXTERNAL_URL"))
        except Exception:
            IS_RENDER = False
        FAST_MODE = bool(str(os.getenv("FAST_MODE", "")).strip().lower() in ("1","true","yes","on"))
        if (not IS_RENDER) or FAST_MODE:
            try:
                fast_headers = dict(headers)
                fast_headers["Cookie"] = "monedaForzada=EUR; moneda=EUR; currency=EUR; country=PT; idioma=PT; lang=pt"
                r_fast = await asyncio.to_thread(requests.get, url, headers=fast_headers, timeout=(6,20))
                r_fast.raise_for_status()
                html_fast = r_fast.text
                items_fast = await asyncio.to_thread(parse_prices, html_fast, url)
                # If homepage-like or empty, quickly try /pt variant as a second shot
                homepage_like_fast = False
                try:
                    homepage_like_fast = ("Pesquisando em mais de 1000 locadoras" in html_fast) or (re.search(r"Pesquisando\s+em\s+mais\s+de\s+1000", html_fast) is not None)
                except Exception:
                    homepage_like_fast = False
                if (not items_fast) or homepage_like_fast:
                    try:
                        from urllib.parse import urlparse as _uparse, urlunparse as _uunparse
                        prx = _uparse(url)
                        if prx.path.startswith('/do/list/') and not prx.path.startswith('/do/list/pt'):
                            pt_url = _uunparse((prx.scheme, prx.netloc, '/do/list/pt', prx.params, prx.query, prx.fragment))
                            r_fast2 = await asyncio.to_thread(requests.get, pt_url, headers=fast_headers, timeout=(6,20))
                            r_fast2.raise_for_status()
                            html_fast2 = r_fast2.text
                            items_fast2 = await asyncio.to_thread(parse_prices, html_fast2, pt_url)
                            if items_fast2:
                                html_fast = html_fast2
                                items_fast = items_fast2
                    except Exception:
                        pass
                items_fast = normalize_and_sort(items_fast, supplier_priority=None)
                payload = {
                    "ok": True,
                    "items": items_fast,
                    "location": location or _detect_location_name(html_fast) or "",
                    "start_date": (start_dt.strftime("%Y-%m-%d") if start_dt else ""),
                    "days": days,
                    "last_updated": time.strftime('%Y-%m-%d %H:%M:%S'),
                }
                _URL_CACHE[norm_url] = (time.time(), dict(payload))
                return _no_store_json(payload)
            except Exception:
                pass
        # Overall time budget to avoid long waits on mobile/Render
        budget_ms = 7000
        total_t0 = time.time()
        def remaining_ms():
            try:
                return max(0, budget_ms - int((time.time() - total_t0) * 1000))
            except Exception:
                return 0

        # 1) Direct fetch for CarJet PT results URLs to preserve locale (avoid proxy geolocation flipping)
        html = ""
        items: List[Dict[str, Any]] = []
        try:
            from urllib.parse import urlparse, parse_qs
            pr = urlparse(url)
            qs = parse_qs(pr.query)
            is_carjet = pr.netloc.endswith("carjet.com")
            is_pt_results = pr.path.startswith("/do/list/pt") and ("s" in qs and "b" in qs)
            is_carjet_list = is_carjet and pr.path.startswith("/do/list/")
        except Exception:
            is_carjet = False
            is_pt_results = False
            is_carjet_list = False

        if USE_PLAYWRIGHT and _HAS_PLAYWRIGHT and is_carjet:
            try:
                items = scrape_with_playwright(url)
                if items:
                    html = "(playwright)"
            except Exception:
                items = []
                html = ""

        if (not items) and is_carjet and (is_pt_results or is_carjet_list) and remaining_ms() > 1200:
            # Race direct URL and a /pt-normalized variant in parallel; first success wins
            direct_headers = dict(headers)
            direct_headers["Cookie"] = "monedaForzada=EUR; moneda=EUR; currency=EUR; country=PT; idioma=PT; lang=pt"
            direct_headers["sec-ch-ua"] = headers.get("sec-ch-ua")
            direct_headers["sec-ch-ua-mobile"] = headers.get("sec-ch-ua-mobile")
            direct_headers["sec-ch-ua-platform"] = headers.get("sec-ch-ua-platform")
            try:
                from urllib.parse import urlparse as _uparse, urlunparse as _uunparse
                prx = _uparse(url)
                pt_url = _uunparse((prx.scheme, prx.netloc, "/do/list/pt", prx.params, prx.query, prx.fragment)) if prx.path.startswith("/do/list/") and not prx.path.startswith("/do/list/pt") else url
            except Exception:
                pt_url = url

            async def fetch_and_parse(u: str):
                try:
                    t0 = time.time()
                    r = await async_fetch_with_optional_proxy(u, direct_headers)
                    r.raise_for_status()
                    h = r.text
                    its = await asyncio.to_thread(parse_prices, h, u)
                    hp = False
                    try:
                        hp = ("Pesquisando em mais de 1000 locadoras" in h) or (re.search(r"Pesquisando\s+em\s+mais\s+de\s+1000", h) is not None)
                    except Exception:
                        hp = False
                    dt = int((time.time() - t0) * 1000)
                    try:
                        print(f"[track_by_url] direct fetch {u} took {dt}ms items={(len(its) if its else 0)} homepage={hp}")
                    except Exception:
                        pass
                    if its and not hp:
                        return (u, h, its)
                except Exception:
                    return None
                return None

            tasks = [asyncio.create_task(fetch_and_parse(url)), asyncio.create_task(fetch_and_parse(pt_url))]
            # Respect remaining time budget for the parallel race
            timeout_sec = max(0.1, remaining_ms() / 1000.0)
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED, timeout=timeout_sec)
            winner = None
            for d in done:
                try:
                    winner = d.result()
                except Exception:
                    winner = None
            for p in pending:
                p.cancel()
            if winner:
                _, html, items = winner
            else:
                html = ""
                items = []

        # 1.a) If Playwright is enabled, try rendering the final UI to capture client-updated totals
        if (not items) and USE_PLAYWRIGHT and _HAS_PLAYWRIGHT and is_carjet:
            try:
                html_pw = render_with_playwright(url)
                if html_pw:
                    html = html_pw
                    items = parse_prices(html_pw, url)
            except Exception:
                pass

        # 1.b) If not a PT results URL, or direct failed, use normal path (with proxy if configured)
        if not html:
            resp = await async_fetch_with_optional_proxy(url, headers=headers)
            resp.raise_for_status()
            html = resp.text
            items = await asyncio.to_thread(parse_prices, html, url)
        # Determine if we only captured provider summaries (no car names) or wrong currency
        gbp_seen = any(("£" in (it.get("price") or "")) or re.search(r"\bGBP\b", (it.get("price") or ""), re.I) for it in (items or []))
        homepage_like = False
        try:
            if isinstance(html, str):
                homepage_like = ("Pesquisando em mais de 1000 locadoras" in html) or (re.search(r"Pesquisando\s+em\s+mais\s+de\s+1000", html) is not None)
        except Exception:
            homepage_like = False
        only_summaries = homepage_like or (not items) or all(not (it.get("car") or "").strip() for it in items)

        # If we have items but they are GBP, convert now; continue to final response
        if items and gbp_seen:
            items = convert_items_gbp_to_eur(items)
        # Apply env-driven adjustments for Carjet
        if items:
            items = apply_price_adjustments(items, url)

        # 1.5) If items are empty or GBP/only summaries, retry with EUR hints
        if (only_summaries or not items) and remaining_ms() > 1200:
            try:
                from urllib.parse import urlencode, urlparse, parse_qsl, urlunparse
                def _with_param(u: str, key: str, value: str) -> str:
                    pr = urlparse(u)
                    q = dict(parse_qsl(pr.query, keep_blank_values=True))
                    q[key] = value
                    new_q = urlencode(q)
                    return urlunparse((pr.scheme, pr.netloc, pr.path, pr.params, new_q, pr.fragment))

                # CarJet-specific normalization: force Portuguese path and EUR params
                url_norm = url
                try:
                    pr = urlparse(url)
                    if pr.netloc.endswith("carjet.com") and pr.path.startswith("/do/list/") and not pr.path.startswith("/do/list/pt"):
                        # keep query intact, only change locale path to /pt
                        url_norm = urlunparse((pr.scheme, pr.netloc, "/do/list/pt", pr.params, pr.query, pr.fragment))
                except Exception:
                    url_norm = url

                # Build robust set of variants including language and country
                base_eur = _with_param(url_norm, "moneda", "EUR")
                eur_variants = [
                    base_eur,
                    _with_param(base_eur, "currency", "EUR"),
                    _with_param(base_eur, "cur", "EUR"),
                    _with_param(base_eur, "idioma", "PT"),
                    _with_param(base_eur, "country", "PT"),
                ]
                # Limit retries to 2 variants to reduce latency
                eur_variants = eur_variants[:2]
                eur_headers = dict(headers)
                eur_headers["Cookie"] = "monedaForzada=EUR; moneda=EUR; currency=EUR; country=PT; idioma=PT; lang=pt"
                eur_headers["sec-ch-ua"] = headers.get("sec-ch-ua")
                eur_headers["sec-ch-ua-mobile"] = headers.get("sec-ch-ua-mobile")
                eur_headers["sec-ch-ua-platform"] = headers.get("sec-ch-ua-platform")
                retried_ok = False
                for u2 in eur_variants:
                    if remaining_ms() <= 1200:
                        break
                    try:
                        t1 = time.time()
                        r2 = await async_fetch_with_optional_proxy(u2, headers=eur_headers)
                        r2.raise_for_status()
                        html2 = r2.text
                        items2 = await asyncio.to_thread(parse_prices, html2, u2)
                        gbp2 = any((("£" in (it.get("price") or "")) or re.search(r"\bGBP\b", (it.get("price") or ""), re.I)) for it in (items2 or []))
                        dt2 = int((time.time() - t1) * 1000)
                        try:
                            print(f"[track_by_url] eur-variant fetch {u2} took {dt2}ms items={(len(items2) if items2 else 0)} gbp={gbp2}")
                        except Exception:
                            pass
                        if items2 and not gbp2:
                            html = html2
                            items = items2
                            only_summaries = False
                            break
                    except Exception:
                        continue
                    # If proxy is configured and still GBP/summary, attempt direct fetch without proxy
                    if only_summaries and (SCRAPER_SERVICE.lower() == "scrapeops" and SCRAPER_API_KEY) and remaining_ms() > 1800:
                        try:
                            r3 = requests.get(u2, headers=headers)
                            r3.raise_for_status()
                            html3 = r3.text
                            items3 = parse_prices(html3, u2)
                            gbp3 = any(("£" in (it.get("price") or "")) or re.search(r"\bGBP\b", (it.get("price") or ""), re.I) for it in (items3 or []))
                            if items3 and not gbp3:
                                html = html3
                                items = items3
                                only_summaries = False
                                break
                        except Exception:
                            pass
            except Exception:
                pass

        # 2) If still no detailed items, try Playwright to render the URL fully
        if only_summaries:
            try:
                from playwright.async_api import async_playwright
                async with async_playwright() as p:
                    browser = await p.chromium.launch(headless=True)
                    context = await browser.new_context()
                    await context.set_extra_http_headers(headers)
                    page = await context.new_page()
                    page.set_default_navigation_timeout(15000)
                    page.set_default_timeout(12000)
                    await page.goto(url, wait_until="domcontentloaded")
                    # Force currency to EUR if possible
                    try:
                        # Try in-page function first
                        await page.evaluate("() => { try { if (typeof submit_monedaForzada === 'function') { submit_monedaForzada(window.location.href, 'EUR'); } } catch(e){} }")
                        # Also click any EUR currency switchers if present
                        eurBtn = page.locator("[data-currency='EUR'], .currency .eur").first
                        if await eurBtn.count() > 0:
                            await eurBtn.click()
                            await page.wait_for_timeout(500)
                    except Exception:
                        pass
                    # wait for network results or any price-like selector
                    try:
                        await page.wait_for_response(lambda r: ("/do/list" in r.url or "/carList.asp" in r.url) and r.status == 200, timeout=20000)
                    except Exception:
                        pass
                    try:
                        await page.wait_for_selector("section.newcarlist article, .newcarlist article, .price, .amount, [class*='price']", timeout=12000)
                    except Exception:
                        pass
                    # Try to reveal hidden cars if there is a 'Ver mais' button or function
                    try:
                        for i in range(4):
                            btn = page.locator("#linkMasCoches").first
                            if await btn.count() == 0:
                                break
                            await btn.click()
                            await page.wait_for_timeout(400)
                    except Exception:
                        pass
                    try:
                        for _ in range(3):
                            await page.evaluate("() => { try { if (typeof VerMasCoches === 'function') { VerMasCoches(); } } catch(e){} }")
                            await page.wait_for_timeout(300)
                    except Exception:
                        pass
                    # Scroll to bottom to trigger any lazy loading
                    try:
                        await page.evaluate("() => { window.scrollTo(0, document.body.scrollHeight); }")
                        await page.wait_for_timeout(600)
                    except Exception:
                        pass
                    html = await page.content()
                    await browser.close()
                items = parse_prices(html, url)
            except Exception:
                items = parse_prices(html, url)
        items = normalize_and_sort(items, supplier_priority=None)
        try:
            total_dt = int((time.time() - total_t0) * 1000)
            print(f"[track_by_url] total={total_dt}ms items={(len(items) if items else 0)}")
        except Exception:
            pass
        # Try to detect dates and days from page HTML if not provided
        try:
            soup = BeautifulSoup(html, "lxml")
            txt = html
            # dataLayer hrental_startdate/hrental_enddate (YYYY-MM-DD)
            m1 = re.search(r'"hrental_startdate"\s*:\s*"(\d{4}-\d{2}-\d{2})"', txt)
            m2 = re.search(r'"hrental_enddate"\s*:\s*"(\d{4}-\d{2}-\d{2})"', txt)
            if m1:
                try:
                    start_dt = datetime.fromisoformat(m1.group(1) + "T" + (pickup_time or "10:00"))
                except Exception:
                    pass
            if m2 and m1:
                try:
                    end_dt = datetime.fromisoformat(m2.group(1) + "T" + (pickup_time or "10:00"))
                    days = (end_dt - start_dt).days if start_dt else days
                except Exception:
                    pass
            # DiasReserva in dataLayer
            if days is None:
                md = re.search(r'"DiasReserva"\s*:\s*"?(\d{1,2})"?', txt)
                if md:
                    try:
                        days = int(md.group(1))
                    except Exception:
                        pass
            # Detect location from dataLayer Destino or hidden inputs
            try:
                ml = re.search(r'"Destino"\s*:\s*"([^"]+)"', txt)
                if ml:
                    location = ml.group(1)
            except Exception:
                pass
            # Hidden inputs frmFechaRecogida / frmFechaDevolucion dd/mm/yyyy HH:MM (various id/name variants)
            if (start_dt is None) or (days is None):
                fr = soup.select_one("#frmFechaRecogida, input[name='frmFechaRecogida'], input[name='fechaRecogida']")
                fd = soup.select_one("#frmFechaDevolucion, input[name='frmFechaDevolucion'], input[name='fechaEntrega']")
                from datetime import datetime as _dt
                def _parse_dmY_HM(v: str) -> Optional[datetime]:
                    try:
                        return _dt.strptime(v, "%d/%m/%Y %H:%M")
                    except Exception:
                        return None
                if fr and fr.has_attr("value"):
                    t = fr.get("value") or ""
                    maybe = _parse_dmY_HM(t)
                    if maybe:
                        start_dt = maybe
                if fd and fd.has_attr("value"):
                    t = fd.get("value") or ""
                    maybe_end = _parse_dmY_HM(t)
                    if (maybe_end and start_dt) and (days is None):
                        days = (maybe_end - start_dt).days
                fdst = soup.select_one("#frmDestino, input[name='frmDestino'], input[name='destino']")
                if fdst and fdst.has_attr("value"):
                    val = (fdst.get("value") or "").strip()
                    if val:
                        location = val
        except Exception:
            pass
        # persist snapshot so UI can show the rows immediately
        try:
            if start_dt and days:
                save_snapshots(location, start_dt, int(days), items, currency or "")
        except Exception:
            pass
        from datetime import datetime as _dt
        payload = {
            "ok": True,
            "items": items,
            "location": location,
            "start_date": pickup_date,
            "days": days,
            "last_updated": _dt.utcnow().isoformat(timespec="seconds") + "Z",
        }
        # store in cache only if we have items
        try:
            if items:
                _URL_CACHE[norm_url] = (time.time(), payload)
        except Exception:
            pass
        # If still empty, write a small debug note (non-fatal)
        try:
            if not items:
                from html import unescape as _unesc
                title_match = re.search(r"<title>(.*?)</title>", html or "", re.I|re.S)
                ttl = _unesc(title_match.group(1)).strip() if title_match else ""
                (DEBUG_DIR / "last_empty.txt").write_text(
                    f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} | URL={url} | parsed_items=0 | title={ttl[:120]} | html_len={len(html or '')}\n",
                    encoding="utf-8"
                )
        except Exception:
            pass
        return JSONResponse(payload)

    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


def normalize_and_sort(items: List[Dict[str, Any]], supplier_priority: Optional[str]) -> List[Dict[str, Any]]:
    # Secondary guard: blocklist filter to ensure unwanted vehicles never appear
    _blocked_models = [
        "Mercedes S Class Auto",
        "MG ZS Auto",
        "Mercedes CLA Coupe Auto",
        "Mercedes A Class",
        "Mercedes A Class Auto",
        "BMW 1 Series Auto",
        "BMW 3 Series SW Auto",
        "Volvo V60 Auto",
        "Volvo XC40 Auto",
        "Mercedes C Class Auto",
        "Tesla Model 3 Auto",
        "Electric",
        "BMW 2 Series Gran Coupe Auto",
        "Mercedes C Class SW Auto",
        "Mercedes E Class Auto",
        "Mercedes E Class SW Auto",
        "BMW 5 Series SW Auto",
        "BMW X1 Auto",
        "Mercedes CLE Coupe Auto",
        "Volkswagen T-Roc Cabrio",
        "Mercedes GLA Auto",
        "Volvo XC60 Auto",
        "Volvo EX30 Auto",
        "BMW 3 Series Auto",
        "Volvo V60 4x4 Auto",
        "Hybrid",
        "Mazda MX5 Cabrio Auto",
        "Mercedes CLA Auto",
    ]
    def _norm_text(s: str) -> str:
        s = (s or "").strip().lower()
        return " ".join(s.replace(",", " ").split())
    _blocked_norm = set(_norm_text(x) for x in _blocked_models)
    import re as _re
    _patterns = [
        r"\bmercedes\s+s\s*class\b",
        r"\bmercedes\s+cla\b",
        r"\bmercedes\s+cle\b",
        r"\bmercedes\s+a\s*class\b",
        r"\bmercedes\s+c\s*class\b",
        r"\bmercedes\s+e\s*class\b",
        r"\bmercedes\s+gla\b",
        r"\bbmw\s+1\s*series\b",
        r"\bbmw\s+2\s*series\b",
        r"\bbmw\s+3\s*series\b",
        r"\bbmw\s+5\s*series\b",
        r"\bbmw\s*x1\b",
        r"\bvolvo\s+v60\b",
        r"\bvolvo\s+xc40\b",
        r"\bvolvo\s+xc60\b",
        r"\bvolvo\s+ex30\b",
        r"\btesla\s+model\s*3\b",
        r"\bmg\s+zs\b",
        r"\bmazda\s+mx5\b",
        r"\bvolkswagen\s+t-roc\b",
        r"\belectric\b",
        r"\bhybrid\b",
    ]
    def _blocked(name: str) -> bool:
        n = _norm_text(name)
        if not n:
            return False
        if n in _blocked_norm:
            return True
        for p in _patterns:
            if _re.search(p, n):
                return True
        for b in _blocked_norm:
            if len(b) >= 6 and b in n:
                return True
        return False

    detailed: List[Dict[str, Any]] = []
    summary: List[Dict[str, Any]] = []
    import re as _re2
    # Use dynamic FX with 1h cache; fallback 1.16
    try:
        GBP_TO_EUR = float(_fx_rate_gbp_eur())
    except Exception:
        GBP_TO_EUR = 1.16
    for it in items:
        if _blocked(it.get("car", "")):
            continue
        price_text_in = it.get("price", "") or ""
        price_num = extract_price_number(price_text_in)
        price_curr = ""
        if "€" in price_text_in or _re2.search(r"\bEUR\b", price_text_in, _re2.I):
            price_curr = "EUR"
        elif "£" in price_text_in or _re2.search(r"\bGBP\b", price_text_in, _re2.I):
            price_curr = "GBP"
        # Convert GBP -> EUR for display and sorting
        if price_curr == "GBP" and price_num is not None:
            try:
                price_num = round(price_num * GBP_TO_EUR, 2)
                price_text_in = f"€{price_num:.2f}"
                price_curr = "EUR"
            except Exception:
                pass
        row = {
            "supplier": it.get("supplier", ""),
            "car": it.get("car", ""),
            "price": price_text_in,
            "price_num": price_num,
            "currency": price_curr or it.get("currency", ""),
            "category": it.get("category", ""),
            "category_code": it.get("category_code", ""),
            "transmission": it.get("transmission", ""),
            "photo": it.get("photo", ""),
            "link": it.get("link", ""),
        }
        if (row["car"] or "").strip():
            detailed.append(row)
        else:
            summary.append(row)

    def _sort(lst: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        lst.sort(key=lambda x: (
            0 if supplier_priority and supplier_priority.lower() in (x.get("supplier") or "").lower() else 1,
            (x.get("category") or ""),
            x.get("price_num") or 1e15,
        ))
        return lst

    # Prefer detailed per-car rows; if none found, fall back to provider-summary rows
    if detailed:
        return _sort(detailed)
    return _sort(summary)


def extract_price_number(price_str: str) -> Optional[float]:
    if not price_str:
        return None
    s = price_str.replace("\xa0", " ")
    digits = []
    dot_seen = False
    comma_seen = False
    for ch in s:
        if ch.isdigit():
            digits.append(ch)
        elif ch == "." and not dot_seen:
            digits.append(".")
            dot_seen = True
        elif ch == "," and not comma_seen:
            # assume comma as decimal if dot not used
            if not dot_seen:
                digits.append(".")
                comma_seen = True
    try:
        return float("".join(digits)) if digits else None
    except Exception:
        return None


@app.post("/api/track-carjet")
async def track_carjet(request: Request):
    require_auth(request)
    body = await request.json()
    pickup_date: str = body.get("pickupDate")  # YYYY-MM-DD
    pickup_time: str = body.get("pickupTime", "10:00")  # HH:mm
    durations: List[int] = body.get("durations", [1,2,3,4,5,6,7,8,9,14,22,31,60])
    locations: List[Dict[str, Any]] = body.get("locations", [])  # [{name, template?}]
    supplier_priority: Optional[str] = body.get("supplier_priority")
    lang: str = body.get("lang", "en")
    currency: str = body.get("currency", "EUR")

    if not pickup_date or not locations:
        return JSONResponse({"ok": False, "error": "pickupDate and locations are required"}, status_code=400)

    try:
        from datetime import datetime, timedelta
        from playwright.async_api import async_playwright

        async def run():
            results: List[Dict[str, Any]] = []
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context()
                default_headers = {"User-Agent": "Mozilla/5.0 (compatible; PriceTracker/1.0)"}
                await context.set_extra_http_headers(default_headers)
                # Allow all resources to ensure CarJet JS initializes correctly
                await context.route("**/*", lambda route: route.continue_())
                page = await context.new_page()
                page.set_default_navigation_timeout(10000)
                page.set_default_timeout(8000)
                for loc in locations:
                    name = loc.get("name", "")
                    template = loc.get("template", "")
                    loc_block = {"location": name, "durations": []}
                    for d in durations:
                        try:
                            start_dt = datetime.fromisoformat(pickup_date + "T" + pickup_time)
                            end_dt = start_dt + timedelta(days=int(d))
                            # Try direct POST to CarJet first (faster, no headless)
                            html = try_direct_carjet(name, start_dt, end_dt, lang=lang, currency=currency)
                            final_url = "https://www.carjet.com/do/list"
                            # Fallback to Playwright if direct returned empty or no prices
                            if not html or len(parse_prices(html, final_url)) == 0:
                                html, final_url = await fetch_carjet_results(page, name, start_dt, end_dt, lang, currency, template)
                            items = parse_prices(html, final_url)
                            items = normalize_and_sort(items, supplier_priority)
                            save_snapshots(name, start_dt, d, items, currency)
                            loc_block["durations"].append({
                                "days": d,
                                "count": len(items),
                                "items": items,
                            })
                        except Exception as e:
                            loc_block["durations"].append({
                                "days": d,
                                "error": str(e),
                                "items": [],
                            })
                    results.append(loc_block)
                await browser.close()
            return results

        results = await run()
        return JSONResponse({"ok": True, "results": results})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


async def fetch_carjet_results(page, location_name, start_dt, end_dt, lang: str, currency: str, template: str):
    try:
        captured_html: Optional[str] = None
        captured_url: Optional[str] = None
        captured_post: Optional[Dict[str, Any]] = None

        async def on_response(resp):
            nonlocal captured_html, captured_url
            try:
                url = resp.url
                if ("/do/list" in url or "/carList.asp" in url) and resp.status == 200 and captured_html is None:
                    text = await resp.text()
                    if text:
                        captured_html = text
                        captured_url = url
            except Exception:
                pass

        # register response listener (use asyncio.create_task for awaiting inside handler)
        page.on("response", lambda r: asyncio.create_task(on_response(r)))
        # capture the first POST payload to /do/list to replay if needed
        def _on_request(req):
            nonlocal captured_post
            try:
                if ("/do/list" in req.url or "/carList.asp" in req.url) and req.method == "POST" and captured_post is None:
                    captured_post = {"url": req.url, "post": req.post_data or ""}
            except Exception:
                pass
        page.on("request", _on_request)
        if template:
            url = (
                template
                .replace("{pickup_date}", start_dt.strftime("%Y-%m-%d"))
                .replace("{pickup_time}", start_dt.strftime("%H:%M"))
                .replace("{dropoff_date}", end_dt.strftime("%Y-%m-%d"))
                .replace("{dropoff_time}", end_dt.strftime("%H:%M"))
                .replace("{location}", location_name)
            )
            await page.goto(url, wait_until="domcontentloaded")
        else:
            # Prefer PT site always for consistency with parsing/selectors
            lang = (lang or "pt").lower()
            if lang not in ("pt", "en", "es", "fr", "de", "it", "nl"):
                lang = "pt"
            base = f"https://www.carjet.com/{lang}/"
            await page.goto(base, wait_until="domcontentloaded")
            try:
                await page.wait_for_timeout(700)
                # Try to accept cookie banner if present
                try:
                    cookies_btn = page.get_by_role("button", name=re.compile("accept|agree|aceitar|ok", re.I)).first
                    if await cookies_btn.count() > 0:
                        await cookies_btn.click()
                        await page.wait_for_timeout(300)
                except Exception:
                    pass
                # Ensure PT language is active to set correct cookies/session
                try:
                    # If not already on /pt/ path, click Portuguese link
                    if not re.search(r"/pt/", page.url):
                        lang_link = page.locator("a[hreflang='pt']").first
                        if await lang_link.count() == 0:
                            lang_link = page.get_by_role("link", name=re.compile("Portugu[eê]s", re.I)).first
                        if await lang_link.count() == 0:
                            lang_link = page.locator("a[href*='/pt/']").first
                        if await lang_link.count() > 0:
                            await lang_link.click()
                            try:
                                await page.wait_for_url(re.compile(r"/pt/"), timeout=4000)
                            except Exception:
                                pass
                            await page.wait_for_timeout(400)
                except Exception:
                    pass
                # Try location input
                loc_input = page.get_by_placeholder("Pick-up location")
                if await loc_input.count() == 0:
                    loc_input = page.locator("input[name*='pickup']")
                if await loc_input.count() == 0:
                    loc_input = page.locator("#pickup")
                await loc_input.click()
                await loc_input.fill(location_name)
                await page.wait_for_timeout(900)
                # Prefer clicking the first autocomplete option if available
                try:
                    # CarJet PT uses #recogida_lista li for suggestions
                    first_opt = page.locator("#recogida_lista li").first
                    if await first_opt.count() == 0:
                        first_opt = page.locator("[role='listbox'] [role='option']").first
                    if await first_opt.count() > 0:
                        await first_opt.click()
                        # extract data attributes from option and populate hidden fields if present
                        try:
                            data = await first_opt.evaluate("(el)=>{const d=el.dataset||{};return {id:d.id||d.dstId||d.zoneId||'', zone:d.zone||d.zoneCode||''};}")
                            await page.evaluate("(vals)=>{const set=(id,val)=>{const el=document.getElementById(id); if(el){ el.value=val; }}; set('dst_id', vals.id); set('zoneCode', vals.zone); set('pickupId', vals.id); }", data)
                        except Exception:
                            pass
                    else:
                        await page.keyboard.press("Enter")
                except Exception:
                    await page.keyboard.press("Enter")
            except Exception:
                pass
            # Force known internal codes for target locations if inputs exist
            try:
                code_map = {
                    "Albufeira": "ABF01",
                    "Albufeira Cidade": "ABF01",
                    "Faro Airport": "FAO02",
                    "Faro Aeroporto": "FAO02",
                }
                dst_code = code_map.get(location_name, "")
                if dst_code:
                    await page.evaluate(
                        "(dst)=>{\n"
                        "  const setVal=(id,val)=>{const el=document.getElementById(id); if(el){ el.value=val; el.dispatchEvent(new Event('change',{bubbles:true})); }};\n"
                        "  setVal('pickupId', dst); setVal('dst_id', dst); setVal('zoneCode', dst);\n"
                        "}",
                        dst_code,
                    )
            except Exception:
                pass
            # Pickup date
            try:
                # Try to set date inputs directly if present (various IDs)
                pickup_str_dmY = start_dt.strftime("%d/%m/%Y")
                dropoff_str_dmY = end_dt.strftime("%d/%m/%Y")
                await page.evaluate("(ids, val) => { for (const id of ids){ const el=document.getElementById(id) || document.querySelector('[name='+id+']'); if(el){ el.removeAttribute && el.removeAttribute('readonly'); el.value=val; el.dispatchEvent && el.dispatchEvent(new Event('input',{bubbles:true})); el.dispatchEvent && el.dispatchEvent(new Event('change',{bubbles:true})); } } }", ["fechaRecogida","pickupDate","date_from"], pickup_str_dmY)
            except Exception:
                pass
            try:
                await page.evaluate("(ids, val) => { for (const id of ids){ const el=document.getElementById(id) || document.querySelector('[name='+id+']'); if(el){ el.removeAttribute && el.removeAttribute('readonly'); el.value=val; el.dispatchEvent && el.dispatchEvent(new Event('input',{bubbles:true})); el.dispatchEvent && el.dispatchEvent(new Event('change',{bubbles:true})); } } }", ["fechaEntrega","fechaDevolucion","dropoffDate","date_to"], dropoff_str_dmY)
            except Exception:
                pass
            # Pickup/Dropoff time
            try:
                await page.evaluate("(ids, val) => { for (const id of ids){ const el=document.getElementById(id) || document.querySelector('[name='+id+']'); if(el){ el.value=val; el.dispatchEvent && el.dispatchEvent(new Event('change',{bubbles:true})); } } }", ["fechaRecogidaSelHour","h-recogida","pickupTime","time_from"], start_dt.strftime("%H:%M"))
            except Exception:
                pass
            try:
                await page.evaluate("(ids, val) => { for (const id of ids){ const el=document.getElementById(id) || document.querySelector('[name='+id+']'); if(el){ el.value=val; el.dispatchEvent && el.dispatchEvent(new Event('change',{bubbles:true})); } } }", ["fechaEntregaSelHour","h-devolucion","dropoffTime","time_to"], end_dt.strftime("%H:%M"))
            except Exception:
                pass
            # Submit search
            try:
                # Prefer submitting the main search form if present
                form = page.locator("form[name='menu_tarifas']")
                if await form.count() > 0:
                    # some sites rely on JS; try clicking the booking form button
                    btn = page.locator("#booking_form .btn-search").first
                    if await btn.count() > 0:
                        await btn.click()
                    else:
                        # fallback to form submit button
                        btn = form.locator("button[type='submit'], input[type='submit']").first
                        if await btn.count() > 0:
                            await btn.click()
                        else:
                            await page.evaluate("sel=>{const f=document.querySelector(sel); f && f.submit();}", "form[name='menu_tarifas']")
                else:
                    # If the page defines submit_fechas(action) use it to ensure s/b tokens are added
                    used_native = await page.evaluate("() => { try { if (typeof submit_fechas === 'function') { submit_fechas('/do/list/pt'); return true; } } catch(e){} return false; }")
                    if not used_native:
                        btn = page.get_by_role("button", name=re.compile("search|continue|find|atualizar|update", re.I))
                        if await btn.count() == 0:
                            btn = page.locator("button[type='submit']")
                        await btn.click()
            except Exception:
                pass
            # As a final nudge, try native submit one more time
            try:
                await page.evaluate("() => { try { if (typeof submit_fechas === 'function') { submit_fechas('/do/list/pt'); } } catch(e){} }")
            except Exception:
                pass
            # If still no request fired, serialize and submit the form directly
            try:
                await page.evaluate("""
                () => {
                  const form = document.querySelector("form[name='menu_tarifas']") || document.querySelector("#booking_form");
                  if (form) {
                    try { form.dispatchEvent(new Event('submit', {bubbles:true,cancelable:true})); } catch(e){}
                    try { form.submit(); } catch(e){}
                  }
                }
                """)
            except Exception:
                pass
            # Wait for results list
            try:
                # Prefer waiting for the actual network response and capture its body
                resp = await page.wait_for_response(lambda r: ("/do/list" in r.url or "/carList.asp" in r.url) and r.status == 200, timeout=25000)
                try:
                    body = await resp.text()
                    if body:
                        captured_html = body
                        captured_url = resp.url
                except Exception:
                    pass
                # Also ensure URL change if applicable
                await page.wait_for_url(re.compile(r"(/do/list|/carList\.asp)"), timeout=5000)
            except Exception:
                pass
            # Wait for any price-like selector quickly
            try:
                await page.wait_for_selector(".price, .amount, [class*='price']", timeout=15000)
            except Exception:
                pass
        # Prefer captured network HTML if present
        if captured_html:
            html = captured_html
            current_url = captured_url or page.url
        else:
            # If we saw the POST payload but didn't capture body, fetch via in-page fetch using same cookies/session
            if captured_post and captured_post.get("url"):
                try:
                    js = """
                    async (u, body) => {
                      const resp = await fetch(u, { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body: body });
                      return await resp.text();
                    }
                    """
                    html = await page.evaluate(js, captured_post["url"], captured_post.get("post", ""))
                    current_url = captured_post["url"]
                except Exception:
                    html = await page.content()
                    current_url = page.url
            else:
                html = await page.content()
                current_url = page.url
        return html, current_url
    finally:
        pass


@app.get("/api/debug_html")
async def debug_html(request: Request):
    params = request.query_params
    location = params.get("location", "Albufeira")
    pickup_date = params.get("date")
    pickup_time = params.get("time", "10:00")
    days = int(params.get("days", 1))
    lang = params.get("lang", "en")
    currency = params.get("currency", "EUR")
    if not pickup_date:
        return JSONResponse({"ok": False, "error": "Missing date (YYYY-MM-DD)"}, status_code=400)

    try:
        from datetime import datetime, timedelta
        from playwright.async_api import async_playwright

        async def run_once():
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context()
                await context.set_extra_http_headers({"User-Agent": "Mozilla/5.0 (compatible; PriceTracker/1.0)"})
                # block heavy resources for speed
                await context.route("**/*", lambda route: (
                    route.abort() if route.request.resource_type in {"image", "media", "font"} else route.continue_()
                ))
                page = await context.new_page()
                page.set_default_navigation_timeout(10000)
                page.set_default_timeout(8000)
                start_dt = datetime.fromisoformat(pickup_date + "T" + pickup_time)
                end_dt = start_dt + timedelta(days=days)
                html, final_url = await fetch_carjet_results(page, location, start_dt, end_dt, lang, currency, template="")
                await browser.close()
                return html, final_url

        html, final_url = await run_once()
        # Save to debug file
        from datetime import datetime as _dt
        stamp = _dt.utcnow().strftime("%Y%m%dT%H%M%S")
        filename = f"debug-{location.replace(' ', '-')}-{pickup_date}-{days}d.html"
        out_path = DEBUG_DIR / filename
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(html)

        # Quick selector counts and dataMap presence
        soup = BeautifulSoup(html, "lxml")
        counts = {
            ".price": len(soup.select(".price")),
            ".amount": len(soup.select(".amount")),
            "[class*='price']": len(soup.select("[class*='price']")),
            "a[href]": len(soup.select("a[href]")),
        }
        try:
            import json as _json
            m = re.search(r"var\s+dataMap\s*=\s*(\[.*?\]);", html, re.S)
            if m:
                arr = _json.loads(m.group(1))
                counts["has_dataMap"] = True
                counts["dataMap_len"] = len(arr)
            else:
                counts["has_dataMap"] = False
                counts["dataMap_len"] = 0
        except Exception:
            counts["has_dataMap"] = False
            counts["dataMap_len"] = 0
        return JSONResponse({
            "ok": True,
            "url": final_url,
            "debug_file": f"/static/debug/{filename}",
            "counts": counts,
        })
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


def save_snapshots(location: str, start_dt, days: int, items: List[Dict[str, Any]], currency: str):
    from datetime import datetime
    ts = datetime.utcnow().isoformat(timespec="seconds")
    with _db_lock:
        conn = sqlite3.connect(DB_PATH)
        try:
            for it in items:
                conn.execute(
                    """
                    INSERT INTO price_snapshots (ts, location, pickup_date, pickup_time, days, supplier, car, price_text, price_num, currency, link)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        ts,
                        location,
                        start_dt.strftime("%Y-%m-%d"),
                        start_dt.strftime("%H:%M"),
                        int(days),
                        (it.get("supplier") or "").strip(),
                        (it.get("car") or "").strip(),
                        (it.get("price") or "").strip(),
                        it.get("price_num"),
                        currency or (it.get("currency") or ""),
                        (it.get("link") or "").strip(),
                    ),
                )
        finally:
            conn.commit()
            conn.close()


@app.get("/api/history")
async def get_history(request: Request):
    require_auth(request)
    params = request.query_params
    location = params.get("location")
    supplier = params.get("supplier")
    days = params.get("days")
    since = params.get("from")
    until = params.get("to")
    limit = int(params.get("limit", 200))

    q = "SELECT ts, location, pickup_date, pickup_time, days, supplier, car, price_text, price_num, currency, link FROM price_snapshots WHERE 1=1"
    args: List[Any] = []
    if location:
        q += " AND location = ?"
        args.append(location)
    if supplier:
        q += " AND supplier LIKE ?"
        args.append(f"%{supplier}%")
    if days:
        q += " AND days = ?"
        args.append(int(days))
    if since:
        q += " AND ts >= ?"
        args.append(since)
    if until:
        q += " AND ts <= ?"
        args.append(until)
    q += " ORDER BY ts DESC LIMIT ?"
    args.append(limit)

    with _db_lock:
        conn = sqlite3.connect(DB_PATH)
        try:
            rows = conn.execute(q, tuple(args)).fetchall()
        finally:
            conn.close()

    items = [
        {
            "ts": r[0],
            "location": r[1],
            "pickup_date": r[2],
            "pickup_time": r[3],
            "days": r[4],
            "supplier": r[5],
            "car": r[6],
            "price": r[7],
            "price_num": r[8],
            "currency": r[9],
            "link": r[10],
        }
        for r in rows
    ]
    return JSONResponse({"ok": True, "count": len(items), "items": items})
