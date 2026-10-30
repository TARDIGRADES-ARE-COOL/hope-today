"""Part 2: wordplay clues for the daily answer. The AI writes them; Python checks every one."""
import html
import json
import re

from wordfreq import zipf_frequency

from llm import client

# Letter-level wordplay is hard for models, so use a stronger one. It runs once a day.
CLUE_MODEL = "gpt-5.5"
SOLVER_MODEL = "gpt-5.4-mini"     # a separate model plays the role of a player
MAX_WORDS = 16                    # the clue has to fit on a phone
NATURAL_MIN = 7                   # how natural a clue sentence must read (0-10)

INSTRUCTIONS = {
    "anagram": "Mix up the letters of a word in this sentence.",
    "hidden": "Today's topic is hidden inside this sentence.",
    "first": "The first letters of some words in this sentence spell today's topic.",
    "backwards": "Today's topic is hidden backwards inside this sentence.",
    "halves": "Two clues, two halves: join them to get today's topic.",
    "pixel": "Guess today's topic from the picture.",
}
# The daily run rotates through these, so the trick changes from day to day.
ROTATION = ["hidden", "anagram", "first", "backwards", "halves"]


def words_of(sentence):
    """The sentence's words, as written (punctuation trimmed off the ends)."""
    return [w.strip(".,;:!?\"'()—–-") for w in sentence.split()]


def letters(text):
    return re.sub(r"[^a-z]", "", text.lower())


def stray_letters(words):
    """Single-letter 'words' other than a and I: a sign of cheating like 'S A N C T U A R Y'."""
    return [w for w in words if len(w) == 1 and w not in ("a", "i")]


def basic_problems(words, answer):
    """Rules every sentence clue shares."""
    problems = []
    if stray_letters(words):
        problems.append("the sentence has stray single letters")
    if letters(answer) in words:
        problems.append("the answer appears in the sentence as a word")
    if len(words) > MAX_WORDS:
        problems.append(f"sentence is over {MAX_WORDS} words")
    return problems


# ---------- Checkers: pure Python, no AI ----------

def check_anagram(sentence, answer, fodder):
    """Problems with a mix-it-up clue, or [] if it works. fodder = the word(s) to mix up."""
    words = [letters(w) for w in words_of(sentence)]
    target = fodder.lower().split()
    problems = []
    # The fodder must be one word, or words side by side, actually in the sentence.
    spots = [i for i in range(len(words)) if words[i:i + len(target)] == [letters(t) for t in target]]
    if not spots:
        problems.append(f"'{fodder}' is not in the sentence")
    if sorted(letters(fodder)) != sorted(letters(answer)):
        problems.append(f"'{fodder}' does not have exactly the letters of {answer}")
    if letters(fodder) == letters(answer):
        problems.append("the word to mix up is the answer itself")
    if not 1 <= len(target) <= 2:
        problems.append("the letters to mix up must be one or two words")
    problems += basic_problems(words, answer)
    return problems, ([spots[0] + k for k in range(len(target))] if spots else [])


def hidden_span(words, target):
    """Where target sits in the sentence's letters, and what's wrong with how it sits."""
    joined, owner = "", []                       # owner[i] = which word letter i came from
    for n, w in enumerate(words):
        joined += w
        owner += [n] * len(w)
    start = joined.find(target)
    if start == -1:
        return ["it is not in the sentence's letters"], []
    end = start + len(target)
    span = sorted(set(owner[start:end]))
    problems = []
    if len(span) < 2:
        problems.append("it sits inside one word; it must cross a gap between words")
    if len(span) > 3:
        problems.append(f"it is spread over {len(span)} words; at most 3")
    # It must be tucked inside words, not whole words glued together.
    whole = (start == 0 or owner[start - 1] != owner[start]) and \
            (end == len(joined) or owner[end] != owner[end - 1])
    if whole:
        problems.append("it is just whole words side by side; it must start or end inside a word")
    return problems, span


def check_hidden(sentence, answer):
    """Problems with a hidden-word clue, or [] if it works; also which words it spans."""
    words = [letters(w) for w in words_of(sentence)]
    problems, span = hidden_span(words, letters(answer))
    return [f"{answer}: {p}" for p in problems] + basic_problems(words, answer), span


