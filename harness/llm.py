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
    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=1024,
        messages=[{"role": "system", "content": SYSTEM_PROMPT}] + messages,
    )
    return response.choices[0].message




if __name__ == "__main__":
    messages = [{"role": "user", "content": "surprise me"}]
    reply = chat(messages)
    # print(reply)
    print()
    print(reply.content)
