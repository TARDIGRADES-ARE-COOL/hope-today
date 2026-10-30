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
from desk import desk_id, render_page

ROOT = Path(__file__).resolve().parent.parent
DAILY = ROOT / "daily"
SITE = ROOT / "_site"
SITE_URL = "https://tardigrades-are-cool.github.io/hope-today/"     # where GitHub Pages serves it
PREVIEW_TITLE = "Hope Today: a daily good-news puzzle"
PREVIEW_TEXT = "One word puzzle a day. Solve it to unlock today's good news."
# GoatCounter code for privacy-friendly stats (no cookies, no personal data). Empty = off.
ANALYTICS = "hopetoday"


def puzzle_id(p):
    """Same id the puzzle page uses to save progress (so the archive can show it)."""
    return hashlib.sha1((p["sentence"] or p.get("image", "")).encode()).hexdigest()[:8]


def live_desk(d):
    """The day's Copy Desk if it is live. Shadow desks ("live": false) are never published."""
    desk = d.get("desk")
    return desk if desk and desk.get("live") else None


def render_day(day_dir, out_dir, is_latest=True):
    """Write index.html (the puzzle), desk.html (Copy Desk, on days that have a live one)
    and deck.html (the reward) for one day."""
    d = json.loads((day_dir / "day.json").read_text(encoding="utf-8"))
    p = d["puzzle"]
    out_dir.mkdir(parents=True, exist_ok=True)
    previews = dict(site_url=SITE_URL, preview_title=PREVIEW_TITLE, preview_text=PREVIEW_TEXT, analytics=ANALYTICS)
    desk = live_desk(d)
    if desk:
        try:
            render_page(desk, out_dir / "desk.html", today=d["date"], theme=d["topic"], label="",
                        word_key=f"hope-puzzle-{d['date']}-{puzzle_id(p)}", analytics=ANALYTICS,
                        is_latest=is_latest)
        except Exception as e:      # noqa: BLE001 (one bad desk must never break the archive)
            print(f"{day_dir.name}: desk left out ({type(e).__name__}: {e})")
            desk = None
    (out_dir / "index.html").write_text(env.get_template("puzzle.html").render(
        **previews, page_url=f"{SITE_URL}{day_dir.name}/", has_desk=bool(desk),
        today=d["date"], puzzle=p, branch=None, branch_b64="",     # Branch out is switched off
        puzzle_id=puzzle_id(p), is_latest=is_latest,
        answer_b64=base64.b64encode(d["answer"].encode()).decode(),
    ), encoding="utf-8")
    (out_dir / "deck.html").write_text(env.get_template("deck.html").render(
        **previews, page_url=f"{SITE_URL}{day_dir.name}/deck.html",
        title=f"Good news: {d['topic']}", user_answer="", topic=d["topic"],
        stories=d["stories"], today=d["date"],
    ), encoding="utf-8")


def build():
    if SITE.exists():
        shutil.rmtree(SITE)
    SITE.mkdir()
    days = sorted(d for d in DAILY.glob("20??-??-??") if (d / "day.json").exists())
    for day in days:
        render_day(day, SITE / day.name, is_latest=(day == days[-1]))

    # Past puzzles: newest first, no topics or answers, each player's status from their browser.
    listing = []
    for day in reversed(days):
        d = json.loads((day / "day.json").read_text(encoding="utf-8"))
        p, desk = d["puzzle"], live_desk(d)
        listing.append({"date": day.name, "length": p["length"], "puzzle_id": puzzle_id(p),
                        "desk_key": f"hope-desk-{day.name}-{desk_id(desk)}"
                        if desk and (SITE / day.name / "desk.html").exists() else ""})
    (SITE / "archive").mkdir()
    (SITE / "archive" / "index.html").write_text(env.get_template("archive.html").render(
        days=listing, today=days[-1].name if days else "",
        site_url=SITE_URL, preview_text=PREVIEW_TEXT, analytics=ANALYTICS), encoding="utf-8")
    shutil.copy(ROOT / "assets" / "og.png", SITE / "og.png")          # the link-preview picture

    # Home page: send players to the newest puzzle.
    target = f"{days[-1].name}/" if days else None
    (SITE / "index.html").write_text(f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Hope Today</title>
  <meta name="description" content="{PREVIEW_TEXT}">
  <meta property="og:type" content="website">
  <meta property="og:site_name" content="Hope Today">
  <meta property="og:title" content="{PREVIEW_TITLE}">
  <meta property="og:description" content="{PREVIEW_TEXT}">
  <meta property="og:url" content="{SITE_URL}">
  <meta property="og:image" content="{SITE_URL}og.png">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">
  <meta property="og:image:alt" content="Hope Today: a pixel-art sunrise behind a paper card">
  <meta name="twitter:card" content="summary_large_image">
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
