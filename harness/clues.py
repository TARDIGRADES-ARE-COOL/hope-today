"""Part 2: wordplay clues for the daily answer. The AI writes them; Python checks every one."""
import html
import json
import re

from llm import client

# Letter-level wordplay is hard for models, so use a stronger one. It runs once a day.
CLUE_MODEL = "gpt-5.5"
MAX_WORDS = 16              # the clue has to fit on a phone

INSTRUCTIONS = {
    "anagram": "Mix up the letters of a word in this sentence.",
    "hidden": "Today's topic is hidden inside this sentence.",
}


def words_of(sentence):
    """The sentence's words, as written (punctuation trimmed off the ends)."""
    return [w.strip(".,;:!?\"'()—–-") for w in sentence.split()]


def letters(text):
    return re.sub(r"[^a-z]", "", text.lower())


def stray_letters(words):
    """Single-letter 'words' other than a and I: a sign of cheating like 'S A N C T U A R Y'."""
    return [w for w in words if len(w) == 1 and w not in ("a", "i")]


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
    if letters(answer) in words:
        problems.append("the answer appears in the sentence as a word")
    if not 1 <= len(target) <= 2:
        problems.append("the letters to mix up must be one or two words")
    if stray_letters(words):
        problems.append("the sentence has stray single letters")
    if len(words) > MAX_WORDS:
        problems.append(f"sentence is over {MAX_WORDS} words")
    return problems, ([spots[0] + k for k in range(len(target))] if spots else [])


def check_hidden(sentence, answer):
    """Problems with a hidden-word clue, or [] if it works; also which words it spans."""
    words = [letters(w) for w in words_of(sentence)]
    joined, owner = "", []                       # owner[i] = which word letter i came from
    for n, w in enumerate(words):
        joined += w
        owner += [n] * len(w)
    problems, span = [], []
    start = joined.find(letters(answer))
    if start == -1:
        problems.append(f"{answer} is not hidden in the sentence's letters")
    else:
        end = start + len(letters(answer))
        span = sorted(set(owner[start:end]))
        if len(span) < 2:
            problems.append(f"{answer} sits inside one word; it must cross a gap between words")
        if len(span) > 3:
            problems.append(f"{answer} is spread over {len(span)} words; at most 3")
        # It must be tucked inside words, not whole words glued together.
        whole = (start == 0 or owner[start - 1] != owner[start]) and \
                (end == len(joined) or owner[end] != owner[end - 1])
        if whole:
            problems.append(f"{answer} is just whole words side by side; it must start or end inside a word")
    if stray_letters(words):
        problems.append("the sentence has stray single letters")
    if letters(answer) in words:
        problems.append("the answer appears in the sentence as a word")
    if len(words) > MAX_WORDS:
        problems.append(f"sentence is over {MAX_WORDS} words")
    return problems, span


# Level 1 hints: generic and playful, teaching the trick with a different word.
# A few of each so the free hint changes from day to day. Examples are checked below.
FREE_HINTS = {
    "hidden": [
        ("Sneaky one! The answer is hiding in plain sight, stretched across words. "
         "Like CAT hiding in \u201cpubli<b>c at</b>tention\u201d.", "public attention", "CAT"),
        ("Hide and seek! Read straight through the spaces and the answer pops out. "
         "OWL is hiding in \u201csl<b>ow l</b>ane\u201d.", "slow lane", "OWL"),
        ("Don't trust the spaces. EAR is tucked into \u201cth<b>e ar</b>t class\u201d; "
         "today's answer is hiding the same way.", "the art class", "EAR"),
    ],
    "anagram": [
        ("Shuffle time! Some letters in the sentence are the answer in disguise. "
         "LISTEN is just SILENT, mixed up.", "SILENT", "LISTEN"),
        ("Letter scramble! Find the word whose letters rearrange into the answer, "
         "like HEART becoming EARTH.", "HEART", "EARTH"),
        ("Things aren't in order today. The answer is a word in the sentence with its "
         "letters jumbled: THING turns into NIGHT.", "THING", "NIGHT"),
    ],
}


def free_hint(kind, day_number):
    """Level 1: the same playful explanation for everyone, rotating by day."""
    text, _, _ = FREE_HINTS[kind][day_number % len(FREE_HINTS[kind])]
    return text


def mark_hidden(phrase, word):
    """The phrase as safe HTML with the hidden word's letters in bold, e.g. publi<b>c at</b>tention."""
    target = letters(word)
    spots = [i for i, ch in enumerate(phrase) if ch.isalpha()]      # char index of each letter
    at = "".join(phrase[i] for i in spots).lower().find(target)
    start, end = spots[at], spots[at + len(target) - 1] + 1
    return (html.escape(phrase[:start]) + "<b>" + html.escape(phrase[start:end]) + "</b>"
            + html.escape(phrase[end:]))


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
                "HEART, EARTH."
            )}],
            response_format={"type": "json_schema", "json_schema": {
                "name": "free_hint", "strict": True, "schema": FREE_HINT_SCHEMA}},
        )
        h = json.loads(response.choices[0].message.content)
        word, source, intro = h["example_word"].upper(), h["example_from"], h["intro"].strip()
        if kind == "hidden":
            works = not check_hidden(source, word)[0]
        else:
            works = sorted(letters(word)) == sorted(letters(source)) and letters(word) != letters(source)
        leaks = letters(answer) in letters(intro + word + source)
        if works and not leaks and len(intro.split()) <= 20:
            if kind == "hidden":
                return f"{html.escape(intro)} Like {word} hiding in \u201c{mark_hidden(source, word)}\u201d."
            return f"{html.escape(intro)} {html.escape(source.upper())} is just {word}, mixed up."
    return None                                   # caller falls back to the hand-written hints


