"""Copy Desk: the second step of the daily puzzle (PLAN.md Part 3).

The night desk dropped a handful of facts from today's stories. The player files each one
under its story, but only once the clues PROVE where it goes.

This file is the logic only (layers C3.1a, C3.1b and C3.2). No model calls yet:
- the solver: every filing that fits the rules, as bitmasks
- provable / possible / hints for any state
- the 8 quality rules from PLAN.md, plus "no dead clues"
- the state table the page reads (so the page never needs its own solver)

    python harness/desk.py --check prototypes/copy-desk/samples.json     # quality rules
    python harness/desk.py --table prototypes/copy-desk/samples.json     # build + verify state tables
    python harness/desk.py --render prototypes/copy-desk/samples.json    # write test pages to output/
"""
import argparse
import base64
import hashlib
import html
import json
import sys
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "prototypes" / "copy-desk" / "samples.json"
OUTPUT = ROOT / "output" / "desk-samples"
HINT_MAX_CLUES = 3          # a hint names at most 3 clues; rule 4 checks one always exists
CHAIN_MAX = 0.5             # rule 8
OPENERS_MAX = 2             # rule 5


class DeskError(Exception):
    """A desk that can't work: bad data, or clues that contradict each other."""


# ---------- Clue rules ----------
# Every clue is one small rule over the cards. `a` is a filing: a tuple giving the story
# index of every card, in card order. Keep this list small: the page never runs it,
# the state table carries the results.

def rule_holds(rule, a, idx):
    op = rule["op"]
    if op == "in":
        return a[idx[rule["card"]]] == rule["story"]
    if op == "not_in":
        return a[idx[rule["card"]]] != rule["story"]
    if op == "same":
        return a[idx[rule["a"]]] == a[idx[rule["b"]]]
    if op == "differ":
        return a[idx[rule["a"]]] != a[idx[rule["b"]]]
    if op == "same_as_any":
        return any(a[idx[rule["card"]]] == a[idx[o]] for o in rule["others"])
    raise DeskError(f"unknown rule op {op!r}")


