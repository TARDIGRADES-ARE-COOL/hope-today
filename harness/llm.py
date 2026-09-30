from dotenv import load_dotenv
load_dotenv()

from openai import OpenAI

MODEL = "gpt-4o-mini"
SYSTEM_PROMPT = (
    "You are Hope Today, a warm, upbeat guide who helps people find "
    "real, substantive good news about the things they care about."
)

client = OpenAI()


def chat(messages, tools=None):
    kwargs = {
        "model": MODEL,
        "max_tokens": 1024,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + messages,
    }
    # Only send tools when we have some; OpenAI rejects tools=None.
    if tools:
        kwargs["tools"] = tools

    response = client.chat.completions.create(**kwargs)
    return response.choices[0].message


if __name__ == "__main__":
    messages = [{"role": "user", "content": "surprise me"}]
    reply = chat(messages)
    # print(reply)
    print()
    print(reply.content)
