"""Part 2, round two: "Branch out". Type words linked to today's answer (SOLAR: sun, panel, eclipse...);
rarer words score more, and words from today's stories score extra. The AI lists the words; a second
pass removes bad ones; code scores rarity, marks the news words and picks the gem.
(The first version asked to 'name' things in a category, like moons; that leaned on general knowledge.)"""
import base64
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
NEWS_BONUS = 2                # a word that appears in today's stories: reading pays off
GEM_MIN_ZIPF = 1.0            # the gem should be rare, but something at least some players know

BRANCH_SCHEMA = {
    "type": "object",
    "properties": {
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
    "required": ["answers"],
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
    """The AI lists words people link with the answer, common to rare."""
    response = client.chat.completions.create(
        model=BRANCH_MODEL,
        messages=[{"role": "user", "content": (
            f"Today's puzzle answer was {answer}; the good news is about '{topic}'. Stories: "
            f"{'; '.join(story_titles)}.\n"
            f"In a second round, players type as many words linked to {answer} as they can. List "
            f"120-180 words or short common terms (at most 3 words) that people strongly link with "
            f"{answer}: things, places, jobs, actions, ideas, from very common to rare (for CORAL: "
            "reef, diver, snorkel, polyp, clownfish, bleaching, atoll, Great Barrier Reef). Start "
            "with the 40 most obvious SINGLE words a player would type first, even general ones (for "
            "CORAL: sea, ocean, fish, reef, pink, colour, island), then rarer words and short terms. "
            f"Words that often go with {answer} count on their own (for CORAL: 'reef' from 'coral reef'). "
            f"Each with any common alternative forms or spellings as aliases. Never a term containing {answer}."
        )}],
        response_format={"type": "json_schema", "json_schema": {
            "name": "branch", "strict": True, "schema": BRANCH_SCHEMA}},
    )
    return json.loads(response.choices[0].message.content)


def misfits(answer, names):
    """A second pass: which words aren't really linked to the answer?"""
    response = client.chat.completions.create(
        model=CHECK_MODEL,
        messages=[{"role": "user", "content": (
            f"Players list words linked to {answer}. Which of these are NOT linked to it at all: a real "
            f"stretch, or not a real word or term? Everyday words a person would naturally say about "
            f"{answer} DO count, even general ones (for CORAL: sea, fish, colour). List only the clear misfits.\n"
            f"{json.dumps(names)}"
        )}],
        response_format={"type": "json_schema", "json_schema": {"name": "misfits", "strict": True, "schema": {
            "type": "object", "properties": {"misfits": {"type": "array", "items": {"type": "string"}}},
            "required": ["misfits"], "additionalProperties": False}}},
    )
    return {normal(n) for n in json.loads(response.choices[0].message.content)["misfits"]}


def make_branch(topic, answer, story_titles, article_texts):
    """Build round two: prompt, cleaned and scored answers, the news words and the gem."""
    raw = propose(topic, answer, story_titles)
    bad = misfits(answer, [a["name"] for a in raw["answers"]])

    answers, seen = [], set()
    for a in raw["answers"]:
        key = normal(a["name"])
        # Code check too: a term containing the answer ("solar panel") is a free point.
        if not key or key in seen or key in bad or normal(answer) in key:
            continue
        seen.add(key)
        aliases = [x for x in a["aliases"] if normal(x) and normal(x) != key and normal(answer) not in normal(x)]
        plain = everyday_name(a["name"])
        if plain and normal(plain) not in {normal(x) for x in aliases}:
            aliases.append(plain)                     # typing "otter" should work too
        zipf, tier, points = rarity([a["name"], *aliases])
        answers.append({"name": a["name"], "aliases": aliases, "zipf": round(zipf, 2),
                        "tier": tier, "points": points})

    # News words: answers that appear in today's articles score extra; the rarest is the gem.
    text = " " + re.sub(r"[^a-z]+", " ", " ".join(article_texts).lower()) + " "
    spaced = lambda n: re.sub(r"[^a-z]+", " ", n.lower()).strip()
    mentioned = lambda n: any(f" {spaced(n)}{end} " in text for end in ("", "s", "es"))   # plurals too
    in_news = [a for a in answers if a["zipf"] >= GEM_MIN_ZIPF and any(
        mentioned(n) for n in [a["name"], *a["aliases"]])]
    # No answer in the stories means no gem today: a random rare answer would break the promise.
    for a in in_news:
        a.update(news=True, points=a["points"] + NEWS_BONUS)
    gem = min(in_news, key=lambda a: a["zipf"]) if in_news else None
    if gem:
        gem.update(tier="Gem", points=GEM_POINTS)

    return {"prompt": f"Words linked to {answer}", "answers": answers, "gem": gem["name"] if gem else None,
            "gem_from_news": bool(in_news), "dropped": len(raw["answers"]) - len(answers)}


def page_answers(branch):
    """The answer list as the puzzle page reads it: short keys, base64 so answers aren't plain text."""
    return base64.b64encode(json.dumps(
        [{"n": a["name"], "a": a["aliases"], "t": a["tier"], "p": a["points"], "w": bool(a.get("news"))}
         for a in branch["answers"]]).encode()).decode()


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
    print("News words:", [a["name"] for a in branch["answers"] if a.get("news")])
    for tier in ["Common", "Uncommon", "Rare", "Very rare", "Gem"]:
        names = [a["name"] for a in branch["answers"] if a["tier"] == tier]
        print(f"  {tier:9} ({len(names):3}): {', '.join(names[:8])}{' ...' if len(names) > 8 else ''}")
    print("Gem:", branch["gem"], "(found in today's articles)" if branch["gem_from_news"] else "(rarest overall)")
