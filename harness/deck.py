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


def nice_date(iso):
    """'2026-10-25' → '25 Oct 2026'. Leaves anything else untouched."""
    try:
        return date.fromisoformat(iso).strftime("%-d %b %Y")
    except (TypeError, ValueError):
        return iso


env.filters["nice_date"] = nice_date

REQUIRED = ["headline", "summary", "key_points", "why_it_matters", "url"]


def check_stories(stories):
    """Return every problem for the model to fix in one go, or None if all good."""
    # Min is 1, not 3: a short honest deck beats one padded with weak or old stories.
    if not 1 <= len(stories) <= 7:
        return f"Need 1 to 7 stories, got {len(stories)}."

    # Collect all problems: reporting only the first makes the model retry once per problem.
    problems = []
    for n, story in enumerate(stories, start=1):
        for field in REQUIRED:
            if not story.get(field):
                problems.append(f"Story {n} is missing '{field}'.")
        points = story.get("key_points") or []
        if len(points) > 4:
            story["key_points"] = points[:4]          # small problem: fix it, don't reject
        elif len(points) == 1:
            problems.append(f"Story {n} needs 2 to 4 key_points, got 1.")
    return " ".join(problems) or None


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
    # Real stories and photos from a past run, so the design is built against real
    # text lengths and images, without calling OpenAI or Guardian.
    sample = [
        {
            "headline": "Roman colour-changing glass",
            "summary": "Scientists have recreated the glass of the Lycurgus Cup, which glows green or red depending on the light.",
            "key_points": [
                "Made by a team at the University of Sheffield",
                "The effect comes from gold and silver nanoparticles in the glass",
                "The Roman recipe had been lost for about 1,600 years",
            ],
            "why_it_matters": "Old craft and new science meeting: a lost skill brought back by curiosity.",
            "url": "https://www.theguardian.com/science/2026/oct/25/scientists-rediscover-ancient-roman-colour-changing-glass",
            "image": "https://media.guim.co.uk/36274fa02586505fbfdfcdc84de3302a298d0f0e/84_0_2690_2152/1000.jpg",
            "date": "2026-10-25",
        },
        {
            "headline": "Bananas get a lifeline",
            "summary": "Researchers have bred a fertile version of the Cavendish, the banana most of the world eats.",
            "key_points": [
                "Cavendish plants are clones, so one disease can wipe them out",
                "A fertile plant means new, disease-resistant varieties can be bred",
                "The aim is to replace the vulnerable Cavendish, not just protect it",
            ],
            "why_it_matters": "A staple food for millions gets a real chance against the disease threatening it.",
            "url": "https://www.theguardian.com/global-development/2026/oct/22/have-scientists-finally-found-a-way-to-save-the-banana-from-disaster",
            "image": "https://media.guim.co.uk/acd57c35350ea477e5e54107c57603bee7d5a111/127_0_1705_1365/1000.jpg",
            "date": "2026-10-22",
        },
        {
            "headline": "Orangutans pick laughter",
            "summary": "Orangutans preferred food linked to the sound of laughter, a new study suggests.",
            "key_points": [
                "Apes chose between foods paired with different sounds",
                "Food linked to laughter was picked more often",
            ],
            "why_it_matters": "Joy may be a language we share with our closest relatives.",
            "url": "https://www.theguardian.com/science/2026/oct/21/orangutans-prefer-food-laughter-sounds-study",
            "image": "https://media.guim.co.uk/57d6699032b4f8a4e77d45cb0c3923d3dafb9870/721_0_4320_3456/1000.jpg",
            "date": "2026-10-21",
        },
        {
            "headline": "Japan heads for Phobos",
            "summary": "Japan has launched a mission to land on Mars's moon Phobos and bring rocks back to Earth.",
            "key_points": [
                "The first mission to return samples from Phobos",
                "Expected to reach Mars orbit in August 2027",
                "Five space agencies are working together on it",
            ],
            "why_it_matters": "Countries pooling their science to answer how Mars and its moons were born.",
            "url": "https://www.theguardian.com/world/2026/oct/20/japan-mars-moon-mission-phobos-collect-rocks",
            "image": "https://media.guim.co.uk/8b8c7baa851530aa5cc92126c0aa8893b34bf1b7/0_63_3016_2414/500.jpg",
            "date": "2026-10-19",
        },
    ]
    # Bad input: these should return errors and write no file.
    print(render_deck("Too few", "test", []))
    print(render_deck("No url", "test", [sample[0], sample[1], {**sample[2], "url": ""}]))

    print(render_deck("Good news in science", "good news about science and nature", sample))
