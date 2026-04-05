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
def get_yt_key():     return os.getenv("YOUTUBE_API_KEY", "AIzaSyBZwGoTnxZpiClo9LNmcnGnoEW2qWraW1s")
def get_yt_keys():
    """מחזיר רשימת כל ה-API keys הזמינים – עד 4"""
    keys = []
    for suffix in ["", "_2", "_3", "_4"]:
        k = os.getenv(f"YOUTUBE_API_KEY{suffix}", "")
        if k:
            keys.append(k)
    return keys if keys else [""]
def get_mc_key():     return os.getenv("MEDIACLOUD_API_KEY", "")
def get_tumblr_key(): return os.getenv("TUMBLR_API_KEY", "fuiKNFp9vQFvjLNvx4sUwti4Yb5yGutBN4Xh10LXZhhRKjWlV4")


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
async def fetch_yt_annual(client, geo, year, keys):
    """
    מביא עד 150 סרטונים עם pagination (3 עמודים × 50).
    משתמש ב-key rotation אם יש מספר מפתחות – מעביר ל-key הבא בעת quota exceeded.
    """
    all_items = []
    next_page_token = None
    pages_fetched = 0
    MAX_PAGES = 3  # 150 סרטונים מקסימום
    key_index = 0
    last_error = None

    base_params = {
        "part": "snippet",
        "q": f"jellyfish {geo}",
        "type": "video",
        "maxResults": 50,
        "order": "date",
        "publishedAfter": f"{year}-01-01T00:00:00Z",
        "publishedBefore": f"{year}-12-31T23:59:59Z",
    }

    while pages_fetched < MAX_PAGES and key_index < len(keys):
        params = {**base_params, "key": keys[key_index]}
        if next_page_token:
            params["pageToken"] = next_page_token

        try:
            r = await client.get(
                "https://www.googleapis.com/youtube/v3/search",
                params=params, timeout=15
            )
            d = r.json()

            if "error" in d:
                err_reason = d["error"].get("errors", [{}])[0].get("reason", "")
                last_error = d["error"].get("message", "unknown")
                if err_reason == "quotaExceeded" and key_index + 1 < len(keys):
                    # נסה key הבא
                    key_index += 1
                    next_page_token = None  # התחל מחדש עם key חדש
                    pages_fetched = 0
                    all_items = []
                    continue
                else:
                    break  # שגיאה אחרת או נגמרו ה-keys

            items = d.get("items", [])
            all_items.extend(items)
            pages_fetched += 1
            next_page_token = d.get("nextPageToken")
            if not next_page_token:
                break  # אין עמוד הבא

        except Exception as e:
            last_error = str(e)
            break

    if not all_items and last_error:
        return None, last_error

    # חלוקה לפי חודש
    monthly = [0] * 12
    for item in all_items:
        pub = item.get("snippet", {}).get("publishedAt", "")
        if pub:
            try:
                m = int(pub[5:7]) - 1
                if 0 <= m < 12:
                    monthly[m] += 1
            except Exception:
                pass

    return monthly, None


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
    yt_keys = get_yt_keys()
    if not any(yt_keys):
        return {"source": "youtube", "status": "no_key", "monthly": [0]*12, "total": 0, "recent": []}

    year = year or datetime.now().year
    reg  = REGIONS.get(region, REGIONS["mediterranean"])
    geo  = reg["geo"]

    async with httpx.AsyncClient() as client:
        monthly, err = await fetch_yt_annual(client, geo, year, yt_keys)
        if err:
            return {"source": "youtube", "status": "error", "error": str(err),
                    "monthly": [0]*12, "total": 0, "recent": []}
        recent = await fetch_yt_recent(client, geo, yt_keys[0])

    return {
        "source": "youtube",
        "status": "live",
        "monthly": monthly,
        "total": sum(monthly),
        "recent": recent,
    }


# ── MediaCloud ────────────────────────────────────────────────────────────────
async def fetch_gdelt_month(client, geo, year, month):
    """GDELT Doc 2.0 API - חינמי, ללא API key, נתונים מ-2015"""
    start = f"{year}{month:02d}01000000"
    days  = monthrange(year, month)[1]
    end   = f"{year}{month:02d}{days:02d}235959"
    params = {
        "query":         f"jellyfish {geo}",
        "mode":          "artlist",
        "maxrecords":    "250",
        "format":        "json",
        "startdatetime": start,
        "enddatetime":   end,
        "sort":          "datedesc",
    }
    try:
        r = await client.get(
            "https://api.gdeltproject.org/api/v2/doc/doc",
            params=params, timeout=20
        )
        data = r.json()
        articles = data.get("articles", [])
        return len(articles)
    except Exception:
        return 0