class Desk:
    """One day's desk, with every legal filing precomputed as a bitmask."""

    def __init__(self, data):
        self.data = data
        self.cards = [c["id"] for c in data["cards"]]
        if len(set(self.cards)) != len(self.cards):
            raise DeskError("card ids must be unique")
        self.idx = {c: i for i, c in enumerate(self.cards)}
        self.n_stories = len(data["stories"])
        self.per = data["per"]
        if self.per * self.n_stories != len(self.cards):
            raise DeskError(f"{len(self.cards)} cards can't fill {self.n_stories} stories with {self.per} each")
        self.kinds = data.get("kinds") or {}
        self.card_kind = [c.get("kind") for c in data["cards"]]
        self.home = tuple(c["home"] for c in data["cards"])
        self.clue_ids = [c["id"] for c in data["clues"]]
        self.clue = {c["id"]: c for c in data["clues"]}
        self.start = [c["id"] for c in data["clues"] if c.get("start")]
        self.hidden_on = {c["id"]: c["clue"] for c in data["cards"] if c.get("clue")}
        for card, cid in self.hidden_on.items():
            if cid not in self.clue:
                raise DeskError(f"card {card} hides unknown clue {cid}")
        if not self.start:
            raise DeskError("a desk needs at least one start clue")
        if any(not (isinstance(h, int) and 0 <= h < self.n_stories) for h in self.home):
            raise DeskError("every card's home must be a story index")
        for c in data["clues"]:
            r = c["rule"]
            ids = [r[k] for k in ("card", "a", "b") if k in r] + list(r.get("others", []))
            missing = [x for x in ids if x not in self.idx]
            if missing:
                raise DeskError(f"clue {c['id']} names unknown card(s) {missing}")
            if "story" in r and not 0 <= r["story"] < self.n_stories:
                raise DeskError(f"clue {c['id']} names story {r['story']}, which doesn't exist")

        self.filings = self._enumerate()                       # list of tuples
        if self.home not in self.filings:
            raise DeskError("the real filing breaks the count or kind rules")
        self.all = (1 << len(self.filings)) - 1
        self.clue_mask = {cid: self._mask(lambda a, r=self.clue[cid]["rule"]: rule_holds(r, a, self.idx))
                          for cid in self.clue_ids}
        # place[(card index, story)] = filings with that card in that story
        self.place = {(i, s): self._mask(lambda a, i=i, s=s: a[i] == s)
                      for i in range(len(self.cards)) for s in range(self.n_stories)}
        self._memo_prov = {}

    # -- building --
    def _enumerate(self):
        out, a = [], [0] * len(self.cards)
        count = [0] * self.n_stories
        kc = [dict() for _ in range(self.n_stories)]

        def rec(i):
            if i == len(self.cards):
                out.append(tuple(a))
                return
            k = self.card_kind[i]
            for s in range(self.n_stories):
                if count[s] >= self.per:
                    continue
                if k in self.kinds and kc[s].get(k, 0) >= self.kinds[k]:
                    continue
                a[i] = s
                count[s] += 1
                if k:
                    kc[s][k] = kc[s].get(k, 0) + 1
                rec(i + 1)
                count[s] -= 1
                if k:
                    kc[s][k] -= 1
        rec(0)
        return out

    def _mask(self, pred):
        m = 0
        for bit, a in enumerate(self.filings):
            if pred(a):
                m |= 1 << bit
        return m

    # -- solving --
    def solutions(self, clue_ids, placed):
        """Bitmask of filings that fit the rules, these clues and the facts already filed.
        `placed` maps card id -> story. Raises if nothing fits (a contradiction is a bug)."""
        m = self.all
        for cid in clue_ids:
            m &= self.clue_mask[cid]
        for card, s in placed.items():
            m &= self.place[(self.idx[card], s)]
        if not m:
            raise DeskError(f"no filing fits clues {sorted(clue_ids)} with {placed}")
        return m

    def possible(self, clue_ids, placed):
        """card id -> stories still possible, for every loose card."""
        m = self.solutions(clue_ids, placed)
        return {c: [s for s in range(self.n_stories) if m & self.place[(i, s)]]
                for i, c in enumerate(self.cards) if c not in placed}

    def provable(self, clue_ids, placed):
        """card id -> story, for every loose card the clues prove. Card order, like the page."""
        key = (tuple(sorted(clue_ids)), tuple(sorted(placed.items())))
        if key not in self._memo_prov:
            self._memo_prov[key] = {c: ss[0] for c, ss in self.possible(clue_ids, placed).items() if len(ss) == 1}
        return self._memo_prov[key]

    def visible(self, placed):
        """Start clues, plus the clue hidden on each fact already filed. In clue order."""
        shown = set(self.start) | {self.hidden_on[c] for c in placed if c in self.hidden_on}
        return [cid for cid in self.clue_ids if cid in shown]

    def best_hint(self, placed):
        """Smallest set of visible clues (up to 3) that proves some fact now, or None."""
        vis = self.visible(placed)
        for size in range(0, min(HINT_MAX_CLUES, len(vis)) + 1):
            for sub in combinations(vis, size):
                p = self.provable(sub, placed)
                if p:
                    card = next(iter(p))
                    return {"clues": list(sub), "card": card, "story": p[card]}
        return None

    def min_proof(self, placed, card):
        """Fewest visible clues that prove `card` in this state (0 = the count rules alone)."""
        vis = self.visible(placed)
        for size in range(0, len(vis) + 1):
            for sub in combinations(vis, size):
                if card in self.provable(sub, placed):
                    return size, sub
        return float("inf"), ()

    def reachable_states(self):
        """Every set of correctly filed facts a player can reach by filing proven facts."""
        seen, todo = {}, [{}]
        while todo:
            placed = todo.pop()
            key = tuple(sorted(placed))
            if key in seen:
                continue
            seen[key] = placed
            if len(placed) == len(self.cards):
                continue
            for card, s in self.provable(self.visible(placed), placed).items():
                todo.append({**placed, card: s})
        return seen

    def truth(self):
        return {c: self.home[i] for i, c in enumerate(self.cards)}


