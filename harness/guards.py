from llm import client, MODEL

# Fixed text, not model-written: in a crisis the reply must be right every time.
SUPPORT_MESSAGE = """\
It sounds like you're carrying something really heavy right now, and I'm glad you said it.
Good news can wait. You deserve to talk to a real person who can help.

  Samaritans of Singapore (SOS): call 1767, any time, 24 hours
  SOS CareText (WhatsApp):        9151 1767, 24 hours
  In immediate danger:            call 995

Outside Singapore, findahelpline.com lists free, confidential lines near you.
You don't have to go through this alone."""

SCREEN_PROMPT = (
    "You screen messages sent to a good-news app. Answer YES if the person may be in real "
    "crisis: thoughts of suicide, self-harm, not wanting to live or be here, or feeling unable "
    "to go on. Answer NO for ordinary sadness, stress, a bad week, or worry about the world. "
    "When unsure, answer YES. Reply with only YES or NO."
)


def is_in_distress(text):
    """True if the message suggests real crisis. Two checks; either one is enough."""
    # 1. OpenAI's moderation model: free, good at direct statements ("I want to end it all").
    result = client.moderations.create(model="omni-moderation-latest", input=text).results[0]
    if result.categories.self_harm or result.categories.self_harm_intent:
        return True

    # 2. A focused yes/no question: catches indirect phrasing moderation misses
    #    ("I don't want to be here anymore" scored 0.01 on moderation).
    reply = client.chat.completions.create(
        model=MODEL,
        max_tokens=3,
        temperature=0,              # same answer every time for the same message
        messages=[
            {"role": "system", "content": SCREEN_PROMPT},
            {"role": "user", "content": text},
        ],
    )
    return reply.choices[0].message.content.strip().upper().startswith("YES")


if __name__ == "__main__":
    tests = {
        "meh week": False,
        "climate feels hopeless": False,
        "this traffic is killing me": False,
        "my exams are killing me lol": False,
        "any good ocean news?": False,
        "I dont want to be here anymore": True,
        "I want to end it all": True,
        "I just want to sleep and not wake up": True,
    }
    for text, expected in tests.items():
        got = is_in_distress(text)
        print("ok  " if got == expected else "FAIL", f"{text!r:42} distress={got}")
