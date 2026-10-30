"""Build the public website from daily/: one folder per day, and a home page that opens today's.
Only the pages go online: no day.json, no history, no logs (and never any API keys)."""
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DAILY = ROOT / "daily"
SITE = ROOT / "_site"
PAGES = ("index.html", "deck.html")


def build():
    if SITE.exists():
        shutil.rmtree(SITE)
    SITE.mkdir()
    days = sorted(d for d in DAILY.glob("20??-??-??") if (d / "index.html").exists())
    for day in days:
        (SITE / day.name).mkdir()
        for page in PAGES:
            if (day / page).exists():
                shutil.copy(day / page, SITE / day.name / page)

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
