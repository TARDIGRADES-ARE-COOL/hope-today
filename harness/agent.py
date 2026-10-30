import json
from llm import chat
from tools import TOOL_SCHEMAS, TOOLS

MAX_TURNS = 10                               # budget: never loop forever

messages = [{"role": "user", "content": "any good ocean news?"}]
nudged = False                               # only nudge once

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

        messages.append({
            "role": "tool",
            "tool_call_id": call.id,         # which request this answers
            "content": json.dumps(result),   # the result, as text
        })

        # Stopping rule: the run succeeds once a deck is actually built.
        if call.function.name == "render_deck" and "error" not in result:
            print("Deck saved:", result["path"])
            done = True

    if done:
        break
else:
    print(f"Stopped after {MAX_TURNS} turns without a deck.")
