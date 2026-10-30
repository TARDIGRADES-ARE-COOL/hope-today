"""Part 2, round two: "Branch out". Name things linked to today's topic; rarer answers score more.
The AI proposes the prompt and answers; a second pass removes bad ones; code scores rarity and picks the gem."""
import json
import re

from wordfreq import zipf_frequency

from llm import client

BRANCH_MODEL = "gpt-5.5"
CHECK_MODEL = "gpt-5.4-mini"

# Rarity tiers on wordfreq's Zipf scale (higher = more common), calibrated on real names:
# fox 4.7, robin 4.3 | otter 3.4, hedgehog 3.3 | kingfisher 2.9, curlew 2.3 | lapwing 1.9, corncrake 1.4
TIERS = [(3.8, "Common", 1), (3.0, "Uncommon", 2), (2.2, "Rare", 3), (-1, "Very rare", 5)]
GEM_POINTS = 10
GEM_MIN_ZIPF = 1.0            # the gem should be rare, but something at least some players know

BRANCH_SCHEMA = {
    "type": "object",
    "properties": {
        "prompt": {"type": "string"},
        "answers": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "aliases": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["name", "aliases"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["prompt", "answers"],
    "additionalProperties": False,
}


# Formal-name prefixes people drop in everyday speech ("Eurasian otter" -> "otter").
QUALIFIERS = ("european", "eurasian", "common", "northern", "southern", "eastern", "western",
              "american", "african", "asian", "british")


def everyday_name(name):
    first, _, rest = name.partition(" ")
    return rest if first.lower() in QUALIFIERS and rest else None


def normal(text):
    return re.sub(r"[^a-z]", "", text.lower())


def rarity(names):
    """Points and tier from the answer's MOST common name: people say 'blackbird',
    not 'Eurasian blackbird', so the formal name alone would overstate rarity."""
    zipf = max(zipf_frequency(n.lower(), "en") for n in names)
    for floor, tier, points in TIERS:
        if zipf >= floor:
            return zipf, tier, points


def propose(topic, answer, story_titles):
    """The AI writes the prompt and a long list of answers, common to rare."""
    response = client.chat.completions.create(
        model=BRANCH_MODEL,
        messages=[{"role": "user", "content": (
            f"Today's puzzle answer was {answer}; the good news is about '{topic}'. Stories: "
            f"{'; '.join(story_titles)}.\n"
            "Write a short 'Name ...' prompt (at most 10 words) for a second round where players type as many fitting "
            "answers as they can. It must be clearly linked to today's topic, concrete (things with "
            "names, like animals, plants, places, foods), and have at least 80 well-known-to-rare "
            "answers. Example: 'Name animals that could live on a rewilded estate'.\n"
            "Then list 100-150 answers that clearly fit, from very common to rare, each with any "
            "common alternative names as aliases. Real names only, no descriptions."
        )}],
        response_format={"type": "json_schema", "json_schema": {
            "name": "branch", "strict": True, "schema": BRANCH_SCHEMA}},
    )
    return json.loads(response.choices[0].message.content)


def misfits(prompt, names):
    """A second pass: which answers don't really fit the prompt?"""
    response = client.chat.completions.create(
        model=CHECK_MODEL,
        messages=[{"role": "user", "content": (
            f"Prompt: '{prompt}'. Which of these answers do NOT clearly fit it (wrong category, "
            f"not a real name, too vague)? List only those.\n{json.dumps(names)}"
        )}],
        response_format={"type": "json_schema", "json_schema": {"name": "misfits", "strict": True, "schema": {
            "type": "object", "properties": {"misfits": {"type": "array", "items": {"type": "string"}}},
            "required": ["misfits"], "additionalProperties": False}}},
    )
    return {normal(n) for n in json.loads(response.choices[0].message.content)["misfits"]}


def make_branch(topic, answer, story_titles, article_texts):
    """Build round two: prompt, cleaned and scored answers, and the gem."""
    raw = propose(topic, answer, story_titles)
    bad = misfits(raw["prompt"], [a["name"] for a in raw["answers"]])

    answers, seen = [], set()
    for a in raw["answers"]:
        key = normal(a["name"])
        if not key or key in seen or key in bad:
            continue
        seen.add(key)
        aliases = [x for x in a["aliases"] if normal(x) and normal(x) != key]
        plain = everyday_name(a["name"])
        if plain and normal(plain) not in {normal(x) for x in aliases}:
            aliases.append(plain)                     # typing "otter" should work too
        zipf, tier, points = rarity([a["name"], *aliases])
        answers.append({"name": a["name"], "aliases": aliases, "zipf": round(zipf, 2),
                        "tier": tier, "points": points})

    # The gem: the rarest answer that appears in today's articles, so reading pays off.
    text = " " + re.sub(r"[^a-z]+", " ", " ".join(article_texts).lower()) + " "
    spaced = lambda n: re.sub(r"[^a-z]+", " ", n.lower()).strip()
    mentioned = lambda n: any(f" {spaced(n)}{end} " in text for end in ("", "s", "es"))   # plurals too
    in_news = [a for a in answers if a["zipf"] >= GEM_MIN_ZIPF and any(
        mentioned(n) for n in [a["name"], *a["aliases"]])]
    pool = in_news or [a for a in answers if a["zipf"] >= GEM_MIN_ZIPF]
    gem = min(pool, key=lambda a: a["zipf"]) if pool else None
    if gem:
        gem.update(tier="Gem", points=GEM_POINTS)

    return {"prompt": raw["prompt"], "answers": answers, "gem": gem["name"] if gem else None,
            "gem_from_news": bool(in_news), "dropped": len(raw["answers"]) - len(answers)}


if __name__ == "__main__":
    branch = make_branch(
        "Saving wild places", "WILDLIFE",
        ["Wildlife Trusts hit £30m target to buy and rewild huge Northumberland estate",
         "Almost $20m raised to protect majestic tract of land in far north Queensland"],
        ["The estate is home to red squirrels, curlews, otters and black grouse, and could see "
         "beavers and pine martens return. Cassowaries and tree kangaroos live at Wooroora."],
    )
    print("Prompt:", branch["prompt"])
    print(f"{len(branch['answers'])} answers kept, {branch['dropped']} dropped by the check")
    for tier in ["Common", "Uncommon", "Rare", "Very rare", "Gem"]:
        names = [a["name"] for a in branch["answers"] if a["tier"] == tier]
        print(f"  {tier:9} ({len(names):3}): {', '.join(names[:8])}{' ...' if len(names) > 8 else ''}")
    print("Gem:", branch["gem"], "(found in today's articles)" if branch["gem_from_news"] else "(rarest overall)")
