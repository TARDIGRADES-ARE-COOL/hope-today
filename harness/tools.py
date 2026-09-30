def search_news(query, since=None):
    """
    Search for news articles related to the given query.

    Fake for now: returns hardcoded stories so we can learn tool calling
    without a real news API. Phase 2 replaces this with the Guardian.

    Args:
        query (str): The search query.
        since (str, optional): Only return stories after this date (ignored for now).

    Returns:
        list: A list of news articles related to the query.
    """
    return [
        {
            "title": f"Big breakthrough in {query} surprises scientists",
            "url": "https://example.com/breakthrough",
            "snippet": f"Researchers say the new {query} discovery could help millions.",
        },
        {
            "title": "Scientists teach octopus to play chess",
            "url": "https://example.com/octopus-chess",
            "snippet": "The octopus, named Gerald, won 3 of 5 games against a grad student.",
        },
        {
            "title": "Village plants one million trees in a single weekend",
            "url": "https://example.com/million-trees",
            "snippet": "Volunteers aged 6 to 92 took part in the record-breaking effort.",
        },
    ]


# The model never sees the Python function above. It only sees this
# description, and uses it to decide when to call the tool and with what.
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "search_news",
            "description": "Search today's news for stories about a topic.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The topic to search for, e.g. 'space exploration'.",
                    },
                    "since": {
                        "type": "string",
                        "description": "Optional ISO date (YYYY-MM-DD); only return stories after it.",
                    },
                },
                "required": ["query"],
            },
        },
    },
]

# Maps the name the model asks for to the Python function that runs it.
TOOLS = {"search_news": search_news}


if __name__ == "__main__":
    from llm import chat

    print(search_news("space"))
    print()

    reply = chat([{"role": "user", "content": "any good space news?"}], TOOL_SCHEMAS)
    print(reply.tool_calls)
