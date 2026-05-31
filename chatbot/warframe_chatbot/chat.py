from __future__ import annotations
import os
import anthropic

from warframe_chatbot.config import CLAUDE_MODEL, RETRIEVAL_K
from warframe_chatbot.store import WikiStore, SearchResult
from warframe_chatbot.search import search

SYSTEM_PROMPT = """You are a Warframe game expert and wiki assistant.
Answer questions using ONLY the provided wiki excerpts below.
Always cite your sources using the format [Page Title](URL) at the end of each claim.
If the provided excerpts do not contain enough information to answer the question, say so clearly.
Do not fabricate information not present in the excerpts."""


def format_sources(results: list[SearchResult]) -> str:
    lines = []
    for i, r in enumerate(results, 1):
        section = f" ({r.section})" if r.section else ""
        lines.append(f"[{i}] [{r.page_title}{section}]({r.url})\n{r.text}")
    return "\n\n---\n\n".join(lines)


def build_prompt(question: str, results: list[SearchResult]) -> str:
    sources = format_sources(results)
    return f"""Wiki excerpts (use these to answer the question):

{sources}

---

Question: {question}"""


def ask(
    question: str,
    *,
    store: WikiStore | None = None,
    k: int = RETRIEVAL_K,
) -> str:
    results = search(question, store=store, k=k)
    if not results:
        return "The wiki index is empty. Run `wf-ingest` first to index the Warframe wiki."
    prompt = build_prompt(question, results)
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


def main() -> None:
    import sys
    print("Warframe Wiki Chatbot (type 'quit' to exit)")
    store = WikiStore()
    print(f"Index: {store.count()} chunks loaded.\n")
    while True:
        try:
            question = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not question or question.lower() in ("quit", "exit"):
            break
        print(f"\nBot: {ask(question, store=store)}\n")


if __name__ == "__main__":
    main()
