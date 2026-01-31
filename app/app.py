import os
import time
from typing import Any, Dict, Optional

import httpx
from fastapi import FastAPI, Header, HTTPException, Query, Request

app = FastAPI()

MODE = os.getenv("MODE", "radarr").lower()  # radarr|sonarr
SHIM_API_KEY = os.getenv("SHIM_API_KEY", "")

OVERSEERR_URL = os.getenv("OVERSEERR_URL", "").rstrip("/")
OVERSEERR_API_KEY = os.getenv("OVERSEERR_API_KEY", "")
OVERSEERR_USER_ID = int(os.getenv("OVERSEERR_USER_ID", "1"))

TMDB_API_KEY = os.getenv("TMDB_API_KEY", "")
DEFAULT_TV_SEASONS = os.getenv("DEFAULT_TV_SEASONS", "all").lower()  # all|first
DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"


def require_api_key(x_api_key: Optional[str], apikey: Optional[str]):
    provided = x_api_key or apikey
    if SHIM_API_KEY and provided != SHIM_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


async def overseerr_request(media_type: str, tmdb_id: int):
    if not OVERSEERR_URL or not OVERSEERR_API_KEY:
        raise HTTPException(status_code=500, detail="Overseerr not configured (OVERSEERR_URL/OVERSEERR_API_KEY)")

    payload: Dict[str, Any] = {
        "mediaType": media_type,
        "mediaId": tmdb_id,
        "userId": OVERSEERR_USER_ID,
    }

    if media_type == "tv":
        if DEFAULT_TV_SEASONS == "all":
            payload["seasons"] = "all"
        elif DEFAULT_TV_SEASONS == "first":
            payload["seasons"] = [1]

    if DRY_RUN:
        return {"dry_run": True, "would_request": payload}

    headers = {"X-Api-Key": OVERSEERR_API_KEY, "Content-Type": "application/json", "Accept": "application/json"}

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(f"{OVERSEERR_URL}/api/v1/request", json=payload, headers=headers)

    if 200 <= r.status_code < 300:
        return r.json() if r.text else {"ok": True}

    raise HTTPException(status_code=502, detail=f"Overseerr error {r.status_code}: {r.text}")


async def tmdb_from_tvdb(tvdb_id: int) -> Optional[int]:
    if not TMDB_API_KEY:
        return None

    url = f"https://api.themoviedb.org/3/find/{tvdb_id}"
    params = {"api_key": TMDB_API_KEY, "external_source": "tvdb_id"}

    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
        data = r.json()

    tv_results = data.get("tv_results") or []
    if not tv_results:
        return None
    return int(tv_results[0]["id"])


@app.get("/health")
def health():
    return {"ok": True, "mode": MODE}


@app.get("/api/v3/system/status")
def status(
    x_api_key: Optional[str] = Header(default=None),
    apikey: Optional[str] = Query(default=None)
):
    require_api_key(x_api_key, apikey)
    return {
        "version": "5.0.0.0",
        "buildTime": "2026-01-01T00:00:00Z",
        "isDebug": False,
        "isProduction": True,
        "isAdmin": True,
        "appName": "kometa-arr-shim",
        "instanceName": f"kometa-{MODE}-shim",
    }


@app.get("/api/v3/rootfolder")
def rootfolders(
    x_api_key: Optional[str] = Header(default=None),
    apikey: Optional[str] = Query(default=None)
):
    require_api_key(x_api_key, apikey)
    if MODE == "radarr":
        return [{"id": 1, "path": "/movies"}]
    return [{"id": 1, "path": "/tv"}]


@app.get("/api/v3/rootFolder")
def rootfolders_alias(
    x_api_key: Optional[str] = Header(default=None),
    apikey: Optional[str] = Query(default=None)
):
    return rootfolders(x_api_key=x_api_key, apikey=apikey)