def check_backwards(sentence, answer):
    """Like hidden, but the answer is spelled right to left."""
    words = [letters(w) for w in words_of(sentence)]
    problems, span = hidden_span(words, letters(answer)[::-1])
    return [f"{answer} backwards: {p}" for p in problems] + basic_problems(words, answer), span


def check_first(sentence, answer):
    """The first letters of consecutive words spell the answer."""
    words = [letters(w) for w in words_of(sentence)]
    n, target = len(answer), letters(answer)
    runs = [i for i in range(len(words) - n + 1) if "".join(w[:1] for w in words[i:i + n]) == target]
    problems = [] if runs else [f"no run of {n} words whose first letters spell {answer}"]
    return problems + basic_problems(words, answer), (list(range(runs[0], runs[0] + n)) if runs else [])


def halves_splits(answer):
    """Ways to cut the answer into two everyday words (WILDLIFE -> WILD + LIFE)."""
    a = answer.lower()
    return [(a[:i].upper(), a[i:].upper()) for i in range(3, len(a) - 2)
            if zipf_frequency(a[:i], "en") >= 3.5 and zipf_frequency(a[i:], "en") >= 3.5]


# ---------- Hints ----------

def mark_hidden(phrase, word):
    """The phrase as safe HTML with the hidden word's letters in bold, e.g. publi<b>c at</b>tention."""
    target = letters(word)
    spots = [i for i, ch in enumerate(phrase) if ch.isalpha()]      # char index of each letter
    at = "".join(phrase[i] for i in spots).lower().find(target)
    start, end = spots[at], spots[at + len(target) - 1] + 1
    return (html.escape(phrase[:start]) + "<b>" + html.escape(phrase[start:end]) + "</b>"
            + html.escape(phrase[end:]))


def mark_initials(phrase):
    """Bold the first letter of each word: <b>H</b>appy <b>O</b>tters."""
    return " ".join(f"<b>{html.escape(w[0])}</b>{html.escape(w[1:])}" for w in phrase.split())


def first_letters_of(phrase):
    return "".join(w[0] for w in letters_words(phrase))


def letters_words(phrase):
    return [letters(w) for w in phrase.split() if letters(w)]


# Level 1 fallbacks, hand-written: used only if the fresh AI-written free hint fails its checks.
# Each example is checked in the tests at the bottom.
FREE_HINTS = {
    "hidden": [("Sneaky one! The answer is hiding in plain sight, stretched across words. "
                "Like CAT hiding in “publi<b>c at</b>tention”.", "public attention", "CAT")],
    "anagram": [("Letter scramble! Find the word whose letters rearrange into the answer, "
                 "like HEART becoming EARTH.", "HEART", "EARTH")],
    "first": [("Read the starts! The first letters of some words in a row spell the answer: "
               "<b>H</b>appy <b>O</b>tters <b>P</b>lay <b>E</b>verywhere spells HOPE.",
               "Happy Otters Play Everywhere", "HOPE")],
    "backwards": [("Read it in reverse! The answer hides backwards across words: LIVE is in "
                   "“th<b>e vil</b>lage”, read right to left.", "the village", "LIVE")],
    "halves": [("Two halves make a whole! Solve each little clue, then glue the words together, "
                "like SUN + FLOWER = SUNFLOWER.", "SUN FLOWER", "SUNFLOWER")],
}


def free_hint(kind, day_number=0):
    text, _, _ = FREE_HINTS[kind][day_number % len(FREE_HINTS[kind])]
    return text


def example_works(kind, word, source):
    """Code check for a free-hint example."""
    if kind == "hidden":
        return not check_hidden(source, word)[0]
    if kind == "backwards":
        return not check_backwards(source, word)[0]
    if kind == "anagram":
        return sorted(letters(word)) == sorted(letters(source)) and letters(word) != letters(source)
    if kind == "first":
        return first_letters_of(source) == letters(word) and len(letters_words(source)) == len(letters(word))
    if kind == "halves":
        parts = letters_words(source)
        return len(parts) == 2 and "".join(parts) == letters(word)
    return False


