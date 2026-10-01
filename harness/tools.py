import os
from datetime import date, timedelta

import requests
from dotenv import load_dotenv

load_dotenv()
GUARDIAN_KEY = os.environ["GUARDIAN_API_KEY"]


def find_topics(query):
    params = {
        "q": query,
        "type": "keyword",
        "api-key": GUARDIAN_KEY,
    }

    response = requests.get("https://content.guardianapis.com/tags", params=params)
    results = response.json()["response"]["results"]

    # Keep only what the model needs to pick a tag; every extra field costs tokens.
    topics = []
    for item in results:
        topics.append({"id": item["id"], "title": item["webTitle"]})
    return topics


def search_news(tag, since=None):
    """Recent Guardian articles for a tag id from find_topics."""
    if since is None:
        since = (date.today() - timedelta(days=7)).isoformat()   # default: last week

    params = {
        "tag": tag,
        "type": "article",
        "order-by": "newest",
        "from-date": since,
        "show-fields": "trailText",
        "api-key": GUARDIAN_KEY,
    }

    response = requests.get("https://content.guardianapis.com/search", params=params)
    results = response.json()["response"]["results"]

    # Same idea as find_topics: only what the model needs to judge and present a story.
    stories = []
    for item in results:
        stories.append({
            "title": item["webTitle"],
            "url": item["webUrl"],
            "snippet": item["fields"]["trailText"],
            "date": item["webPublicationDate"][:10],
        })
    return stories


# The model never sees the Python function above. It only sees this
# description, and uses it to decide when to call the tool and with what.
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "find_topics",
            "description": (
                "Find Guardian topic tags for a subject. Returns tag ids and titles. "
                "Call this first, then pick the tag that best matches what the user means."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "A short subject, e.g. 'ocean' or 'climate'.",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_news",
            "description": "Get recent news articles for a Guardian tag.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tag": {
                        "type": "string",
                        "description": "A tag id from find_topics, e.g. 'environment/oceans'.",
                    },
                    "since": {
                        "type": "string",
                        "description": "Optional ISO date (YYYY-MM-DD); only return stories after it.",
                    },
                },
                "required": ["tag"],
            },
        },
    },
]

# Maps the name the model asks for to the Python function that runs it.
TOOLS = {"find_topics": find_topics, "search_news": search_news}


if __name__ == "__main__":
    print(find_topics("ocean"))
