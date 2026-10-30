import os
from datetime import date, timedelta

import requests
from dotenv import load_dotenv

from deck import render_deck

load_dotenv()
GUARDIAN_KEY = os.environ["GUARDIAN_API_KEY"]

# Every url search_news has returned this run. render_deck only accepts these,
# so the model cannot invent stories.
SEEN_URLS = set()


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

    # Hard cap: never older than 30 days, whatever the model asks for.
    # ISO dates compare correctly as strings.
    oldest = (date.today() - timedelta(days=30)).isoformat()
    since = max(since, oldest)

    params = {
        "tag": tag,
        "type": "article",
        "order-by": "newest",
        "from-date": since,
        "show-fields": "trailText",
        "page-size": 20,                                          # default is 10
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
        SEEN_URLS.add(item["webUrl"])
    return stories


def checked_render_deck(title, user_answer, stories):
    """render_deck, but first reject any story the model did not get from search_news."""
    for n, story in enumerate(stories, start=1):
        if story.get("url") not in SEEN_URLS:
            return {"error": (
                f"Story {n}'s url was not in your search results. Only use real articles "
                "from search_news; if you have too few, search more tags."
            )}
    return render_deck(title, user_answer, stories)


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
                        "description": (
                            "Optional ISO date (YYYY-MM-DD); only return stories after it. "
                            "Default is 7 days ago; anything older than 30 days is capped."
                        ),
                    },
                },
                "required": ["tag"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "render_deck",
            "description": (
                "Build the final slide deck. Call this last, once, with the best 1-7 "
                "genuinely hopeful stories. Returns an error message if a story is incomplete."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Short deck title, e.g. 'Good news from the ocean'.",
                    },
                    "user_answer": {
                        "type": "string",
                        "description": "What the user said, word for word.",
                    },
                    "stories": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "headline": {
                                    "type": "string",
                                    "description": "Your own headline, 32 characters or fewer.",
                                },
                                "summary": {
                                    "type": "string",
                                    "description": "One sentence: what happened.",
                                },
                                "key_points": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "2-4 short concrete facts from the source. Never invent facts.",
                                },
                                "why_it_matters": {
                                    "type": "string",
                                    "description": "One sentence tying the story to what the user said.",
                                },
                                "url": {"type": "string", "description": "The article url from search_news."},
                                "date": {"type": "string", "description": "The article date from search_news."},
                            },
                            "required": ["headline", "summary", "key_points", "why_it_matters", "url"],
                        },
                    },
                },
                "required": ["title", "user_answer", "stories"],
            },
        },
    },
]

# Maps the name the model asks for to the Python function that runs it.
# The model asks for "render_deck"; the harness runs the checked version.
TOOLS = {"find_topics": find_topics, "search_news": search_news, "render_deck": checked_render_deck}


if __name__ == "__main__":
    print(find_topics("ocean"))
