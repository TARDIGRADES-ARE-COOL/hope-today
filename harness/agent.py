import json
from llm import chat
from tools import TOOL_SCHEMAS, TOOLS

messages = [{"role": "user", "content": "any good ocean news?"}]

while True:
    print(len(messages))                     # history grows each pass
    reply = chat(messages, TOOL_SCHEMAS)

    if not reply.tool_calls:                 # no tools requested → final answer
        print(reply.content)
        break

    messages.append(reply)                   # the model's "please run these tools"

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
