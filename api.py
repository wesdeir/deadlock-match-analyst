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

# Time of our last live request, used to enforce MIN_INTERVAL_S between calls.
_last_request = 0.0


class RateLimited(Exception):
    """Raised when the server asks us to wait longer than we are willing to (the caller should stop and retry later)."""
    def __init__(self, wait_s):
        super().__init__(f"rate limited, retry in ~{wait_s:.0f}s")
        self.wait_s = wait_s


def _cache_path(url: str) -> Path:
    """Disk-cache file for a URL: a readable prefix plus a hash so long query strings stay unique."""
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
    """All of a player's matches (small summary rows, newest included once the match is processed)."""
    return get_json(f"{API}/v1/players/{account_id}/match-history", refresh)


def match_metadata(match_id: int, refresh=False):
    """Full metadata for one match (players, items, deaths, damage matrix, paths). Heavily rate limited."""
    return get_json(f"{API}/v1/matches/{match_id}/metadata", refresh)


def items_table(refresh=False):
    """Item/ability name table (the API's /v1/assets mirror first, the assets server as a fallback)."""
    # api.deadlock-api.com serves the same assets under /v1/assets/ and is up when assets.deadlock-api.com is not
    return get_json(f"{API}/v1/assets/items", refresh) or get_json(f"{ASSETS}/v2/items", refresh)


def heroes_table(refresh=False):
    """Hero name table (same sources as items_table)."""
    return get_json(f"{API}/v1/assets/heroes", refresh) or get_json(f"{ASSETS}/v2/heroes", refresh)


def generic_data(refresh=False):
    """Misc. game data, e.g. lane names, via the /v1/assets mirror."""
    return get_json(f"{API}/v1/assets/generic-data", refresh)


def cached_match_metadata(match_id: int):
    """Match metadata from the disk cache only (never touches the network); None if not cached."""
    path = _cache_path(f"{API}/v1/matches/{match_id}/metadata")
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


MAP_URL = "https://assets-bucket.deadlock-api.com/assets-api-res/images/maps/minimap_midtown_mid.png"


def ensure_map_image(dest: Path):
    """Download the minimap PNG once (kept out of git); returns True if it is available locally."""
    if dest.exists():
        return True
    try:
        d = get_json(f"{API}/v1/assets/map") or {}
        url = d.get("images", {}).get("minimap", MAP_URL)
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=60) as r:
            b = r.read()
        if b[:8] != b"\x89PNG\r\n\x1a\n":
            return False
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b)
        return True
    except Exception as e:  # the map is cosmetic
        print("map image not downloaded:", e)
        return False


def ensure_hero_icons(dest_dir: Path):
    """Download each hero's small portrait and card art into docs/assets/heroes/ (committed, so the site works offline)
    and write heroes.js mapping hero name -> {icon, card}. Existing files are skipped, so this is cheap to re-run."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    table = heroes_table()
    rows = table if isinstance(table, list) else list(table.values())
    out = {}
    for h in rows:
        img, name = h.get("images") or {}, h.get("name")
        if not name or h.get("disabled") or h.get("player_selectable") is False:
            continue
        entry = {}
        for key, field in (("icon", "icon_image_small_webp"), ("card", "icon_hero_card_webp")):
            url = img.get(field)
            if not url:
                continue
            fn = f"{h['class_name'].replace('hero_', '')}_{key}.webp"
            path = dest_dir / fn
            if not path.exists():
                try:
                    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
                    with urllib.request.urlopen(req, timeout=60) as r:
                        path.write_bytes(r.read())
                    time.sleep(0.2)
                except Exception as e:  # icons are cosmetic
                    print("hero image not downloaded:", url, e)
                    continue
            entry[key] = "assets/heroes/" + fn
        if entry:
            out[name] = entry
    # a .js file (not .json) so pages also work when opened straight from disk, where fetch() is blocked
    (dest_dir.parent / "heroes.js").write_text("window.HEROES=" + json.dumps(out) + ";\n", encoding="utf-8")
    return out