@app.get("/api/v3/qualityprofile")
def qualityprofiles(
    x_api_key: Optional[str] = Header(default=None),
    apikey: Optional[str] = Query(default=None)
):
    require_api_key(x_api_key, apikey)
    return [{"id": 1, "name": "Any"}]


@app.get("/api/v3/qualityProfile")
def qualityprofiles_alias(
    x_api_key: Optional[str] = Header(default=None),
    apikey: Optional[str] = Query(default=None)
):
    return qualityprofiles(x_api_key=x_api_key, apikey=apikey)


@app.get("/api/v3/tag")
def list_tags(
    x_api_key: Optional[str] = Header(default=None),
    apikey: Optional[str] = Query(default=None)
):
    require_api_key(x_api_key, apikey)
    return []


@app.post("/api/v3/tag")
async def create_tag(
    request: Request,
    x_api_key: Optional[str] = Header(default=None),
    apikey: Optional[str] = Query(default=None)
):
    require_api_key(x_api_key, apikey)
    body = await request.json()
    label = body.get("label", "kometa")
    return {"id": 1, "label": label}


# -------- Radarr-style exclusions --------

@app.get("/api/v3/exclusions")
def get_exclusions(
    x_api_key: Optional[str] = Header(default=None),
    apikey: Optional[str] = Query(default=None)
):
    require_api_key(x_api_key, apikey)
    return []


@app.post("/api/v3/exclusions")
async def add_exclusion(
    request: Request,
    x_api_key: Optional[str] = Header(default=None),
    apikey: Optional[str] = Query(default=None)
):
    require_api_key(x_api_key, apikey)
    body = await request.json()
    return {"id": int(time.time()), **body}


@app.post("/api/v3/movie/import")
async def movie_import(
    request: Request,
    x_api_key: Optional[str] = Header(default=None),
    apikey: Optional[str] = Query(default=None)
):
    require_api_key(x_api_key, apikey)
    if MODE != "radarr":
        raise HTTPException(status_code=404, detail="Not in radarr mode")

    body = await request.json()

    # Radarr can send a list of movies or a dict wrapper.
    items = body
    if isinstance(body, dict):
        # sometimes wraps in {"movies":[...]} or similar
        items = body.get("movies") or body.get("movie") or body.get("importListMovies") or []
        if not items:
            # could be a single movie dict
            items = [body]

    if not isinstance(items, list):
        items = [items]

    results = []
    for it in items:
        tmdb_id = None
        if isinstance(it, dict):
            tmdb_id = it.get("tmdbId") or it.get("tmdb_id")
            # sometimes nested as {"movie":{"tmdbId":...}}
            if tmdb_id is None and isinstance(it.get("movie"), dict):
                tmdb_id = it["movie"].get("tmdbId") or it["movie"].get("tmdb_id")

        if not tmdb_id:
            results.append({"ok": False, "msg": "missing tmdbId", "item": it})
            continue

        try:
            await overseerr_request("movie", int(tmdb_id))
            results.append({"ok": True, "tmdbId": int(tmdb_id)})
        except Exception as e:
            results.append({"ok": False, "tmdbId": int(tmdb_id), "msg": str(e)})

    # Return something Kometa will accept as "import succeeded"
    return {
        "imported": sum(1 for r in results if r.get("ok")),
        "failed": sum(1 for r in results if not r.get("ok")),
        "results": results,
    }


@app.get("/api/v3/series")
def list_series(
    x_api_key: Optional[str] = Header(default=None),
    apikey: Optional[str] = Query(default=None)
):
    require_api_key(x_api_key, apikey)
    if MODE != "sonarr":
        return []
    return []

