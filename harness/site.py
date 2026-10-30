"""Build the public website from daily/: one folder per day, and a home page that opens today's.
Every day's pages are re-rendered from day.json with the CURRENT templates, so design fixes
reach the live site (and past days) on the next publish, not just tomorrow's puzzle.
Only the pages go online: no day.json, no history, no logs (and never any API keys)."""
import base64
import hashlib
import json
import shutil
from pathlib import Path

from deck import env

ROOT = Path(__file__).resolve().parent.parent
DAILY = ROOT / "daily"
SITE = ROOT / "_site"


def render_day(day_dir, out_dir):
    """Write index.html (the puzzle) and deck.html (the reward) for one day."""
    d = json.loads((day_dir / "day.json").read_text(encoding="utf-8"))
    p = d["puzzle"]
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "index.html").write_text(env.get_template("puzzle.html").render(
        today=d["date"], puzzle=p, branch=None, branch_b64="",     # Branch out is switched off
        puzzle_id=hashlib.sha1((p["sentence"] or p.get("image", "")).encode()).hexdigest()[:8],
        answer_b64=base64.b64encode(d["answer"].encode()).decode(),
    ), encoding="utf-8")
    (out_dir / "deck.html").write_text(env.get_template("deck.html").render(
        title=f"Good news: {d['topic']}", user_answer="", topic=d["topic"],
        stories=d["stories"], today=d["date"],
    ), encoding="utf-8")


def build():
    if SITE.exists():
        shutil.rmtree(SITE)
    SITE.mkdir()
    days = sorted(d for d in DAILY.glob("20??-??-??") if (d / "day.json").exists())
    for day in days:
        render_day(day, SITE / day.name)

    # Home page: send players to the newest puzzle.
    target = f"{days[-1].name}/" if days else None
    (SITE / "index.html").write_text(f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Hope Today</title>
  {f'<meta http-equiv="refresh" content="0; url={target}">' if target else ''}
</head>
<body style="background:#2c3620;color:#e3e2da;font-family:Georgia,serif;padding:2rem">
  {f'<p><a style="color:inherit" href="{target}">Open today\'s puzzle</a></p>' if target
   else "<p>The first puzzle is on its way. Come back tomorrow morning.</p>"}
</body>
</html>
""", encoding="utf-8")
    return days


if __name__ == "__main__":
    days = build()
    print(f"Built _site/ with {len(days)} day(s); home page opens {days[-1].name if days else 'nothing yet'}")
