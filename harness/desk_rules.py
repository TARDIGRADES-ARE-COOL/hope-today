"""Copy Desk clue building, no LLM (PLAN.md Part 3, layers C3.5a and C3.5b).

C3.5a: list every TRUE small rule over the cards, plus the names code can resolve for each
card ("the only acres", "the biggest size on the desk"). The structure search (C3.5b) picks
clues from these; the LLM (C3.5c) only phrases them.

    python harness/desk_rules.py prototypes/copy-desk/samples.json
"""
import json
import re
import sys
from itertools import combinations

from desk import Desk, rule_holds
from desk_facts import MARGIN, NUMBER, normalise

CURRENCY = "$£€¥"
UNIT_WORDS = {"hectares": "ha", "hectare": "ha", "acre": "acres", "year": "years",
              "month": "months", "week": "weeks"}


def visible_unit(text):
    """The unit a player sees on the card: '$19m+' -> '$', '460 acres' -> 'acres', '91%' -> '%'."""
    if text.strip()[:1] in CURRENCY:
        return text.strip()[0]
    if "%" in text:
        return "%"
    words = NUMBER.split(text)[-1].replace("+", " ").lower().split()     # text after the last number
    return UNIT_WORDS.get(words[-1], words[-1]) if words else ""


def group_key(card):
    """Cards with the same key can be ranked. Money only against the same currency symbol;
    counts by what the player sees (bare numbers together). Ranges ('30 to 50') never rank."""
    if len(NUMBER.findall(card["t"])) != 1:
        return None
    if card["kind"] in ("money", "count"):
        return (card["kind"], visible_unit(card["t"]))
    return (card["kind"], normalise(card)[0])


def card_names(cards):
    """card id -> every way code can name it uniquely on the desk. The text always works."""
    names = {c["id"]: [{"by": "text"}] for c in cards}
    units = [visible_unit(c["t"]) for c in cards]
    kinds = [c["kind"] for c in cards]
    for c, u, k in zip(cards, units, kinds):
        if u and units.count(u) == 1:
            names[c["id"]].append({"by": "unit", "unit": u})
        if kinds.count(k) == 1:
            names[c["id"]].append({"by": "kind", "kind": k})
    groups = {}
    for c in cards:
        groups.setdefault(group_key(c), []).append(c)
    for key, group in groups.items():
        if key is None or len(group) < 2:
            continue
        kind, unit = key
        ranked = sorted(group, key=lambda c: normalise(c)[1])
        values = [normalise(c)[1] for c in ranked]
        margin = 1 if kind == "year" else MARGIN    # years only need to differ
        tag = {"kind": kind, "unit": unit, "of": len(group)}
        if values[-1] > values[-2] and values[-1] >= margin * values[-2]:
            names[ranked[-1]["id"]].append({"by": "rank", "rank": "biggest", **tag})
        if values[1] > values[0] and values[1] >= margin * values[0]:
            names[ranked[0]["id"]].append({"by": "rank", "rank": "smallest", **tag})
    return names


def true_rules(desk_data):
    """Every true rule over the real filing that rules out at least one filing.
    Returns (rules, names). Each rule is a dict in the day.json clue "rule" shape."""
    cards = desk_data["cards"]
    n = len(desk_data["stories"])
    home = {c["id"]: c["home"] for c in cards}
    rules = []
    for c in cards:
        rules.append({"op": "in", "card": c["id"], "story": c["home"]})
        rules += [{"op": "not_in", "card": c["id"], "story": s} for s in range(n) if s != c["home"]]
    for a, b in combinations(cards, 2):
        op = "same" if a["home"] == b["home"] else "differ"
        rules.append({"op": op, "a": a["id"], "b": b["id"]})
    # same_as_any over groups a player can see: one kind, or one unit (2+ cards, not the card itself).
    groups = {}
    for c in cards:
        groups.setdefault(("kind", c["kind"]), []).append(c["id"])
        groups.setdefault(("unit", visible_unit(c["t"])), []).append(c["id"])
    for c in cards:
        for key, members in groups.items():
            others = [m for m in members if m != c["id"]]
            if len(others) >= 2 and any(home[m] == c["home"] for m in others):
                rules.append({"op": "same_as_any", "card": c["id"], "others": others, "group": list(key)})

    # Masks from the real engine, so a rule that every filing meets (it says nothing) is dropped.
    probe = Desk({**desk_data, "cards": [{k: v for k, v in c.items() if k != "clue"} for c in cards],
                  "clues": [{"id": f"r{i}", "start": True, "rule": r} for i, r in enumerate(rules)]})
    useful = [r for i, r in enumerate(rules) if probe.clue_mask[f"r{i}"] != probe.all]
    return useful, card_names(cards)


def rule_key(rule):
    """Compare rules ignoring the 'group' label and the order of same/differ pairs."""
    r = {k: v for k, v in rule.items() if k != "group"}
    if r["op"] in ("same", "differ"):
        r["a"], r["b"] = sorted((r["a"], r["b"]))
    if "others" in r:
        r["others"] = sorted(r["others"])
    return json.dumps(r, sort_keys=True)


if __name__ == "__main__":
    # Test (C3.5a): every listed rule is true for the real filing. Also shows which of the
    # hand-made clues the lister would have found.
    failed = False
    for sample in json.load(open(sys.argv[1], encoding="utf-8")):
        d = sample["desk"]
        rules, names = true_rules(d)
        real = tuple(c["home"] for c in d["cards"])
        idx = {c["id"]: i for i, c in enumerate(d["cards"])}
        false = [r for r in rules if not rule_holds(r, real, idx)]
        failed |= bool(false)
        listed = {rule_key(r) for r in rules}
        missed = [c["id"] for c in d["clues"] if rule_key(c["rule"]) not in listed]
        ops = {}
        for r in rules:
            ops[r["op"]] = ops.get(r["op"], 0) + 1
        print(f"{sample['label']} · {sample['size']}: {len(rules)} rules "
              f"({', '.join(f'{k} {v}' for k, v in ops.items())}) · "
              f"{'ALL TRUE' if not false else f'{len(false)} FALSE'} · "
              f"hand-made clues found {len(d['clues']) - len(missed)}/{len(d['clues'])}"
              + (f" (missed {', '.join(missed)})" if missed else ""))
        for c in d["cards"]:
            extra = [n for n in names[c["id"]] if n["by"] != "text"]
            print(f"    {c['t']:<12} " + "; ".join(
                f"the {n['rank']} of {n['of']} {n['kind']} ({n['unit']})" if n["by"] == "rank"
                else f"the only {n['by']} '{n.get('unit') or n.get('kind')}'" for n in extra))
    sys.exit(1 if failed else 0)