# ---------- Quality rules (PLAN.md Part 3) ----------

def check(desk):
    """Run the quality rules. Returns (passed, rules dict, stats dict)."""
    truth = desk.truth()
    home = desk.home
    truth_ok = all(rule_holds(desk.clue[c]["rule"], home, desk.idx) for c in desk.clue_ids)

    full = desk.all
    for cid in desk.clue_ids:
        full &= desk.clue_mask[cid]
    unique = bin(full).count("1") == 1 and desk.filings[full.bit_length() - 1] == home
    if not (truth_ok and unique):
        # Everything below assumes the real filing fits every clue (states are keyed by
        # which facts are filed, which is only safe then). Stop here with a clear failure.
        rules = {"1 the real filing fits every clue": truth_ok, "2 one answer": unique}
        return False, rules, {"states": 0, "avg_provable": 0, "chain": 0, "longest_proof": 0,
                              "openers": [], "dead_clues": []}

    states = desk.reachable_states()
    dead = wrong = no_hint = 0
    choice = False
    n_states = prov_sum = 0
    longest = 0
    used = set()                       # clues that appear in some smallest proof
    for placed in states.values():
        left = len(desk.cards) - len(placed)
        if not left:
            continue
        n_states += 1
        p = desk.provable(desk.visible(placed), placed)
        prov_sum += len(p)
        if not p:
            dead += 1
            continue
        if desk.best_hint(placed) is None:
            no_hint += 1
        wrong += sum(1 for c, s in p.items() if s != truth[c])
        if left >= 3 and len(set(p.values())) >= 2:
            choice = True
        for card in p:
            size, _ = desk.min_proof(placed, card)
            longest = max(longest, size)
            vis = desk.visible(placed)
            for sub in combinations(vis, size):       # every smallest proof, not just the first
                if card in desk.provable(sub, placed):
                    used.update(sub)

    # Rule 6: can the whole desk be filed using at most ONE clue per move? Then it's a chain.
    memo = {}

    def one_clue_finish(placed):
        key = tuple(sorted(placed))
        if key in memo:
            return memo[key]
        if len(placed) == len(desk.cards):
            memo[key] = True
            return True
        result = False
        for card, s in desk.provable(desk.visible(placed), placed).items():
            if desk.min_proof(placed, card)[0] <= 1 and one_clue_finish({**placed, card: s}):
                result = True
                break
        memo[key] = result
        return result
    chain_only = one_clue_finish({})

    # Chain score on the hint path: share of moves proven by the clue revealed just before.
    placed, prev_vis, chain_moves, moves = {}, desk.visible({}), 0, 0
    while len(placed) < len(desk.cards):
        h = desk.best_hint(placed)
        if not h:
            break
        moves += 1
        vis = desk.visible(placed)
        fresh = [c for c in vis if c not in prev_vis]
        if any(h["card"] in desk.provable([c], placed) for c in fresh):
            chain_moves += 1
        prev_vis = vis
        placed = {**placed, h["card"]: h["story"]}
    chain = chain_moves / moves if moves else 0.0

    openers = [c for c in desk.clue_ids if desk.provable([c], {})]
    dead_clues = [c for c in desk.clue_ids if c not in used]

    rules = {
        "1 the real filing fits every clue": truth_ok,
        "2 one answer": unique,
        "3 never stuck, never a wrong proof": dead == 0 and wrong == 0,
        "4 a hint exists in every state": no_hint == 0,
        f"5 at most {OPENERS_MAX} clues file a fact on sight": len(openers) <= OPENERS_MAX,
        "6 every solve path needs a two-clue step": not chain_only,
        "7 a real choice of where to go next": choice,
        f"8 chain score at most {CHAIN_MAX}": chain <= CHAIN_MAX,
        "9 no dead clues": not dead_clues,
    }
    stats = {
        "states": n_states,
        "avg_provable": round(prov_sum / n_states, 2) if n_states else 0,
        "chain": round(chain, 2),
        "longest_proof": longest,
        "openers": openers,
        "dead_clues": dead_clues,
    }
    return all(rules.values()), rules, stats