FREE_HINT_SCHEMA = {
    "type": "object",
    "properties": {
        "intro": {"type": "string"},
        "example_word": {"type": "string"},
        "example_from": {"type": "string"},
    },
    "required": ["intro", "example_word", "example_from"],
    "additionalProperties": False,
}
FREE_HINT_ASK = {
    "hidden": ("example_word: a short common word (3-5 letters). example_from: a short everyday "
               "phrase where that word hides across two words, ignoring spaces "
               "(like CAT in 'public attention')."),
    "anagram": ("example_word: a common word (4-6 letters). example_from: a DIFFERENT real word "
                "made of exactly the same letters (like SILENT for LISTEN)."),
    "first": ("example_word: a short common word (3-5 letters). example_from: a short fun phrase "
              "with exactly one word per letter, whose first letters spell it (like 'Happy Otters "
              "Play Everywhere' for HOPE)."),
    "backwards": ("example_word: a short common word (3-5 letters). example_from: a short everyday "
                  "phrase where that word appears BACKWARDS across two words (like LIVE in 'the "
                  "village', which contains e-v-i-l)."),
    "halves": ("example_word: a common compound word made of two everyday words (like SUNFLOWER). "
               "example_from: the two words separated by a space (like 'SUN FLOWER')."),
}


def fresh_free_hint(kind, answer):
    """Level 1, new for every puzzle: the AI writes a playful intro and a fresh example;
    code checks the example really works and that nothing gives today's answer away."""
    for _ in range(3):
        response = client.chat.completions.create(
            model=CLUE_MODEL,
            messages=[{"role": "user", "content": (
                "Write the free first hint for a friendly word puzzle. It teaches the trick in "
                "general, with an example that is NOT today's answer.\n"
                f"The trick: {INSTRUCTIONS[kind]}\n"
                "intro: one playful sentence (max 16 words) explaining the trick, no example in it.\n"
                + FREE_HINT_ASK[kind] + f"\nNever use the word {answer} or anything containing it. "
                "Pick a fresh, surprising example; avoid the overused CAT, OWL, EAR, LISTEN, SILENT, "
                "HEART, EARTH, HOPE, SUNFLOWER."
            )}],
            response_format={"type": "json_schema", "json_schema": {
                "name": "free_hint", "strict": True, "schema": FREE_HINT_SCHEMA}},
        )
        h = json.loads(response.choices[0].message.content)
        word, source, intro = h["example_word"].upper(), h["example_from"], h["intro"].strip()
        leaks = letters(answer) in letters(intro + word + source)
        if example_works(kind, word, source) and not leaks and len(intro.split()) <= 20:
            intro = html.escape(intro)
            if kind == "hidden":
                return f"{intro} Like {word} hiding in “{mark_hidden(source, word)}”."
            if kind == "backwards":
                return (f"{intro} Like {word} hiding backwards in "
                        f"“{mark_hidden(source, letters(word)[::-1])}”.")
            if kind == "first":
                return f"{intro} Like {mark_initials(source)}, which spells {word}."
            if kind == "halves":
                a, b = source.upper().split()
                return f"{intro} Like {html.escape(a)} + {html.escape(b)} = {word}."
            return f"{intro} {html.escape(source.upper())} is just {word}, mixed up."
    return None                                   # caller falls back to the hand-written hints


