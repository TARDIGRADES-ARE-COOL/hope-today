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


GROUP_PROMPT = (
    "These are this week's best good-news stories. Group them into possible topics for a daily "
    "word puzzle, best topic first. For each topic give:\n"
    "topic: a short name (e.g. 'Protecting wild land').\n"
    "answer: ONE common English word, 4-9 letters, letters only, that a player could guess as the "
    "topic (e.g. NATURE, SOLAR, CORAL). Not a name, not an acronym, not two words. Pick a "
    "vivid, specific word that is fun to guess, not a plain or vague one (NATURE over LAND, "
    "SOLAR over ENERGY, CANCER over HEALTH).\n"
    "story_ids: the 3-5 stories that clearly belong to this topic (use their ids).\n"
    "why: one sentence on why this topic is a happy one for today.\n"
    "A story may appear in more than one topic. Prefer topics whose stories are clearly happy."
)
GROUP_SCHEMA = {
    "type": "object",
    "properties": {
        "groups": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string"},
                    "answer": {"type": "string"},
                    "story_ids": {"type": "array", "items": {"type": "integer"}},
                    "why": {"type": "string"},
                },
                "required": ["topic", "answer", "story_ids", "why"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["groups"],
    "additionalProperties": False,
}


def answer_problems(answer, blocked):
    """What's wrong with a proposed answer word, or [] if it's fine."""
    problems = []
    word = answer.strip().upper()
    if not word.isalpha() or not 4 <= len(word) <= 9:
        problems.append(f"answer '{answer}' must be one word of 4-9 letters")
    if word in blocked:
        problems.append(f"answer '{word}' was used in the last {TOPIC_COOLDOWN_DAYS} days")
    return problems


def fix_answer(group, blocked):
    """A good topic with a bad answer word: ask for another word instead of dropping the topic."""
    response = client.chat.completions.create(
        model=JUDGE_MODEL,
        messages=[{"role": "user", "content": (
            f"Topic: {group['topic']}. The answer word '{group['answer']}' doesn't work: "
            f"{'; '.join(answer_problems(group['answer'], blocked))}. Give ONE other common English "
            "word, 4-9 letters, letters only, vivid and fun to guess, that a player could guess as "
            "this topic." + (f" Not any of: {sorted(blocked)}." if blocked else "")
        )}],
        response_format={"type": "json_schema", "json_schema": {"name": "answer", "strict": True, "schema": {
            "type": "object", "properties": {"answer": {"type": "string"}},
            "required": ["answer"], "additionalProperties": False}}},
    )
    return json.loads(response.choices[0].message.content)["answer"]


def group_problems(group, keep, blocked):
    """Everything wrong with one proposed topic, or [] if it can be a day."""
    ids = group["story_ids"]
    problems = answer_problems(group["answer"], blocked)
    if not 3 <= len(set(ids)) <= 5:
        problems.append(f"needs 3-5 different stories, got {len(set(ids))}")
    if any(not 0 <= i < len(keep) for i in ids):
        problems.append("uses a story id that isn't in the list")
    return problems


def pick_topics(keep, blocked):
    """Step 3-4: group the strong stories into topics; return the valid ones, best first."""
    listing = "\n".join(f"{i}. [{s['section']}] {s['title']} | {s['snippet']}" for i, s in enumerate(keep))
    messages = [
        {"role": "system", "content": GROUP_PROMPT},
        {"role": "user", "content": listing + (f"\n\nDo not use these answers: {sorted(blocked)}" if blocked else "")},
    ]
    for attempt in range(2):                  # one retry with the problems spelled out
        response = client.chat.completions.create(
            model=JUDGE_MODEL,
            messages=messages,
            response_format={"type": "json_schema", "json_schema": {
                "name": "groups", "strict": True, "schema": GROUP_SCHEMA}},
        )
        reply = response.choices[0].message.content
        groups = json.loads(reply)["groups"]

        valid, rejected = [], []
        for group in groups:
            problems = group_problems(group, keep, blocked)
            # Only the answer word is wrong: repair the word (up to 3 tries), keep the topic.
            if problems and problems == answer_problems(group["answer"], blocked):
                old, tried = group["answer"], {group["answer"].strip().upper()}
                for _ in range(3):
                    # Failed words go in as "blocked" so the model won't suggest them again.
                    group = {**group, "answer": fix_answer(group, blocked | tried)}
                    if not answer_problems(group["answer"], blocked):
                        break
                    tried.add(group["answer"].strip().upper())
                problems = group_problems(group, keep, blocked)
                if not problems:
                    rejected.append(f"{group['topic']}: answer '{old}' replaced by '{group['answer']}'")
            if problems:
                rejected.append(f"{group['topic']}: {'; '.join(problems)}")
            else:
                ids = list(dict.fromkeys(group["story_ids"]))           # drop repeats, keep order
                valid.append({**group, "answer": group["answer"].strip().upper(),
                              "stories": [keep[i] for i in ids]})
        if valid:
            # Rank in code, not by the model's order: the happiest set of stories wins.
            mean = lambda t, k: sum(s[k] for s in t["stories"]) / len(t["stories"])
            valid.sort(key=lambda t: (mean(t, "hopeful"), mean(t, "significant")), reverse=True)
            return valid, rejected
        messages += [{"role": "assistant", "content": reply},
                     {"role": "user", "content": "None of these work: " + " | ".join(rejected) + ". Try again."}]
    return [], rejected


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
    history = load_history()
    found = unseen(sweep(), history)
    print(f"{len(found)} new candidate articles from the last {WINDOW_DAYS} days")

    keep = strong(judge(found))
    print(f"{len(keep)} strong good-news stories")

    topics, rejected = pick_topics(keep, blocked_answers(history))
    for r in rejected:
        print(f"  rejected by code: {r}")
    if not topics:
        raise SystemExit("No topic today: no group passed the checks.")

    for rank, t in enumerate(topics, start=1):
        avg = sum(s["hopeful"] for s in t["stories"]) / len(t["stories"])
        print(f"\n#{rank}  {t['answer']} ({len(t['answer'])})  {t['topic']}   avg hopeful {avg:.1f}")
        print(f"    {t['why']}")
        for s in t["stories"]:
            print(f"    - H{s['hopeful']}  {s['title'][:85]}")
