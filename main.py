from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import httpx
import asyncio
import os
from datetime import datetime, date
from calendar import monthrange
from pytrends.request import TrendReq
import json

app = FastAPI(title="Jellyfish Outbreak API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_origin_regex=".*",
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# ── Keys from environment variables ──────────────────────────────────────────
# NOTE: keys are loaded at request time to pick up Render env vars correctly
def get_yt_key():  return os.getenv("YOUTUBE_API_KEY", "")
def get_mc_key():  return os.getenv("MEDIACLOUD_API_KEY", "")

# ── Region definitions ────────────────────────────────────────────────────────
REGIONS = {
    "mediterranean": {"lat1": 30, "lat2": 46, "lng1": -6,  "lng2": 36,  "geo": "mediterranean sea",  "trends_geo": ""},
    "red_sea":       {"lat1": 12, "lat2": 30, "lng1": 32,  "lng2": 44,  "geo": "red sea",             "trends_geo": "IL"},
    "black_sea":     {"lat1": 40, "lat2": 47, "lng1": 27,  "lng2": 42,  "geo": "black sea",           "trends_geo": "UA"},
    "north_sea":     {"lat1": 51, "lat2": 61, "lng1": -4,  "lng2": 10,  "geo": "north sea",           "trends_geo": "GB"},
    "atlantic":      {"lat1": 20, "lat2": 60, "lng1": -20, "lng2": -5,  "geo": "atlantic ocean",      "trends_geo": "PT"},
    "pacific":       {"lat1": 20, "lat2": 50, "lng1": 120, "lng2": 180, "geo": "pacific ocean",       "trends_geo": "JP"},
}

TAXA = {
    "scyphozoa": 47534,   # מדוזות אמיתיות
    "medusozoa": 47533,   # כל המדוזות
    "physalia":  118313,  # ספינת מלחמה פורטוגלית
    "cubozoa":   47804,   # מדוזות קופסה
    "hydrozoa":  47534,   # הידרוזואה - using closest available
    "jellyfish":  47533,  # jellyfish (general) - same as medusozoa
}


# ── iNaturalist ───────────────────────────────────────────────────────────────
async def fetch_inat_month(client, taxon_id, region, year, month):
    params = {
        "taxon_id": taxon_id,
        "swlat": region["lat1"], "swlng": region["lng1"],
        "nelat": region["lat2"], "nelng": region["lng2"],
        "year": year, "month": month,
        "per_page": 1, "only_id": "true",
    }
    try:
        r = await client.get("https://api.inaturalist.org/v1/observations", params=params, timeout=15)
        return r.json().get("total_results", 0)
    except Exception:
        return 0


async def fetch_inat_recent(client, taxon_id, region, limit=6):
    params = {
        "taxon_id": taxon_id,
        "swlat": region["lat1"], "swlng": region["lng1"],
        "nelat": region["lat2"], "nelng": region["lng2"],
        "per_page": limit,
        "order_by": "created_at", "order": "desc",
    }
    try:
        r = await client.get("https://api.inaturalist.org/v1/observations", params=params, timeout=15)
        results = r.json().get("results", [])
        return [
            {
                "id": o["id"],
                "taxon": o.get("taxon", {}).get("preferred_common_name") or o.get("taxon", {}).get("name", ""),
                "place": o.get("place_guess", ""),
                "date": o.get("observed_on") or o.get("created_at", "")[:10],
                "photo": (o.get("photos") or [{}])[0].get("url", "").replace("square", "small"),
                "url": f"https://www.inaturalist.org/observations/{o['id']}",
            }
            for o in results
        ]
    except Exception:
        return []


@app.get("/api/inaturalist")
async def inaturalist(
    region: str = Query("mediterranean"),
    taxon: str = Query("scyphozoa"),
    year: int = Query(None),
):
    year = year or datetime.now().year
    reg = REGIONS.get(region, REGIONS["mediterranean"])
    taxon_id = TAXA.get(taxon, TAXA["scyphozoa"])

    async with httpx.AsyncClient() as client:
        monthly = await asyncio.gather(*[
            fetch_inat_month(client, taxon_id, reg, year, m)
            for m in range(1, 13)
        ])
        recent = await fetch_inat_recent(client, taxon_id, reg)

    return {
        "source": "inaturalist",
        "status": "live",
        "monthly": list(monthly),
        "total": sum(monthly),
        "recent": recent,
    }


# ── YouTube ───────────────────────────────────────────────────────────────────
async def fetch_yt_month(client, geo, year, month, key):
    days = monthrange(year, month)[1]
    after  = f"{year}-{month:02d}-01T00:00:00Z"
    before = f"{year}-{month:02d}-{days:02d}T23:59:59Z"
    params = {
        "part": "snippet",
        "q": f"jellyfish {geo}",
        "type": "video",
        "maxResults": 50,
        "order": "date",
        "publishedAfter": after,
        "publishedBefore": before,
        "key": key,
    }
    try:
        r = await client.get("https://www.googleapis.com/youtube/v3/search", params=params, timeout=15)
        d = r.json()
        if "error" in d:
            return 0
        return d.get("pageInfo", {}).get("totalResults", len(d.get("items", [])))
    except Exception:
        return 0


async def fetch_yt_recent(client, geo, key, limit=5):
    params = {
        "part": "snippet",
        "q": f"jellyfish {geo}",
        "type": "video",
        "maxResults": limit,
        "order": "date",
        "key": key,
    }
    try:
        r = await client.get("https://www.googleapis.com/youtube/v3/search", params=params, timeout=15)
        items = r.json().get("items", [])
        return [
            {
                "id": i["id"].get("videoId", ""),
                "title": i["snippet"]["title"],
                "channel": i["snippet"]["channelTitle"],
                "date": i["snippet"]["publishedAt"][:10],
                "thumbnail": i["snippet"]["thumbnails"]["default"]["url"],
                "url": f"https://youtube.com/watch?v={i['id'].get('videoId','')}",
            }
            for i in items
        ]
    except Exception:
        return []


@app.get("/api/youtube")
async def youtube(
    region: str = Query("mediterranean"),
    year: int = Query(None),
):
    YT_KEY = get_yt_key()
    if not YT_KEY:
        return {"source": "youtube", "status": "no_key", "monthly": [0]*12, "total": 0, "recent": []}

    year = year or datetime.now().year
    reg  = REGIONS.get(region, REGIONS["mediterranean"])
    geo  = reg["geo"]

    async with httpx.AsyncClient() as client:
        monthly = await asyncio.gather(*[
            fetch_yt_month(client, geo, year, m, YT_KEY)
            for m in range(1, 13)
        ])
        recent = await fetch_yt_recent(client, geo, YT_KEY)

    return {
        "source": "youtube",
        "status": "live",
        "monthly": list(monthly),
        "total": sum(monthly),
        "recent": recent,
    }


# ── MediaCloud ────────────────────────────────────────────────────────────────
async def fetch_mc_month(client, geo, year, month, key):
    days  = monthrange(year, month)[1]
    fq    = f"publish_date:[{year}-{month:02d}-01T00:00:00Z TO {year}-{month:02d}-{days:02d}T23:59:59Z]"
    params = {
        "q": f"jellyfish {geo}",
        "fq": fq,
        "key": key,
    }
    try:
        r = await client.get("https://api.mediacloud.org/api/v2/stories/count", params=params, timeout=15)
        return r.json().get("count", 0)
    except Exception:
        return 0


@app.get("/api/mediacloud")
async def mediacloud(
    region: str = Query("mediterranean"),
    year: int = Query(None),
):
    MC_KEY = get_mc_key()
    if not MC_KEY:
        return {"source": "mediacloud", "status": "no_key", "monthly": [0]*12, "total": 0}

    year = year or datetime.now().year
    reg  = REGIONS.get(region, REGIONS["mediterranean"])
    geo  = reg["geo"]

    async with httpx.AsyncClient() as client:
        monthly = await asyncio.gather(*[
            fetch_mc_month(client, geo, year, m, MC_KEY)
            for m in range(1, 13)
        ])

    return {
        "source": "mediacloud",
        "status": "live",
        "monthly": list(monthly),
        "total": sum(monthly),
    }


# ── Reddit ────────────────────────────────────────────────────────────────────
@app.get("/api/reddit")
async def reddit(region: str = Query("mediterranean"), year: int = Query(None)):
    year = year or datetime.now().year
    reg  = REGIONS.get(region, REGIONS["mediterranean"])
    geo  = reg["geo"]
    queries = [
        f"jellyfish beach {geo}",
        f"jellyfish bloom {geo}",
        f"jellyfish sting {geo}",
    ]
    headers = {"User-Agent": "jellyfish-tracker/1.0"}
    total = 0
    posts = []

    async with httpx.AsyncClient() as client:
        for q in queries:
            try:
                r = await client.get(
                    "https://www.reddit.com/search.json",
                    params={"q": q, "sort": "new", "limit": 25, "t": "year", "type": "link"},
                    headers=headers,
                    timeout=15,
                )
                data = r.json().get("data", {}).get("children", [])
                total += len(data)
                for item in data[:3]:
                    d = item["data"]
                    posts.append({
                        "title": d["title"],
                        "subreddit": d["subreddit"],
                        "score": d["score"],
                        "date": datetime.utcfromtimestamp(d["created_utc"]).strftime("%Y-%m-%d"),
                        "url": f"https://reddit.com{d['permalink']}",
                    })
            except Exception:
                continue

    return {
        "source": "reddit",
        "status": "live" if total > 0 else "empty",
        "total": total,
        "posts": posts[:6],
        "monthly": [round(total / 12)] * 12,
    }


# ── Google Trends ─────────────────────────────────────────────────────────────
@app.get("/api/trends")
async def trends(region: str = Query("mediterranean"), year: int = Query(None)):
    year = year or datetime.now().year
    reg  = REGIONS.get(region, REGIONS["mediterranean"])
    geo  = reg.get("trends_geo", "")

    try:
        pt = TrendReq(hl="en-US", tz=0, timeout=(10, 25))
        timeframe = f"{year}-01-01 {year}-12-31"
        pt.build_payload(["jellyfish"], geo=geo, timeframe=timeframe)
        df = pt.interest_over_time()

        if df.empty:
            raise ValueError("empty")

        # אגרגציה לפי חודש (ממוצע)
        df.index = df.index.to_period("M")
        monthly_raw = df.groupby(df.index)["jellyfish"].mean()
        monthly = [float(monthly_raw.get(f"{year}-{m:02d}", 0)) for m in range(1, 13)]

        return {"source": "trends", "status": "live", "monthly": monthly}
    except Exception as e:
        return {"source": "trends", "status": "error", "error": str(e), "monthly": [0]*12}


# ── Tumblr ────────────────────────────────────────────────────────────────────
@app.get("/api/tumblr")
async def tumblr(region: str = Query("mediterranean")):
    reg = REGIONS.get(region, REGIONS["mediterranean"])
    geo = reg["geo"]
    TUMBLR_KEY = "fuiKNFp9vQFvjLNvx4sUwti4Yb5yGutBN4Xh10LXZhhRKjWlV4"
    posts = []
    total = 0

    async with httpx.AsyncClient() as client:
        for tag in [f"jellyfish {geo}", "jellyfish bloom", "jellyfish"]:
            try:
                r = await client.get(
                    "https://api.tumblr.com/v2/tagged",
                    params={"tag": tag, "api_key": TUMBLR_KEY},
                    timeout=15,
                )
                items = r.json().get("response", [])
                total += len(items)
                for p in items[:2]:
                    posts.append({
                        "title": p.get("summary") or p.get("slug", ""),
                        "blog": p.get("blog_name", ""),
                        "url": p.get("post_url") or p.get("short_url", ""),
                        "date": p.get("date", "")[:10],
                    })
                if total > 0:
                    break
            except Exception:
                continue

    return {
        "source": "tumblr",
        "status": "live" if total > 0 else "empty",
        "total": total,
        "posts": posts[:4],
    }


# ── Combined score ────────────────────────────────────────────────────────────
WEIGHTS = {
    "inaturalist": 0.30,
    "youtube":     0.18,
    "mediacloud":  0.20,
    "reddit":      0.17,
    "trends":      0.15,
}


@app.get("/api/combined")
async def combined(
    region: str = Query("mediterranean"),
    taxon:  str = Query("scyphozoa"),
    year:   int = Query(None),
):
    year = year or datetime.now().year

    # קריאה מקבילית לכל המקורות
    inat_data, yt_data, mc_data, rd_data, tr_data = await asyncio.gather(
        inaturalist(region=region, taxon=taxon, year=year),
        youtube(region=region, year=year),
        mediacloud(region=region, year=year),
        reddit(region=region, year=year),
        trends(region=region, year=year),
    )

    sources = {
        "inaturalist": inat_data["monthly"],
        "youtube":     yt_data["monthly"],
        "mediacloud":  mc_data["monthly"],
        "reddit":      rd_data["monthly"],
        "trends":      tr_data["monthly"],
    }

    # נרמול + weighted average
    def normalize(lst):
        mx = max(lst) if max(lst) > 0 else 1
        return [v / mx * 100 for v in lst]

    scores = [0.0] * 12
    for src, weight in WEIGHTS.items():
        norm = normalize(sources[src])
        for i in range(12):
            scores[i] += norm[i] * weight

    statuses = {
        "inaturalist": inat_data["status"],
        "youtube":     yt_data["status"],
        "mediacloud":  mc_data["status"],
        "reddit":      rd_data["status"],
        "trends":      tr_data["status"],
    }

    return {
        "monthly_scores": [round(s, 1) for s in scores],
        "sources": sources,
        "statuses": statuses,
        "peak_month": scores.index(max(scores)) + 1,
        "current_score": round(scores[datetime.now().month - 1], 1),
    }


@app.get("/")
async def root():
    return {
        "name": "Jellyfish Outbreak API",
        "endpoints": ["/api/inaturalist", "/api/youtube", "/api/mediacloud",
                      "/api/reddit", "/api/trends", "/api/tumblr", "/api/combined"],
        "docs": "/docs",
    }

@app.get("/api/debug")
async def debug():
    """בדיקת סטטוס המפתחות + תשובה גולמית מה-APIs"""
    yt = get_yt_key()
    mc = get_mc_key()
    yt_raw = None
    mc_raw = None

    async with httpx.AsyncClient() as client:
        if yt:
            try:
                r = await client.get(
                    "https://www.googleapis.com/youtube/v3/search",
                    params={"part": "snippet", "q": "jellyfish", "type": "video",
                            "maxResults": 3, "key": yt},
                    timeout=15
                )
                yt_raw = r.json()
            except Exception as e:
                yt_raw = {"error": str(e)}

        if mc:
            try:
                r = await client.get(
                    "https://api.mediacloud.org/api/v2/stories/count",
                    params={"q": "jellyfish", "key": mc},
                    timeout=15
                )
                mc_raw = r.json()
            except Exception as e:
                mc_raw = {"error": str(e)}

    return {
        "youtube_key_set": bool(yt),
        "youtube_key_prefix": yt[:8] + "..." if yt else None,
        "youtube_raw_response": yt_raw,
        "mediacloud_key_set": bool(mc),
        "mediacloud_key_prefix": mc[:8] + "..." if mc else None,
        "mediacloud_raw_response": mc_raw,
        "taxa_available": list(TAXA.keys()),
        "regions_available": list(REGIONS.keys()),
    }