# ---------- State table (C3.2) ----------

def build_table(desk):
    """For every reachable state: what is visible, what is provable, what is still possible,
    and the best hint. Keyed by the filed card ids, sorted and comma-joined ("" = start).
    Only correct filings are ever stored, so a state is just WHICH facts are filed.
    Also carries what the page must not show in plain text: each fact's meaning (it names
    the story) and the hidden clues' wording (showing them early would skip the puzzle)."""
    return {
        "states": build_states(desk),
        "means": {c["id"]: c["means"] for c in desk.data["cards"]},
        "clues": {c["id"]: c["t"] for c in desk.data["clues"]},
    }


def build_states(desk):
    table = {}
    for key, placed in desk.reachable_states().items():
        vis = desk.visible(placed)
        if len(placed) == len(desk.cards):
            table[",".join(key)] = {"vis": vis, "prov": {}, "poss": {}, "hint": None}
            continue
        table[",".join(key)] = {
            "vis": vis,
            "prov": desk.provable(vis, placed),
            "poss": desk.possible(vis, placed),
            "hint": desk.best_hint(placed),
        }
    return table


def encode_table(table):
    return base64.b64encode(json.dumps(table, separators=(",", ":"), sort_keys=True).encode()).decode()


def decode_table(b64):
    return json.loads(base64.b64decode(b64).decode())


def verify_table(desk, b64):
    """Decode a table and re-check every state against the solver. Returns a list of problems."""
    full = decode_table(b64)
    table = full["states"]
    problems = []
    if full["means"] != {c["id"]: c["means"] for c in desk.data["cards"]}:
        problems.append("meanings differ")
    if full["clues"] != {c["id"]: c["t"] for c in desk.data["clues"]}:
        problems.append("clue texts differ")
    states = desk.reachable_states()
    keys = {",".join(k) for k in states}
    if set(table) != keys:
        problems.append(f"table has {len(table)} states, solver reaches {len(keys)}")
    for key, placed in states.items():
        row = table.get(",".join(key))
        if row is None:
            continue
        vis = desk.visible(placed)
        if row["vis"] != vis:
            problems.append(f"state {key}: visible clues differ")
        if len(placed) == len(desk.cards):
            continue
        if row["prov"] != desk.provable(vis, placed):
            problems.append(f"state {key}: provable differs")
        if row["poss"] != desk.possible(vis, placed):
            problems.append(f"state {key}: possible differs")
        if row["hint"] != desk.best_hint(placed):
            problems.append(f"state {key}: hint differs")
    return problems


def desk_id(data):
    """Keys the page's saved progress, so a regenerated desk never inherits an old one's state.
    Hashes everything that changes the puzzle: cards, clues, stories, counts and kinds."""
    core = json.dumps({k: data.get(k) for k in ("per", "kinds", "stories", "cards", "clues")}, sort_keys=True)
    return hashlib.sha1(core.encode()).hexdigest()[:8]


def public_desk(data):
    """What the page may show in plain text: no homes, no clue rules, no meanings (each one
    names its story) and only the START clues' wording. The rest is in the encoded table."""
    return {
        "per": data["per"],
        "rule": data["rule"],
        "stories": [{"head": s["head"], "dl": s["dl"], "blurb": s["blurb"]} for s in data["stories"]],
        "cards": [{"id": c["id"], "t": c["t"]} for c in data["cards"]],
        "clues": [{"id": c["id"], "t": c["t"] if c.get("start") else ""} for c in data["clues"]],
    }