@app.get("/api/mediacloud")
async def mediacloud(
    region: str = Query("mediterranean"),
    year: int = Query(None),
):
    """GDELT Doc 2.0 API – מחליף את MediaCloud, חינמי וללא API key"""
    year = year or datetime.now().year
    reg  = REGIONS.get(region, REGIONS["mediterranean"])
    geo  = reg["geo"]

    async with httpx.AsyncClient() as client:
        monthly = await asyncio.gather(*[
            fetch_gdelt_month(client, geo, year, m)
            for m in range(1, 13)
        ])

    return {
        "source": "gdelt",
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
async def tumblr(region: str = Query("mediterranean"), year: int = Query(None)):
    year = year or datetime.now().year
    reg  = REGIONS.get(region, REGIONS["mediterranean"])
    geo  = reg["geo"]
    key  = get_tumblr_key()
    posts = []
    total = 0
    monthly = [0] * 12
    last_error = None

    # תגיות ממוקדות למדוזות אמיתיות בטבע – לפי אזור גיאוגרפי
    tags_to_try = [
        f"jellyfish {geo}",
        f"jellyfish sighting {geo}",
        "jellyfish bloom",
        "jellyfish sighting",
        "jellyfish beach",
        "marine biology jellyfish",
        "ocean jellyfish",
        "jellyfish photography",
    ]

    async with httpx.AsyncClient() as client:
        for tag in tags_to_try:
            try:
                r = await client.get(
                    "https://api.tumblr.com/v2/tagged",
                    params={"tag": tag, "api_key": key, "limit": 20},
                    headers={"User-Agent": "jellyfish-tracker/1.0"},
                    timeout=20,
                )
                if r.status_code != 200:
                    last_error = f"HTTP {r.status_code}"
                    continue

                data = r.json()
                # Tumblr returns error in meta field
                meta_status = data.get("meta", {}).get("status", 200)
                if meta_status != 200:
                    last_error = data.get("meta", {}).get("msg", "unknown error")
                    continue

                items = data.get("response", [])
                if not items:
                    continue

                total += len(items)
                # סינון פוסטים – רק מדוזות אמיתיות
                FANDOM_KEYWORDS = ["fandom", "fiction", "anime", "cartoon", "oc ",
                                   "fanart", "roleplay", "rp ", "ask ", "help! i'm a fish",
                                   "offical", "official blog", "chuck", "character"]
                
                real_posts = []
                for p in items:
                    title = (p.get("summary") or p.get("slug", "") or 
                             p.get("caption", "") or "").lower()
                    blog  = p.get("blog_name", "").lower()
                    # דלג על פוסטי פנדום/בלוגי ג'לי-פיש הבדיוניים
                    if any(kw in title or kw in blog for kw in FANDOM_KEYWORDS):
                        continue
                    real_posts.append(p)

                for p in (real_posts or items)[:4]:
                    date_str = p.get("date", "")[:10]
                    posts.append({
                        "title": p.get("summary") or p.get("slug", "") or p.get("caption", "")[:80],
                        "blog":  p.get("blog_name", ""),
                        "url":   p.get("post_url") or p.get("short_url", ""),
                        "date":  date_str,
                        "type":  p.get("type", ""),
                    })
                    try:
                        m = int(date_str[5:7]) - 1
                        if date_str[:4] == str(year) and 0 <= m < 12:
                            monthly[m] += 1
                    except Exception:
                        pass
                
                if real_posts:
                    total = len(real_posts)
                    break  # מצאנו פוסטים רלוונטיים
                # אם לא – ממשיכים לתגית הבאה

            except Exception as e:
                last_error = str(e)
                continue

    status = "live" if total > 0 else ("error" if last_error else "empty")
    return {
        "source":     "tumblr",
        "status":     status,
        "total":      total,
        "monthly":    monthly,
        "posts":      posts[:4],
        "last_error": last_error,
    }



# ── Combined score ────────────────────────────────────────────────────────────
WEIGHTS = {
    "inaturalist": 0.30,
    "youtube":     0.18,
    "mediacloud":  0.20,
    "reddit":      0.16,
    "trends":      0.11,
    "tumblr":      0.05,
}


@app.get("/api/combined")
async def combined(
    region: str = Query("mediterranean"),
    taxon:  str = Query("scyphozoa"),
    year:   int = Query(None),
):
    year = year or datetime.now().year

    # קריאה מקבילית לכל המקורות
    inat_data, yt_data, mc_data, rd_data, tr_data, tb_data = await asyncio.gather(
        inaturalist(region=region, taxon=taxon, year=year),
        youtube(region=region, year=year),
        mediacloud(region=region, year=year),
        reddit(region=region, year=year),
        trends(region=region, year=year),
        tumblr(region=region, year=year),
    )

    sources = {
        "inaturalist": inat_data["monthly"],
        "youtube":     yt_data["monthly"],
        "mediacloud":  mc_data["monthly"],
        "reddit":      rd_data["monthly"],
        "trends":      tr_data["monthly"],
        "tumblr":      tb_data["monthly"],
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
        "tumblr":      tb_data["status"],
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
                    "https://api.gdeltproject.org/api/v2/doc/doc",
                    params={"query": "jellyfish", "mode": "artlist", "maxrecords": "5", "format": "json", "startdatetime": "20240701000000", "enddatetime": "20240731235959"},
                    timeout=15
                )
                mc_raw = r.json()
            except Exception as e:
                mc_raw = {"error": str(e)}

    tb = get_tumblr_key()
    yt_keys = get_yt_keys()
    return {
        "youtube_keys_count": len(yt_keys),
        "youtube_key_set": bool(yt),
        "youtube_key_prefix": yt[:8] + "..." if yt else None,
        "youtube_keys_prefixes": [k[:8]+"..." for k in yt_keys if k],
        "tumblr_key_set": bool(tb),
        "tumblr_key_prefix": tb[:8] + "..." if tb else None,
        "youtube_raw_response": yt_raw,
        "mediacloud_key_set": bool(mc),
        "mediacloud_key_prefix": mc[:8] + "..." if mc else None,
        "mediacloud_raw_response": mc_raw,
        "taxa_available": list(TAXA.keys()),
        "regions_available": list(REGIONS.keys()),
    }

