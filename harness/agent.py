import json
import sys
from llm import chat
from tools import TOOL_SCHEMAS, TOOLS

MAX_TURNS = 15                               # budget: never loop forever (fetches need turns)
MAX_DECK_TRIES = 3                           # stop if render_deck keeps failing

# python harness/agent.py "good news about science"
question = sys.argv[1] if len(sys.argv) > 1 else "any good ocean news?"
messages = [{"role": "user", "content": question}]
nudged = False                               # only nudge once
deck_tries = 0

for turn in range(MAX_TURNS):
    print(len(messages))                     # history grows each pass
    reply = chat(messages, TOOL_SCHEMAS)

    if not reply.tool_calls:                 # model answered in text instead of building the deck
        if nudged:
            print("No deck. The model's reply:")
            print(reply.content)
            break
        messages.append(reply)
        messages.append({"role": "user", "content": (
            "If you found any genuinely good stories, call render_deck with them now. "
            "If not, reply with a short kind message."
        )})
        nudged = True
        continue

    messages.append(reply)                   # the model's "please run these tools"
    done = False

    for call in reply.tool_calls:
        print(call.function.name, call.function.arguments)

        args = json.loads(call.function.arguments)   # text → dict
        func = TOOLS[call.function.name]             # name → real function
        result = func(**args)                        # run it
        if isinstance(result, dict) and "error" in result:
            print("  error:", result["error"])       # tracing: see why a call was rejected

        messages.append({
            "role": "tool",
            "tool_call_id": call.id,         # which request this answers
            "content": json.dumps(result),   # the result, as text
        })

        # Stopping rule: the run succeeds once a deck is actually built.
        if call.function.name == "render_deck":
            deck_tries += 1
            if "error" not in result:
                print("Deck saved:", result["path"])
                done = True

    if done:
        break
    if deck_tries >= MAX_DECK_TRIES:
        print(f"render_deck failed {deck_tries} times, giving up.")
        break
else:
    print(f"Stopped after {MAX_TURNS} turns without a deck.")
