"""Optional Statlocker snapshot (data/statlocker_snapshot.json): community percentiles plus per-game match rank, grade and
MMR change. The file is captured by hand from your own signed-in Statlocker profile (see NOTES.md) - nothing here talks to
Statlocker. If the file is missing, the dashboards simply omit the Statlocker panels.
"""
import json
from pathlib import Path

SNAPSHOT = Path(__file__).parent / "data" / "statlocker_snapshot.json"

# Plain-English meaning of the categories that matter most, shown next to the percentile bars. These are interpretations,
# not Statlocker's words; categories without an entry are shown without a note.
HINTS = {
    "HEADSHOT ACCURACY PERCENTAGE": "your headshots land far more often than the community's - elite aim",
    "ANTI-HEAL/MIN": "you apply anti-heal much more than most players (Healbane-type items)",
    "2ND HALF DAMAGE": "you deal strong damage in the late game",
    "HERO DAMAGE": "you deal a lot of damage to enemy heroes overall",
    "DAMAGE ABSORBED/MIN": "you soak up more damage than most (resists/barriers)",
    "2ND HALF DEATHS": "you die more in the second half of games - matches our late-death/respawn finding",
    "LAST HITS/MIN": "you farm fewer creeps per minute - fits 0 lane wins at 9:00",
    "AVG LAST HITS": "fewer creep last hits than average",
    "1ST HALF KILLS": "fewer early kills than most",
    "CLOSE-RANGE DAMAGE %": "you fight from range; fewer close-range fights won",
    "CLOSE-RANGE KILLS": "fewer close-range kills",
    "MELEE DAMAGE %": "you rarely melee - probably not important unless your hero benefits from it",
    "MELEE KILLS %": "you rarely get melee kills - probably low priority",
}
# Rows that are about rank or outcomes rather than something you can practise; kept in the file, hidden from the charts.
SKIP = {"YOUR RANK", "AVG MATCH RANK", "ABANDON RATE", "WIN RATE", "KDA RATIO", "KD RATIO", "AVERAGE MATCH MVP", "TEAM MVP PLACE", "MVP SCORE"}


def load():
    """Read the hand-captured Statlocker snapshot, or None if it doesn't exist."""
    try:
        return json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _secs(mmss):
    """'42:12' -> 2532 seconds."""
    m, s = mmss.split(":")
    return int(m) * 60 + int(s)


def match_games(records, snap):
    """Attach Statlocker's per-game numbers to our match records: {match_id: {mvp, grade, mmr}}.

    Games are matched on KDA plus duration (within 3 seconds); each Statlocker game is used at most once.
    """
    out, used = {}, set()
    for rec in records:
        for i, g in enumerate(snap["matches"]):
            if i in used or g["kda"] != rec["kda"] or abs(_secs(g["dur"]) - rec["dur"]) > 3:
                continue
            used.add(i)
            out[rec["id"]] = {"mvp": g["mvp"], "grade": g["grade"], "mmr": g["mmr"]}
            break
    return out


def community(snap, n=7):
    """Strengths and weaknesses as percentiles (higher = better than more of the community), skipping outcome/rank rows."""
    rows = []
    for order, name, value, side, pct in snap["community"]["rows"]:
        if name in SKIP:
            continue
        better_than = 100 - pct if side == "TOP" else pct  # 'TOP 5' = better than 95%; 'BOTTOM 10' = better than only 10%
        rows.append({"name": name.title().replace("1St", "1st").replace("2Nd", "2nd"), "key": name, "value": value, "pct": better_than, "hint": HINTS.get(name)})
    rows.sort(key=lambda r: -r["pct"])
    return {"strengths": rows[:n], "weaknesses": rows[-n:][::-1], "meta": {k: snap["community"][k] for k in ("sample", "caveat")},
            "rank": snap["rank"], "laning": snap["laning"], "captured": snap["captured"], "overview": snap["overview"]}