# ---------- Page (C3.3) ----------

def render_page(data, path, today, theme, label, deck_href="deck.html", word_key="",
                analytics="", is_latest=True):
    """Write desk.html for one desk. `word_key` is the word puzzle's localStorage key
    ("hope-puzzle-<date>-<puzzle_id>"), so the share line can include the word result."""
    from deck import env                                   # Jinja env with nice_date
    desk = Desk(data)
    passed, rules, _ = check(desk)
    if not passed:
        failed = [name for name, ok in rules.items() if not ok]
        raise DeskError(f"desk fails quality rules: {', '.join(failed)}")
    table = build_table(desk)
    problems = verify_table(desk, encode_table(table))
    if problems:
        raise DeskError(f"state table doesn't match the solver: {problems[:3]}")
    html = env.get_template("desk.html").render(
        today=today, theme=theme, label=label,
        desk=public_desk(data), table_b64=encode_table(table), desk_id=desk_id(data),
        deck_href=deck_href, word_key=word_key, analytics=analytics, is_latest=is_latest,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    return path


# ---------- Command line ----------

def load_samples(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", metavar="SAMPLES", help="run the quality rules on every desk in a samples file")
    ap.add_argument("--table", metavar="SAMPLES", help="build each state table and verify it against the solver")
    ap.add_argument("--render", metavar="SAMPLES", help=f"write a test desk.html per sample under {OUTPUT.relative_to(ROOT)}/")
    ap.add_argument("-v", "--verbose", action="store_true", help="show every rule, not just failures")
    args = ap.parse_args(argv)
    if not (args.check or args.table or args.render):
        ap.print_help()
        return 0

    ok = True
    if args.check:
        for s in load_samples(args.check):
            passed, rules, stats = check(Desk(s["desk"]))
            ok &= passed
            print(f"{s['label']} · {s['size']}: {'PASS' if passed else 'FAIL'}  "
                  f"openers=[{','.join(stats['openers'])}] states={stats['states']} "
                  f"avg-provable={stats['avg_provable']:.2f} chain={stats['chain']:.2f} "
                  f"longest-proof={stats['longest_proof']}")
            for name, v in rules.items():
                if not v or args.verbose:
                    print(f"   {'✓' if v else '✗'} {name}")
            if stats["dead_clues"]:
                print(f"   dead clues: {', '.join(stats['dead_clues'])}")

    if args.table:
        for s in load_samples(args.table):
            desk = Desk(s["desk"])
            b64 = encode_table(build_table(desk))
            problems = verify_table(desk, b64)
            ok &= not problems
            print(f"{s['label']} · {s['size']}: table {len(decode_table(b64)['states'])} states, "
                  f"{len(b64):,} bytes base64 · {'OK' if not problems else 'MISMATCH'}")
            for p in problems:
                print("   " + p)

    if args.render:
        samples = load_samples(args.render)
        links = []
        for n, s in enumerate(samples, start=1):
            path = render_page(s["desk"], OUTPUT / f"{n}" / "desk.html", today=s["date"],
                               theme=s["theme"], label=f"{s['label']} · {s['size']}", is_latest=False)
            links.append(f'<li><a href="{n}/desk.html">{html.escape(s["label"])} · {html.escape(s["size"])}</a></li>')
            print(f"wrote {path.relative_to(ROOT)}")
        (OUTPUT / "index.html").write_text(
            "<!doctype html><meta charset=utf-8><title>Copy Desk samples</title>"
            f"<h1>Copy Desk samples</h1><ul>{''.join(links)}</ul>", encoding="utf-8")
        print(f"open {(OUTPUT / 'index.html').relative_to(ROOT)}")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))      # so "from deck import env" works
    sys.exit(main())