def build_hints(kind, sentence, answer, highlight, day_number=0, halves=None):
    """Hint levels and a give-up walkthrough, worked out in code from the verified clue.
    Level 2 (the definition) is filled in later by theme_hint()."""
    spot = [words_of(sentence)[i] for i in highlight]
    quoted = " and ".join(f"“{w}”" for w in spot)
    joined = "".join(letters(w) for w in spot)
    if kind == "hidden":
        at = joined.find(letters(answer))
        how = f"{joined[:at]} · {answer} · {joined[at + len(answer):]}".strip(" ·")
        where = f"Peek between {quoted}…"
        steps = ["The trick: the answer was hiding across the words.",
                 f"Where: in “{' '.join(spot)}”.", f"How: {how} → {answer}"]
    elif kind == "backwards":
        rev = letters(answer)[::-1]
        at = joined.find(rev)
        how = f"{joined[:at]} · {rev.upper()} · {joined[at + len(rev):]}".strip(" ·")
        where = f"Peek between {quoted}, then read right to left…"
        steps = ["The trick: the answer was hiding backwards across the words.",
                 f"Where: in “{' '.join(spot)}”.", f"How: {how} → read backwards → {answer}"]
    elif kind == "first":
        where = f"Start at “{spot[0]}” and read the first letters of the next {len(answer)} words…"
        steps = ["The trick: the first letters of a run of words spelled the answer.",
                 f"Where: “{' '.join(spot)}”.",
                 f"How: {' · '.join(w[0].upper() for w in spot)} → {answer}"]
    elif kind == "halves":
        a, b = halves
        where = f"The first half has {len(a)} letters and starts with {a[0]}."
        steps = ["The trick: two little clues, one for each half of the word.",
                 f"Halves: {a} + {b}.", f"How: {a} + {b} → {answer}"]
    else:
        where = f"Try unscrambling {quoted}…"
        steps = ["The trick: some letters in the sentence were the answer, mixed up.",
                 f"Where: in “{' '.join(spot)}”.",
                 f"How: {' '.join(spot).upper()} → rearranged → {answer}"]
    hints = [
        {"level": 1, "free": True, "text": free_hint(kind, day_number)},   # replaced by fresh_free_hint()
        {"level": 2, "free": False, "text": ""},          # definition, added by theme_hint()
        {"level": 3, "free": False, "text": where, "highlight": highlight},
    ]
    return hints, {"answer": answer, "steps": steps}


# ---------- AI helpers with checks ----------

def solver_guesses(hint, length):
    """A second model sees only the hint and the letter count, like a player would."""
    response = client.chat.completions.create(
        model=SOLVER_MODEL,
        messages=[{"role": "user", "content": (
            f"A word puzzle hint: \"{hint}\". The answer is one English word of {length} letters. "
            "Give your 5 best guesses."
        )}],
        response_format={"type": "json_schema", "json_schema": {"name": "guesses", "strict": True, "schema": {
            "type": "object", "properties": {"guesses": {"type": "array", "items": {"type": "string"}}},
            "required": ["guesses"], "additionalProperties": False}}},
    )
    return [g.strip().upper() for g in json.loads(response.choices[0].message.content)["guesses"]]


def natural_scores(sentences):
    """A second model scores how natural each clue sentence reads. 'Shore acres cue volunteers'
    passed the letter checks but read badly; this catches that."""
    if not sentences:
        return []
    listing = "\n".join(f"{i}. {s}" for i, s in enumerate(sentences))
    response = client.chat.completions.create(
        model=SOLVER_MODEL,
        messages=[{"role": "user", "content": (
            "Score each sentence 0-10 for how natural and grammatical it reads, as something a "
            "person might really write. Awkward word choices forced in to fit a pattern score low.\n"
            + listing
        )}],
        response_format={"type": "json_schema", "json_schema": {"name": "natural", "strict": True, "schema": {
            "type": "object",
            "properties": {"scores": {"type": "array", "items": {
                "type": "object", "properties": {"id": {"type": "integer"}, "score": {"type": "integer"}},
                "required": ["id", "score"], "additionalProperties": False}}},
            "required": ["scores"], "additionalProperties": False}}},
    )
    got = {s["id"]: s["score"] for s in json.loads(response.choices[0].message.content)["scores"]}
    return [got.get(i, 0) for i in range(len(sentences))]


def theme_hint(answer, topic, sentence):
    """Level 2: a playful definition of the word. Two checks: it never contains the answer,
    and a separate solver model can get the answer from it (so it isn't too vague)."""
    tried = []
    for _ in range(3):
        response = client.chat.completions.create(
            model=CLUE_MODEL,
            messages=[{"role": "user", "content": (
                f"Write a hint for the word {answer} ({len(answer)} letters). Describe what the WORD "
                "itself means, clearly, like a friendly crossword definition, with a playful touch "
                f"(e.g. for HEALTH: 'What doctors check on, and what you raise a glass to.'). At most "
                "14 words; you may start with one emoji. Never say the word or any word containing it. "
                "Describe the word, not today's news story."
                + (f" These were too vague, do better: {tried}" if tried else "")
            )}],
        )
        text = response.choices[0].message.content.strip().strip('"')
        if letters(answer) in letters(text) or len(text.split()) > 16:
            continue
        if answer in solver_guesses(text, len(answer)):
            return text
        tried.append(text)
    return f"\U0001F305 Think about what today's good news is about: {html.escape(topic.lower())}." \
        if letters(answer) not in letters(topic) else "\U0001F305 Think about the happiest part of today's news."


