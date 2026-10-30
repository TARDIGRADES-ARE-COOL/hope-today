"""Part 2: the daily run. Nobody types a topic; the agent finds where this week's good news is."""
import json
from datetime import date, timedelta
from pathlib import Path

from llm import client
from tools import IMAGES, search_news

HISTORY = Path(__file__).resolve().parent.parent / "daily" / "history.json"
TOPIC_COOLDOWN_DAYS = 30

# Runs once a day for everyone, so a stronger model than the agent's is cheap here.
JUDGE_MODEL = "gpt-5.4-mini"
JUDGE_PROMPT = (
    "You are the editor of a good-news app. Score each story 0-10 on three things:\n"
    "hopeful: is this genuinely good news? Real progress, a solution, a recovery, a discovery, "
    "kindness, a problem getting smaller. Warnings, disasters, crime, scandals, deaths and "
    "'experts fear' stories score low even if they mention a solution.\n"
    "significant: does it matter to many people or the planet, beyond a tiny local story?\n"
    "credible: is it a real, specific development (a study, a law, a measured result), "
    "not hype, opinion or a product launch?\n"
    "Give a short reason. Score every story; use its id."
)
JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "scores": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "hopeful": {"type": "integer"},
                    "significant": {"type": "integer"},
                    "credible": {"type": "integer"},
                    "reason": {"type": "string"},
                },
                "required": ["id", "hopeful", "significant", "credible", "reason"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["scores"],
    "additionalProperties": False,
}

# Good-news-friendly corners of the Guardian, as exact tag ids (all checked to be live).
SECTIONS = {
    "science": "science/science",
    "environment": "environment/environment",
    "health": "society/health",
    "technology": "technology/technology",
    "wildlife": "environment/wildlife",
    "space": "science/space",
    "global development": "global-development/global-development",
}
WINDOW_DAYS = 7


def sweep():
    """Step 1: every recent news article from the sections above, each url once."""
    since = (date.today() - timedelta(days=WINDOW_DAYS)).isoformat()
    candidates = {}
    for section, tag in SECTIONS.items():
        results = search_news(tag, since=since, page_size=50)
        if isinstance(results, dict):                    # search_news error: no news this week
            continue
        for story in results:
            # The same article can sit in two sections; keep the first.
            if story["url"] not in candidates:
                candidates[story["url"]] = {**story, "section": section, "image": IMAGES.get(story["url"])}
    return list(candidates.values())


def judge(candidates):
    """Step 2: score every candidate in one call, from its title and snippet."""
    # Numbered ids, so the model never has to copy urls.
    listing = "\n".join(
        f"{i}. [{s['section']}] {s['title']} | {s['snippet']}" for i, s in enumerate(candidates)
    )
    response = client.chat.completions.create(
        model=JUDGE_MODEL,
        messages=[
            {"role": "system", "content": JUDGE_PROMPT},
            {"role": "user", "content": listing},
        ],
        # strict: the reply is guaranteed to match JUDGE_SCHEMA.
        response_format={"type": "json_schema", "json_schema": {
            "name": "scores", "strict": True, "schema": JUDGE_SCHEMA}},
    )
    scores = {s["id"]: s for s in json.loads(response.choices[0].message.content)["scores"]}

    # Code check: a story the model skipped counts as not hopeful, never as a free pass.
    judged = []
    for i, story in enumerate(candidates):
        score = scores.get(i, {"hopeful": 0, "significant": 0, "credible": 0, "reason": "not scored"})
        judged.append({**story, **{k: score[k] for k in ("hopeful", "significant", "credible", "reason")}})
    return judged


def strong(judged):
    """The stories worth building a day around, best first."""
    keep = [s for s in judged if s["hopeful"] >= 7 and s["significant"] >= 5 and s["credible"] >= 7]
    return sorted(keep, key=lambda s: s["hopeful"] + s["significant"], reverse=True)


def load_history(path=HISTORY):
    """Past days: every story url shown, and every topic with its date."""
    if not path.exists():
        return {"urls": [], "topics": []}
    return json.loads(path.read_text(encoding="utf-8"))


def save_day(history, topic, answer, urls, day=None, path=HISTORY):
    """Remember today's topic and stories so they don't come back."""
    history["topics"].append({"date": (day or date.today()).isoformat(), "topic": topic, "answer": answer})
    history["urls"].extend(u for u in urls if u not in history["urls"])
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(history, indent=2), encoding="utf-8")


def unseen(candidates, history):
    """Drop stories already shown on a past day. Never repeat a story."""
    shown = set(history["urls"])
    return [s for s in candidates if s["url"] not in shown]


def blocked_answers(history, today=None):
    """Answers used in the last 30 days. The topic picker must not choose these."""
    cutoff = ((today or date.today()) - timedelta(days=TOPIC_COOLDOWN_DAYS)).isoformat()
    return {t["answer"].upper() for t in history["topics"] if t["date"] > cutoff}


if __name__ == "__main__":
    found = unseen(sweep(), load_history())
    print(f"{len(found)} new candidate articles from the last {WINDOW_DAYS} days")

    judged = judge(found)
    keep = strong(judged)
    print(f"{len(keep)} strong good-news stories (hopeful 7+, significant 5+, credible 7+)\n")
    for s in keep:
        print(f"  H{s['hopeful']} S{s['significant']} C{s['credible']}  [{s['section']}] {s['title'][:75]}")
        print(f"      {s['reason'][:110]}")

    print("\nLowest 5 on hopeful (should be bad news):")
    for s in sorted(judged, key=lambda s: s["hopeful"])[:5]:
        print(f"  H{s['hopeful']}  {s['title'][:80]}")