@app.get("/api/v3/series/lookup")
async def series_lookup(
    term: str,
    x_api_key: Optional[str] = Header(default=None),
    apikey: Optional[str] = Query(default=None)
):
    require_api_key(x_api_key, apikey)
    if MODE != "sonarr":
        return []

    if not term.lower().startswith("tvdb:"):
        return []

    if not TMDB_API_KEY:
        raise HTTPException(status_code=400, detail="TMDB_API_KEY is required for /series/lookup")

    tvdb_id = int(term.split(":", 1)[1])

    # Convert TVDB -> TMDb
    tmdb_id = await tmdb_from_tvdb(tvdb_id)
    if tmdb_id is None:
        return []

    # Fetch TV details from TMDb
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(
            f"https://api.themoviedb.org/3/tv/{tmdb_id}",
            params={"api_key": TMDB_API_KEY}
        )
        if r.status_code == 404:
            return []
        r.raise_for_status()
        s = r.json()

    title = s.get("name") or s.get("original_name") or "Unknown"
    first_air_date = s.get("first_air_date") or ""
    year = int(first_air_date.split("-")[0]) if first_air_date else 0
    poster_path = s.get("poster_path")

    result = {
        "title": title,
        "tvdbId": tvdb_id,
        "year": year,
        "titleSlug": f"tvdb-{tvdb_id}",
        "images": (
            [{"coverType": "poster", "url": f"https://image.tmdb.org/t/p/original{poster_path}"}]
            if poster_path else []
        ),
        # Sonarr sometimes expects these fields to exist
        "seasonFolder": True,
        "seriesType": "standard",
    }

    return [result]


@app.post("/api/v3/series/import")
async def series_import(
    request: Request,
    x_api_key: Optional[str] = Header(default=None),
    apikey: Optional[str] = Query(default=None)
):
    require_api_key(x_api_key, apikey)
    if MODE != "sonarr":
        raise HTTPException(status_code=404, detail="Not in sonarr mode")

    body = await request.json()

    # Sonarr can send a list, or a wrapper dict, or a single object.
    items = body
    if isinstance(body, dict):
        items = (
            body.get("series")
            or body.get("shows")
            or body.get("importListSeries")
            or body.get("importListItems")
            or []
        )
        if not items:
            items = [body]

    if not isinstance(items, list):
        items = [items]

    results = []
    for it in items:
        tvdb_id = None

        if isinstance(it, dict):
            tvdb_id = it.get("tvdbId") or it.get("tvdb_id")
            # sometimes nested
            if tvdb_id is None and isinstance(it.get("series"), dict):
                tvdb_id = it["series"].get("tvdbId") or it["series"].get("tvdb_id")

        if not tvdb_id:
            results.append({"ok": False, "msg": "missing tvdbId", "item": it})
            continue

        # Convert TVDB -> TMDb (Overseerr wants TMDb)
        tmdb_id = await tmdb_from_tvdb(int(tvdb_id))
        if tmdb_id is None:
            results.append({"ok": False, "tvdbId": int(tvdb_id), "msg": "tvdb->tmdb conversion failed"})
            continue

        try:
            await overseerr_request("tv", int(tmdb_id))
            results.append({"ok": True, "tvdbId": int(tvdb_id), "tmdbId": int(tmdb_id)})
        except Exception as e:
            results.append({"ok": False, "tvdbId": int(tvdb_id), "tmdbId": int(tmdb_id), "msg": str(e)})

    return {
        "imported": sum(1 for r in results if r.get("ok")),
        "failed": sum(1 for r in results if not r.get("ok")),
        "results": results,
    }





# -------- Sonarr-style import list exclusions --------

@app.get("/api/v3/importlistexclusion")
def get_import_list_exclusions(
    x_api_key: Optional[str] = Header(default=None),
    apikey: Optional[str] = Query(default=None)
):
    require_api_key(x_api_key, apikey)
    return []


@app.post("/api/v3/importlistexclusion")
async def add_import_list_exclusion(
    request: Request,
    x_api_key: Optional[str] = Header(default=None),
    apikey: Optional[str] = Query(default=None)
):
    require_api_key(x_api_key, apikey)
    body = await request.json()
    return {"id": int(time.time()), **body}