# ---------- Puzzle makers ----------

def make_pixel_puzzle(answer, topic, stories):
    """Pixel reveal: guess the topic from one of its story photos, which sharpens as you play.
    Everything but hint 2 is built in code; returns None if no story has a photo."""
    story = next((s for s in stories if s.get("image")), None)
    if not story:
        return None
    answer = answer.upper()
    return {
        "type": "pixel",
        "instruction": INSTRUCTIONS["pixel"],
        "sentence": "",
        "image": story["image"],
        "length": len(answer),
        "answer": answer,
        "highlight": [],
        "hints": [
            {"level": 1, "free": True,
             "text": "It starts as a blur of big pixels. Every wrong guess or hint makes the picture sharper."},
            {"level": 2, "free": False, "text": theme_hint(answer, topic, "")},
            {"level": 3, "free": False, "text": f"It starts with {answer[0]} and ends with {answer[-1]}."},
        ],
        "solution": {"answer": answer, "steps": [
            f"The picture came from: “{story['title']}”.",
            f"Today's topic: {topic}.",
            f"The answer: {answer}.",
        ]},
    }


def make_halves(answer):
    """Two-halves clue, if the answer splits into two everyday words. The AI writes a little
    clue for each half; code checks neither clue names its half, and a solver can get the answer."""
    splits = halves_splits(answer)
    for a, b in splits[:2]:
        for _ in range(2):
            response = client.chat.completions.create(
                model=CLUE_MODEL,
                messages=[{"role": "user", "content": (
                    f"Write two short playful clues (max 7 words each) for a word puzzle: one for "
                    f"{a} and one for {b}, like crossword definitions. Never use the words {a}, {b} "
                    f"or {answer}, or anything containing them."
                )}],
                response_format={"type": "json_schema", "json_schema": {"name": "halves", "strict": True, "schema": {
                    "type": "object", "properties": {"first": {"type": "string"}, "second": {"type": "string"}},
                    "required": ["first", "second"], "additionalProperties": False}}},
            )
            c = json.loads(response.choices[0].message.content)
            clue = f"{c['first'].strip().rstrip('.')} + {c['second'].strip().rstrip('.')}"
            if any(letters(x) in letters(clue) for x in (a, b, answer)):
                continue
            if answer in solver_guesses(f"Two halves joined: {clue}", len(answer)):
                return {"type": "halves", "sentence": clue, "highlight": [], "halves": (a, b)}
    return None


CLUE_PROMPT = (
    "You write clues for a friendly daily word puzzle. The answer is {answer} ({n} letters); "
    "today's good news is about: {topic}.\n"
    "Write 4 clues of each type below. Each is ONE natural, grammatical, upbeat sentence of at "
    "most 16 words that hints at the good news. It must read like something a person would "
    "really write, not words forced together.\n"
    "anagram: the sentence contains a real word (or two words side by side) whose letters are "
    "EXACTLY the letters of {answer} rearranged ({sorted_letters}). Put that word in 'fodder'.\n"
    "hidden: {answer} is spelled out by consecutive letters running across two or three words, "
    "ignoring spaces, starting or ending inside a word (e.g. CORAL in 'arctic oral').\n"
    "backwards: {answer} spelled BACKWARDS ({reversed}) by consecutive letters across two or "
    "three words, starting or ending inside a word.\n"
    "first: {n} consecutive words whose first letters spell {answer} in order.\n"
    "Leave 'fodder' empty except for anagram. Never use {answer} itself. Check every letter."
)
CLUE_SCHEMA = {
    "type": "object",
    "properties": {
        "clues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": ["anagram", "hidden", "backwards", "first"]},
                    "sentence": {"type": "string"},
                    "fodder": {"type": "string"},
                },
                "required": ["type", "sentence", "fodder"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["clues"],
    "additionalProperties": False,
}
CHECKERS = {
    "anagram": lambda c, a: check_anagram(c["sentence"], a, c["fodder"]),
    "hidden": lambda c, a: check_hidden(c["sentence"], a),
    "backwards": lambda c, a: check_backwards(c["sentence"], a),
    "first": lambda c, a: check_first(c["sentence"], a),
}


