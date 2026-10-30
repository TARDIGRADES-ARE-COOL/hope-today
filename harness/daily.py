"""Part 2: the daily run. Nobody types a topic; the agent finds where this week's good news is."""
from datetime import date, timedelta

from tools import IMAGES, search_news

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


if __name__ == "__main__":
    found = sweep()
    print(f"{len(found)} candidate articles from the last {WINDOW_DAYS} days\n")
    for section in SECTIONS:
        mine = [s for s in found if s["section"] == section]
        print(f"{section} ({len(mine)})")
        for story in mine[:4]:
            print(f"   {story['date']}  {story['title'][:80]}")
        if len(mine) > 4:
            print(f"   ... and {len(mine) - 4} more")
