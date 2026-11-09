"""Cached, rate-limited client for api.deadlock-api.com and assets.deadlock-api.com."""
import hashlib
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

CACHE_DIR = Path(__file__).parent / "cache"
USER_AGENT = "deadlock-match-analyst/0.1 (personal match review script)"
MIN_INTERVAL_S = 6.0  # minimum gap between live requests
API = "https://api.deadlock-api.com"
ASSETS = "https://assets.deadlock-api.com"

_last_request = 0.0


class RateLimited(Exception):
    def __init__(self, wait_s):
        super().__init__(f"rate limited, retry in ~{wait_s:.0f}s")
        self.wait_s = wait_s


def _cache_path(url: str) -> Path:
    h = hashlib.sha1(url.encode()).hexdigest()[:16]
    tail = url.split("//", 1)[1].replace("/", "_").replace("?", "_").replace("&", "_")[:80]
    return CACHE_DIR / f"{tail}.{h}.json"


def get_json(url: str, refresh: bool = False, retries: int = 3):
    """GET url as JSON. Disk-cached forever unless refresh=True. Returns None on failure."""
    global _last_request
    CACHE_DIR.mkdir(exist_ok=True)
    path = _cache_path(url)
    if path.exists() and not refresh:
        return json.loads(path.read_text(encoding="utf-8"))
    for attempt in range(retries):
        wait = MIN_INTERVAL_S - (time.time() - _last_request)
        if wait > 0:
            time.sleep(wait)
        _last_request = time.time()
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read().decode("utf-8"))
            path.write_text(json.dumps(data), encoding="utf-8")
            return data
        except urllib.error.HTTPError as e:
            if e.code == 429:
                ra = e.headers.get("Retry-After")
                print(f"429 rate limited (Retry-After={ra!r}); body={e.read()[:200]!r}")
                try:
                    wait_s = float(ra) if ra else 30 * (attempt + 1)
                except ValueError:
                    wait_s = 60
                if wait_s > 90:  # don't sit here for ages: stop and let the caller retry later
                    raise RateLimited(wait_s)
                time.sleep(wait_s)
                continue
            print(f"HTTP {e.code} for {url}")
            return None
        except (urllib.error.URLError, TimeoutError) as e:
            print(f"Network error for {url}: {e}")
            time.sleep(2 * (attempt + 1))
    return None


def match_history(account_id: int, refresh=False):
    return get_json(f"{API}/v1/players/{account_id}/match-history", refresh)


def match_metadata(match_id: int, refresh=False):
    return get_json(f"{API}/v1/matches/{match_id}/metadata", refresh)


def items_table(refresh=False):
    # api.deadlock-api.com serves the same assets under /v1/assets/ and is up when assets.deadlock-api.com is not
    return get_json(f"{API}/v1/assets/items", refresh) or get_json(f"{ASSETS}/v2/items", refresh)


def heroes_table(refresh=False):
    return get_json(f"{API}/v1/assets/heroes", refresh) or get_json(f"{ASSETS}/v2/heroes", refresh)


def generic_data(refresh=False):
    return get_json(f"{API}/v1/assets/generic-data", refresh)


def cached_match_metadata(match_id: int):
    """Match metadata from the disk cache only (never touches the network); None if not cached."""
    path = _cache_path(f"{API}/v1/matches/{match_id}/metadata")
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