def make_puzzle(answer, topic, rounds=2, day_number=0):
    """Ask for candidate clues, keep only those Python can verify and that read naturally,
    then build the hints in code. Returns every good puzzle, of every type that worked."""
    answer = answer.upper()
    prompt = CLUE_PROMPT.format(answer=answer, n=len(answer), topic=topic,
                                sorted_letters=" ".join(sorted(answer)), reversed=answer[::-1])
    valid, rejected = [], []
    for _ in range(rounds):
        response = client.chat.completions.create(
            model=CLUE_MODEL,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_schema", "json_schema": {
                "name": "clues", "strict": True, "schema": CLUE_SCHEMA}},
        )
        passed = []
        for clue in json.loads(response.choices[0].message.content)["clues"]:
            problems, spot = CHECKERS[clue["type"]](clue, answer)
            if problems:
                rejected.append(f"{clue['type']}: {clue['sentence']}  -> {'; '.join(problems)}")
            else:
                passed.append({**clue, "highlight": spot})
        # Letters work; now drop the ones that read badly.
        for clue, score in zip(passed, natural_scores([c["sentence"] for c in passed])):
            if score >= NATURAL_MIN:
                valid.append(clue)
            else:
                rejected.append(f"{clue['type']}: {clue['sentence']}  -> reads unnaturally ({score}/10)")
        if len({c["type"] for c in valid}) >= 3:          # enough variety; stop early
            break

    halves = make_halves(answer)
    if halves:
        valid.append(halves)

    puzzles = []
    for c in valid:
        hints, solution = build_hints(c["type"], c["sentence"], answer, c["highlight"], day_number,
                                      halves=c.get("halves"))
        puzzles.append({
            "type": c["type"],
            "instruction": INSTRUCTIONS[c["type"]],
            "sentence": c["sentence"],
            "length": len(answer),
            "answer": answer,
            "highlight": c["highlight"],     # word positions where the answer hides
            "hints": hints,                  # level 1 is free; 2 and 3 on request
            "solution": solution,            # shown on give up: how each hint led to the answer
        })
    return puzzles, rejected


if __name__ == "__main__":
    # Checkers on known examples first: no AI involved.
    print("checker tests:")
    tests = [
        (check_anagram("Carol swam back to the reef today.", "CORAL", "Carol")[0], []),
        (check_anagram("Carlo swam back to the reef today.", "CORAL", "Carol")[0] != [], True),   # not in sentence
        (check_anagram("Coral swam back today.", "CORAL", "Coral")[0] != [], True),               # answer itself
        (check_hidden("The arctic oral histories were saved.", "CORAL")[0], []),
        (check_hidden("Divers found coral reefs.", "CORAL")[0] != [], True),                      # plain word
        (check_hidden("Nothing to see here.", "CORAL")[0] != [], True),                           # missing
        (check_hidden("Volunteers raised S A N C T U A R Y flags.", "SANCTUARY")[0] != [], True), # spelled out
        (check_hidden("Bright sun shines on farms.", "SUNSHINES")[0] != [], True),                # whole words
        (check_hidden("Clean power, so large families save.", "SOLAR")[0], []),                   # ends inside 'large'
        (check_anagram("We saw S O L A R panels.", "SOLAR", "S O L A R")[0] != [], True),        # spelled out
        (check_backwards("Everyone in the village cheered.", "LIVE")[0], []),                     # e-v-i-l backwards
        (check_backwards("Everyone cheered the evil end.", "LIVE")[0] != [], True),               # 'evil' is a whole word
        (check_first("Happy otters play everywhere now.", "HOPE")[0], []),
        (check_first("Happy people everywhere.", "HOPE")[0] != [], True),
        (halves_splits("WILDLIFE"), [("WILD", "LIFE")]),
        (halves_splits("SOLAR"), []),
    ]
    for got, expected in tests:
        print("  ok" if got == expected else f"  FAIL got {got}")

    print("fallback free-hint examples really work:")
    for kind, items in FREE_HINTS.items():
        for _, source, word in items:
            print(f"  {'ok' if example_works(kind, word, source) else 'FAIL'} {kind}: {word}")
