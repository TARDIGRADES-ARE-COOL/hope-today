"""Part 2: the daily run. Nobody types a topic; the agent finds where this week's good news is."""
import json
from datetime import date, timedelta
from pathlib import Path

from tools import IMAGES, search_news

HISTORY = Path(__file__).resolve().parent.parent / "daily" / "history.json"
TOPIC_COOLDOWN_DAYS = 30

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
    print(f"{len(found)} new candidate articles from the last {WINDOW_DAYS} days\n")
    for section in SECTIONS:
        mine = [s for s in found if s["section"] == section]
        print(f"{section} ({len(mine)})")
        for story in mine[:4]:
            print(f"   {story['date']}  {story['title'][:80]}")
        if len(mine) > 4:
            print(f"   ... and {len(mine) - 4} more")
