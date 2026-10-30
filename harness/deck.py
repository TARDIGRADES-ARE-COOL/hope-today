import webbrowser
from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "templates"
OUTPUT = ROOT / "output"

# autoescape: story text comes from the model and from articles, so treat it as
# plain text. A "<script>" in a headline shows up as text instead of running.
env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=True)

REQUIRED = ["headline", "summary", "key_points", "why_it_matters", "url"]


def check_stories(stories):
    """Return a readable problem for the model to fix, or None if all good."""
    if not 3 <= len(stories) <= 7:
        return f"Need 3 to 7 stories, got {len(stories)}."

    for n, story in enumerate(stories, start=1):
        for field in REQUIRED:
            if not story.get(field):
                return f"Story {n} is missing '{field}'."
        if not 2 <= len(story["key_points"]) <= 4:
            return f"Story {n} needs 2 to 4 key_points, got {len(story['key_points'])}."
    return None


def render_deck(title, user_answer, stories):
    """Fill the deck template with stories, save it as HTML and open it."""
    # Errors go back to the model as text (not raised) so it can fix and retry.
    problem = check_stories(stories)
    if problem:
        return {"error": problem}

    template = env.get_template("deck.html")
    html = template.render(
        title=title,
        user_answer=user_answer,
        stories=stories,
        today=date.today().isoformat(),
    )

    OUTPUT.mkdir(exist_ok=True)
    path = OUTPUT / f"deck-{date.today().isoformat()}.html"
    path.write_text(html, encoding="utf-8")

    webbrowser.open(path.as_uri())
    return {"path": str(path), "slides": len(stories)}


if __name__ == "__main__":
    # Fake stories so we can test the deck without calling OpenAI or Guardian.
    sample = [
        {
            "headline": "Coral reef shows record recovery",
            "summary": "Surveys found coral cover on parts of the reef at its highest in decades.",
            "key_points": [
                "Coral cover reached 36%, the highest since records began in 1986",
                "Recovery was strongest on the northern reef",
                "Scientists warn heatwaves could still reverse the gains",
            ],
            "why_it_matters": "You asked about the ocean: reefs can bounce back when given a chance.",
            "url": "https://www.theguardian.com/environment/oceans",
            "date": "2026-10-28",
        },
        {
            "headline": "Whale numbers climb off Brazil",
            "summary": "Humpback whales have returned to near pre-whaling numbers in the South Atlantic.",
            "key_points": [
                "Population grew from about 450 in the 1950s to around 25,000",
                "Commercial whaling bans made the difference",
            ],
            "why_it_matters": "Protection works: a species once nearly gone is thriving again.",
            "url": "https://www.theguardian.com/environment/whales",
            "date": "2026-10-27",
        },
        {
            "headline": "High seas treaty comes into force",
            "summary": "Enough countries have ratified the treaty to protect international waters.",
            "key_points": [
                "60 countries ratified, triggering the treaty",
                "Allows marine protected areas outside national waters",
                "Covers about two-thirds of the world's ocean",
            ],
            "why_it_matters": "Two-thirds of the ocean finally gets a legal path to protection.",
            "url": "https://www.theguardian.com/environment/marine-life",
            "date": "2026-10-25",
        },
    ]
    # Bad input: these should return errors and write no file.
    print(render_deck("Too few", "test", sample[:2]))
    print(render_deck("No url", "test", [sample[0], sample[1], {**sample[2], "url": ""}]))

    print(render_deck("Good news from the ocean", "any good ocean news?", sample))
