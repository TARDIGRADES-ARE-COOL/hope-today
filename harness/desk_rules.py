"""Copy Desk clue building, no LLM (PLAN.md Part 3, layers C3.5a and C3.5b).

C3.5a: list every TRUE small rule over the cards, plus the names code can resolve for each
card ("the only acres", "the biggest size on the desk"). The structure search (C3.5b) picks
clues from these; the LLM (C3.5c) only phrases them.

    python harness/desk_rules.py prototypes/copy-desk/samples.json            # C3.5a test
    python harness/desk_rules.py --search prototypes/copy-desk/samples.json   # C3.5b test
"""
import json
import random
import re
import sys
import time
from itertools import combinations

from desk import Desk, check, rule_holds
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
    probe, masks = rule_masks(desk_data, rules)
    useful = [r for r, m in zip(rules, masks) if m != probe.all]
    return useful, card_names(cards)


def rule_masks(desk_data, rules):
    """(probe Desk, bitmask of filings each rule allows), using the real engine."""
    probe = Desk({**desk_data, "cards": [{k: v for k, v in c.items() if k != "clue"} for c in desk_data["cards"]],
                  "clues": [{"id": f"r{i}", "start": True, "rule": r} for i, r in enumerate(rules)]})
    return probe, [probe.clue_mask[f"r{i}"] for i in range(len(rules))]


# ---------- C3.5b: structure search ----------

ATTEMPTS = 20000            # hard cap on tries per desk; most are rejected by bitmasks alone
START = (2, 3)              # how many start clues
HIDDEN = (2, 3, 4)          # how many clues hidden on facts


def search(desk_data, seed=0, attempts=ATTEMPTS):
    """Pick start clues and hidden clues from the true rules until all quality rules pass.
    Returns (desk data with clues, stats) or (None, stats). Clue texts come later (C3.5c)."""
    rules, _ = true_rules(desk_data)
    probe, masks = rule_masks(desk_data, rules)
    pool, seen = [], set()
    for r, m in zip(rules, masks):        # one rule per mask: same effect means same clue
        if m not in seen:
            seen.add(m)
            pool.append((r, m))
    places = list(probe.place.values())

    def proves(m):                        # does a set of filings fix at least one card?
        return any(m & p == m for p in places)

    rng = random.Random(seed)
    cards = [c["id"] for c in desk_data["cards"]]
    stats = {"rules": len(pool), "attempts": 0, "full_checks": 0}
    for attempt in range(1, attempts + 1):
        stats["attempts"] = attempt
        n_start, n_hidden = rng.choice(START), rng.choice(HIDDEN)
        chosen = rng.sample(pool, n_start + n_hidden)
        both = probe.all
        for _, m in chosen:
            both &= m
        if bin(both).count("1") != 1:                                  # rule 2: one answer
            continue
        if sum(proves(m) for _, m in chosen) > 2:                      # rule 5: openers
            continue
        start = probe.all
        for _, m in chosen[:n_start]:
            start &= m
        if not proves(start):                                          # rule 3 at the start
            continue
        hide_on = rng.sample(cards, n_hidden)
        clues = [{"id": f"c{i + 1}", "rule": r, **({"start": True} if i < n_start else {})}
                 for i, (r, _) in enumerate(chosen)]
        hidden = dict(zip(hide_on, [c["id"] for c in clues[n_start:]]))
        data = {**desk_data, "clues": clues,
                "cards": [{**{k: v for k, v in c.items() if k != "clue"},
                           **({"clue": hidden[c["id"]]} if c["id"] in hidden else {})}
                          for c in desk_data["cards"]]}
        stats["full_checks"] += 1
        passed, _, checks = check(Desk(data))
        if passed:
            return data, {**stats, **checks}
    return None, stats


def rule_key(rule):
    """Compare rules ignoring the 'group' label and the order of same/differ pairs."""
    r = {k: v for k, v in rule.items() if k != "group"}
    if r["op"] in ("same", "differ"):
        r["a"], r["b"] = sorted((r["a"], r["b"]))
    if "others" in r:
        r["others"] = sorted(r["others"])
    return json.dumps(r, sort_keys=True)


def search_test(path, seeds=10):
    """C3.5b test: search each sample's cards (its hand-made clues removed) with several seeds."""
    found = tries = 0
    for sample in json.load(open(path, encoding="utf-8")):
        d = {k: v for k, v in sample["desk"].items() if k != "clues"}
        wins, t0, example = [], time.time(), None
        for seed in range(seeds):
            data, stats = search(d, seed=seed)
            tries += 1
            if data:
                wins.append(stats["attempts"])
                example = example or (data, stats)
        found += len(wins)
        print(f"{sample['label']} · {sample['size']}: {len(wins)}/{seeds} seeds pass"
              + (f", attempts median {sorted(wins)[len(wins) // 2]} max {max(wins)}" if wins else "")
              + f", {(time.time() - t0) / seeds:.1f}s per search")
        if example:
            data, stats = example
            gate = {c["clue"]: c["t"] for c in data["cards"] if c.get("clue")}
            for c in data["clues"]:
                where = "start" if c.get("start") else f"on {gate[c['id']]}"
                print(f"    {c['id']} ({where}): {json.dumps(c['rule'])}")
            print(f"    states={stats['states']} avg-provable={stats['avg_provable']} "
                  f"chain={stats['chain']} longest-proof={stats['longest_proof']} openers={stats['openers']}")
    print(f"pass rate: {found}/{tries}")
    return found


if __name__ == "__main__":
    if "--search" in sys.argv:
        sys.argv.remove("--search")
        sys.exit(0 if search_test(sys.argv[1]) else 1)
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
