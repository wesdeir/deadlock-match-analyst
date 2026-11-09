"""Build gamedata.json (hero/item names + item stats) from the SteamTracking/GameTracking-Deadlock text dumps
in data/gametracking/. Pure text parsing - nothing from those files is ever executed."""
import json, re, sys
from pathlib import Path
from analyst import murmur2

D = Path(__file__).parent / "data" / "gametracking"


def tokens(fn):
    out = {}
    for line in (D / fn).read_text(encoding="utf-8-sig").splitlines():
        m = re.match(r'\s*"([^"]+)"\s+"(.*)"\s*$', line)
        if m:
            out[m.group(1)] = m.group(2)
    return out


def top_blocks(fn):
    """Yield (name, [lines]) for each top-level entry of a vdata file (depth-1 `name =` blocks)."""
    depth, name, buf = 0, None, []
    for line in (D / fn).read_text(encoding="utf-8-sig").splitlines():
        s = line.strip()
        if depth == 1 and name is None and re.match(r"^[A-Za-z0-9_]+ =\s*$", s):
            name, buf = s.split(" =")[0], []
        elif name is not None:
            buf.append(line)
        if s == "{" or s.endswith("{"):
            depth += 1
        if s == "}" or s.startswith("}"):
            depth -= 1
            if depth == 1 and name is not None:
                yield name, buf
                name = None


def scalar(lines, key):
    for l in lines:
        m = re.match(rf'\s*{key} = "?([^"\n]*)"?\s*$', l)
        if m:
            return m.group(1).strip()


def main():
    hero_names = tokens("citadel_gc_hero_names_english.txt")
    item_names = tokens("citadel_gc_mod_names_english.txt")
    heroes = {}
    for name, lines in top_blocks("heroes.vdata"):
        if not name.startswith("hero_"):
            continue
        hid = scalar(lines, "m_HeroID")
        if hid is None:
            continue
        heroes[int(hid)] = {"key": name, "name": hero_names.get(name + ":n", name)}
    items = {}
    for name, lines in top_blocks("abilities.vdata"):
        if not any('_class = "citadel_item"' in l for l in lines[:6]):
            continue
        props, cur = {}, None
        for l in lines:
            if m := re.match(r"^\t\t\t([A-Za-z0-9_]+) = $", l):
                cur = m.group(1)
                props[cur] = None
            elif cur and props[cur] is None and (m := re.match(r'^\t\t\t\tm_strValue = "([^"]*)"', l)):
                props[cur] = m.group(1)
        items[murmur2(name.encode())] = {
            "class": name, "name": item_names.get(name, name),
            "slot": (scalar(lines, "m_eItemSlotType") or "").replace("EItemSlotType_", ""),
            "tier": (scalar(lines, "m_iItemTier") or "").replace("EModTier_", ""),
            "props": props,  # property -> value string (as in the game file)
            "disabled": scalar(lines, "m_bDisabled") == "true",
        }
    (Path(__file__).parent / "gamedata.json").write_text(json.dumps({"heroes": heroes, "items": items}, indent=0), encoding="utf-8")
    print(f"heroes {len(heroes)}, items {len(items)}")
    print({k: v for k, v in list(heroes.items())[:3]}, heroes.get(81), heroes.get(7))
    print(items.get(murmur2(b"upgrade_endurance")))


if __name__ == "__main__":
    main()
