from ddgs import DDGS


def web_search(query: str, max_results: int = 5, **_) -> str:
    """Search the web using DuckDuckGo and return a formatted string of results."""
    return _ddg_search(query, max_results)


def _ddg_search(query: str, max_results: int) -> str:
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
    except Exception as e:
        return f"Search failed: {e}"

    if not results:
        return f"No results found for query: {query}"

    formatted = []
    for i, r in enumerate(results, 1):
        title = r.get("title", "No title")
        url = r.get("href", "")
        body = r.get("body", "").strip()[:400]
        formatted.append(f"[{i}] {title}\n{url}\n{body}")

    return "\n\n".join(formatted)
