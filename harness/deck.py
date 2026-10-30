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


def render_deck(title, user_answer, stories):
    """Fill the deck template with stories, save it as HTML and open it."""
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
            "why_it_matters": "You asked about the ocean: reefs can bounce back when given a chance.",
            "url": "https://www.theguardian.com/environment/oceans",
            "date": "2026-10-28",
        },
        {
            "headline": "Whale numbers climb off Brazil",
            "summary": "Humpback whales have returned to near pre-whaling numbers in the South Atlantic.",
            "why_it_matters": "Protection works: a species once nearly gone is thriving again.",
            "url": "https://www.theguardian.com/environment/whales",
            "date": "2026-10-27",
        },
        {
            "headline": "High seas treaty comes into force",
            "summary": "Enough countries have ratified the treaty to protect international waters.",
            "why_it_matters": "Two-thirds of the ocean finally gets a legal path to protection.",
            "url": "https://www.theguardian.com/environment/marine-life",
            "date": "2026-10-25",
        },
    ]
    print(render_deck("Good news from the ocean", "any good ocean news?", sample))
