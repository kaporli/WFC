from __future__ import annotations
import logging
import litellm

logging.getLogger("LiteLLM").setLevel(logging.ERROR)

from warframe_chatbot.config import CHAT_MODEL, RETRIEVAL_K
from warframe_chatbot.store import WikiStore, SearchResult
from warframe_chatbot.search import search

# Suppress litellm's verbose success/debug logging
litellm.suppress_debug_info = True

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
    model: str = CHAT_MODEL,
) -> str:
    results = search(question, store=store, k=k)
    if not results:
        return "The wiki index is empty. Run `wf-ingest` first to index the Warframe wiki."

    prompt = build_prompt(question, results)
    try:
        response = litellm.completion(
            model=model,
            max_tokens=1024,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": prompt},
            ],
        )
        return response.choices[0].message.content
    except Exception as e:
        err = str(e)
        if "not found" in err.lower() and "ollama" in model.lower():
            model_tag = model.replace("ollama/", "")
            return (
                f"Model '{model_tag}' not found in Ollama.\n"
                f"Run:  ollama pull {model_tag}\n"
                f"Or use a different model:  WF_MODEL=ollama/qwen2.5:7b uv run wf-chat"
            )
        return f"Error calling {model}: {err}"


def main() -> None:
    import argparse
    p = argparse.ArgumentParser(description="Warframe Wiki Chatbot")
    p.add_argument("--model", default=CHAT_MODEL,
                   help=f"LiteLLM model string (default: {CHAT_MODEL}). "
                        "Use 'ollama/qwen2.5:7b' for local, 'gpt-4o' for OpenAI, etc.")
    args = p.parse_args()

    store = WikiStore()
    print(f"Warframe Wiki Chatbot  |  model: {args.model}  |  {store.count()} chunks indexed")
    print("Type 'quit' to exit.\n")

    while True:
        try:
            question = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not question or question.lower() in ("quit", "exit"):
            break
        print(f"\nBot: {ask(question, store=store, model=args.model)}\n")