@app.get("/api/v3/movie")
def list_movies(
    x_api_key: Optional[str] = Header(default=None),
    apikey: Optional[str] = Query(default=None)
):
    require_api_key(x_api_key, apikey)
    if MODE != "radarr":
        # Sonarr shim shouldn't claim it has /movie
        return []
    return []

@app.get("/api/v3/series")
def list_series(
    x_api_key: Optional[str] = Header(default=None),
    apikey: Optional[str] = Query(default=None)
):
    require_api_key(x_api_key, apikey)
    if MODE != "sonarr":
        return []
    return []

@app.get("/api/v3/movie/lookup")
async def movie_lookup(
    term: str,
    x_api_key: Optional[str] = Header(default=None),
    apikey: Optional[str] = Query(default=None)
):
    require_api_key(x_api_key, apikey)
    if MODE != "radarr":
        return []

    # term will look like "tmdb:12345"
    if not term.lower().startswith("tmdb:"):
        return []

    if not TMDB_API_KEY:
        raise HTTPException(status_code=400, detail="TMDB_API_KEY is required for /movie/lookup")

    tmdb_id = int(term.split(":", 1)[1])

    # Fetch movie details from TMDb
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(
            f"https://api.themoviedb.org/3/movie/{tmdb_id}",
            params={"api_key": TMDB_API_KEY}
        )
        if r.status_code == 404:
            return []
        r.raise_for_status()
        m = r.json()

    title = m.get("title") or m.get("original_title") or "Unknown"
    release_date = m.get("release_date") or ""
    year = int(release_date.split("-")[0]) if release_date else 0
    poster_path = m.get("poster_path")

    result = {
        "title": title,
        "year": year,
        "tmdbId": tmdb_id,
        "titleSlug": f"tmdb-{tmdb_id}",
        "images": (
            [{"coverType": "poster", "url": f"https://image.tmdb.org/t/p/original{poster_path}"}]
            if poster_path else []
        ),
    }

    return [result]




# -------- Intercept add calls --------

@app.post("/api/v3/movie")
async def add_movie(
    request: Request,
    x_api_key: Optional[str] = Header(default=None),
    apikey: Optional[str] = Query(default=None)
):
    require_api_key(x_api_key, apikey)
    if MODE != "radarr":
        raise HTTPException(status_code=404, detail="Not in radarr mode")

    body = await request.json()
    tmdb_id = body.get("tmdbId") or body.get("tmdb_id")
    if not tmdb_id:
        raise HTTPException(status_code=400, detail="Missing tmdbId in Radarr add payload")

    await overseerr_request("movie", int(tmdb_id))

    return {
        "id": int(time.time()),
        "title": body.get("title", "Unknown"),
        "tmdbId": int(tmdb_id),
        "monitored": body.get("monitored", True),
        "path": body.get("path", ""),
        "added": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


@app.post("/api/v3/series")
async def add_series(
    request: Request,
    x_api_key: Optional[str] = Header(default=None),
    apikey: Optional[str] = Query(default=None)
):
    require_api_key(x_api_key, apikey)
    if MODE != "sonarr":
        raise HTTPException(status_code=404, detail="Not in sonarr mode")

    body = await request.json()
    tvdb_id = body.get("tvdbId") or body.get("tvdb_id")
    if not tvdb_id:
        raise HTTPException(status_code=400, detail="Missing tvdbId in Sonarr add payload")

    tmdb_id = await tmdb_from_tvdb(int(tvdb_id))
    if tmdb_id is None:
        raise HTTPException(status_code=400, detail="Could not convert tvdbId -> tmdbId (set TMDB_API_KEY)")

    await overseerr_request("tv", tmdb_id)

    return {
        "id": int(time.time()),
        "title": body.get("title", "Unknown"),
        "tvdbId": int(tvdb_id),
        "monitored": body.get("monitored", True),
        "path": body.get("path", ""),
        "added": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
