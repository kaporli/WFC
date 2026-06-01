from __future__ import annotations
import logging
import litellm

for _log in ("LiteLLM", "litellm", "litellm.utils", "litellm.main"):
    logging.getLogger(_log).setLevel(logging.ERROR)

from warframe_chatbot.config import CHAT_MODEL, RETRIEVAL_K
from warframe_chatbot.store import WikiStore, SearchResult
from warframe_chatbot.search import search

# Suppress litellm's verbose success/debug logging
litellm.suppress_debug_info = True

SYSTEM_PROMPT = """You are a Warframe game expert and wiki assistant.

Rules:
1. Answer using ONLY information from the provided wiki excerpts.
2. ONLY include a source if it DIRECTLY answers the question. Do not include tangentially related items.
3. If an excerpt is about a different topic (e.g. the question is about companion buffing but the excerpt is about a warframe arcane that has nothing to do with companions), IGNORE that excerpt entirely.
4. If the excerpts lack enough direct information, say so clearly — do not pad with loosely related content.
5. Cite sources as [Page Title](URL) inline.
6. Do not invent explanations for why unrelated items might apply."""


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
        # For Ollama models, disable thinking mode (Qwen3 etc.) so content
        # is returned directly instead of being absorbed by <think> tokens.
        extra = {"think": False} if model.startswith("ollama/") else {}
        response = litellm.completion(
            model=model,
            max_tokens=2048,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": prompt},
            ],
            **extra,
        )
        msg = response.choices[0].message
        # Qwen3 / thinking models may put the answer in content or reasoning_content
        content = (
            msg.content
            or getattr(msg, "reasoning_content", None)
            or next(
                (getattr(msg, f, None) for f in ("text", "tool_calls") if getattr(msg, f, None)),
                None,
            )
        )
        return content or "(no response — model returned empty content)"
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
