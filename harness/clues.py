"""Part 2: wordplay clues for the daily answer. The AI writes them; Python checks every one."""
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
        span = sorted(set(owner[start:start + len(letters(answer))]))
        if len(span) < 2:
            problems.append(f"{answer} sits inside one word; it must cross a gap between words")
    if letters(answer) in words:
        problems.append("the answer appears in the sentence as a word")
    if len(words) > MAX_WORDS:
        problems.append(f"sentence is over {MAX_WORDS} words")
    return problems, span


def build_hints(kind, sentence, answer, highlight):
    """Three hint levels and a give-up walkthrough, all worked out in code from the
    verified clue, so every hint is correct and really leads to the answer."""
    spot = [words_of(sentence)[i] for i in highlight]
    joined = "".join(letters(w) for w in spot)
    first, n = answer[0], len(answer)
    if kind == "hidden":
        at = joined.find(letters(answer))
        before, after = joined[:at], joined[at + n:]
        hints = [
            {"level": 1, "free": True,
             "text": "The answer hides across the gaps between words. Ignore the spaces."},
            {"level": 2, "free": False, "text": f"Look closely at: {' '.join(spot)}"},
            {"level": 3, "free": False,
             "text": f"Join them with no space: {joined.upper()}. Find the {n} letters starting with {first}."},
        ]
        how = f"{before} · {answer} · {after}".strip(" ·")
        steps = [
            "The trick: the answer was hiding across the words.",
            f"Where: in \"{' '.join(spot)}\".",
            f"How: {how} → {answer}",
        ]
    else:
        hints = [
            {"level": 1, "free": True,
             "text": "One word, or two side by side, is the answer with its letters mixed up."},
            {"level": 2, "free": False, "text": f"The letters to mix up are in: {' '.join(spot)}"},
            {"level": 3, "free": False,
             "text": f"In alphabetical order they are: {' '.join(sorted(answer))}. It starts with {first}."},
        ]
        steps = [
            "The trick: some letters in the sentence were the answer, mixed up.",
            f"Where: in \"{' '.join(spot)}\".",
            f"How: {' '.join(spot).upper()} → rearranged → {answer}",
        ]
    return hints, {"answer": answer, "steps": steps}


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


def make_puzzle(answer, topic, rounds=2):
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
        hints, solution = build_hints(c["type"], c["sentence"], answer, c["highlight"])
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
    ]
    for got, expected in tests:
        print("  ok" if got == expected else f"  FAIL got {got}")

    examples = [
        ("hidden", "Communities rewild landscapes, giving otters room to thrive.", "WILDLAND",
         check_hidden("Communities rewild landscapes, giving otters room to thrive.", "WILDLAND")[1]),
        ("anagram", "Rangers file wild meadow sightings.", "WILDLIFE",
         check_anagram("Rangers file wild meadow sightings.", "WILDLIFE", "file wild")[1]),
    ]
    for kind, sentence, answer, spot in examples:
        hints, solution = build_hints(kind, sentence, answer, spot)
        print(f"\n[{kind}] \"{sentence}\" ({len(answer)})")
        for h in hints:
            print(f"  Level {h['level']}{' (free)' if h['free'] else ''}: {h['text']}")
        print("  Give up:")
        for step in solution["steps"]:
            print(f"    {step}")