def build_hints(kind, sentence, answer, highlight, day_number=0):
    """Hint levels and a give-up walkthrough, worked out in code from the verified clue.
    Level 2 (the theme nudge) is filled in later by theme_hint()."""
    spot = [words_of(sentence)[i] for i in highlight]
    quoted = " and ".join(f"\u201c{w}\u201d" for w in spot)
    if kind == "hidden":
        joined = "".join(letters(w) for w in spot)
        at = joined.find(letters(answer))
        how = f"{joined[:at]} · {answer} · {joined[at + len(answer):]}".strip(" ·")
        where = f"Peek between {quoted}\u2026"
        steps = [
            "The trick: the answer was hiding across the words.",
            f"Where: in \u201c{' '.join(spot)}\u201d.",
            f"How: {how} \u2192 {answer}",
        ]
    else:
        where = f"Try unscrambling {quoted}\u2026"
        steps = [
            "The trick: some letters in the sentence were the answer, mixed up.",
            f"Where: in \u201c{' '.join(spot)}\u201d.",
            f"How: {' '.join(spot).upper()} \u2192 rearranged \u2192 {answer}",
        ]
    hints = [
        {"level": 1, "free": True, "text": free_hint(kind, day_number)},   # replaced by fresh_free_hint()
        {"level": 2, "free": False, "text": ""},          # theme nudge, added by theme_hint()
        {"level": 3, "free": False, "text": where, "highlight": highlight},
    ]
    return hints, {"answer": answer, "steps": steps}


SOLVER_MODEL = "gpt-5.4-mini"     # a separate model plays the role of a player


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


CLUE_PROMPT = (
    "You write clues for a friendly daily word puzzle. The answer is {answer} ({n} letters); "
    "today's good news is about: {topic}.\n"
    "Write 6 'anagram' clues and 6 'hidden' clues. Each is ONE natural, upbeat sentence of at "
    "most 16 words that hints at the good news.\n"
    "anagram: the sentence contains a real word (or two words side by side) whose letters are "
    "EXACTLY the letters of {answer} rearranged ({sorted_letters}). Put that word in 'fodder'. "
    "Do not use {answer} itself anywhere.\n"
    "hidden: {answer} is spelled out by consecutive letters running across two or more words, "
    "ignoring spaces (e.g. CORAL in 'arctic oral'). Leave 'fodder' empty.\n"
    "Check every letter carefully."
)
CLUE_SCHEMA = {
    "type": "object",
    "properties": {
        "clues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": ["anagram", "hidden"]},
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


def make_puzzle(answer, topic, rounds=2, day_number=0):
    """Ask for candidate clues, keep only those Python can verify, build the hints in code."""
    answer = answer.upper()
    prompt = CLUE_PROMPT.format(answer=answer, n=len(answer), topic=topic,
                                sorted_letters=" ".join(sorted(answer)))
    valid, rejected = [], []
    for _ in range(rounds):
        response = client.chat.completions.create(
            model=CLUE_MODEL,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_schema", "json_schema": {
                "name": "clues", "strict": True, "schema": CLUE_SCHEMA}},
        )
        for clue in json.loads(response.choices[0].message.content)["clues"]:
            if clue["type"] == "anagram":
                problems, spot = check_anagram(clue["sentence"], answer, clue["fodder"])
            else:
                problems, spot = check_hidden(clue["sentence"], answer)
            if problems:
                rejected.append(f"{clue['type']}: {clue['sentence']}  -> {'; '.join(problems)}")
            else:
                valid.append({**clue, "highlight": spot})
        if valid:
            break

    puzzles = []
    for c in valid:
        hints, solution = build_hints(c["type"], c["sentence"], answer, c["highlight"], day_number)
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
        (check_hidden("Clean power, so large families save.", "SOLAR")[0], []),                   # fine: ends inside 'large'
        (check_anagram("We saw S O L A R panels.", "SOLAR", "S O L A R")[0] != [], True),        # spelled out
    ]
    for got, expected in tests:
        print("  ok" if got == expected else f"  FAIL got {got}")

    print("free-hint examples really work:")
    for _, phrase, word in FREE_HINTS["hidden"]:
        print("  ok" if not check_hidden(phrase, word)[0] else f"  FAIL {word} in {phrase}")
    for _, mixed, word in FREE_HINTS["anagram"]:
        print("  ok" if sorted(mixed) == sorted(word) and mixed != word else f"  FAIL {mixed}/{word}")

    sentence = "Communities rewild landscapes, giving otters room to thrive."
    hints, solution = build_hints("hidden", sentence, "WILDLAND", check_hidden(sentence, "WILDLAND")[1])
    hints[1]["text"] = theme_hint("WILDLAND", "Saving wild places", sentence)
    print(f"\n\"{sentence}\" (8)")
    for h in hints:
        print(f"  Level {h['level']}{' (free)' if h['free'] else ''}: {h['text']}")
    print("  Give up: " + " / ".join(solution["steps"]))
