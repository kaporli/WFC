from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

CHATBOT_DIR   = Path(__file__).parent.parent
RAW_DIR       = CHATBOT_DIR / "raw"
CHROMA_DIR    = CHATBOT_DIR / "chroma"
STATE_FILE    = CHATBOT_DIR / "state.json"

RAW_DIR.mkdir(exist_ok=True)

WIKI_API      = "https://wiki.warframe.com/api.php"
WIKI_BASE     = "https://wiki.warframe.com/w"
RATE_LIMIT_S  = 1.0
BATCH_SIZE    = 20           # TextExtracts exintro allows max 20 per request
MIN_PAGE_SIZE = 500

CHUNK_TOKENS  = 500
CHUNK_OVERLAP = 50

EMBED_MODEL   = "all-MiniLM-L6-v2"
EMBED_DIM     = 384

COLLECTION    = "warframe_wiki"

# Chat model — override with WF_MODEL environment variable.
# Examples:
#   claude-sonnet-4-6                           (Anthropic — needs ANTHROPIC_API_KEY)
#   gpt-4o                                      (OpenAI — needs OPENAI_API_KEY)
#   gemini/gemini-2.0-flash                     (Google — needs GEMINI_API_KEY)
#   ollama/qwen2.5:7b                           (local via Ollama, no API key)
#   ollama/llama3.2                             (local via Ollama, no API key)
#   huggingface/Qwen/Qwen2.5-7B-Instruct       (HuggingFace Inference API — needs HF_TOKEN)
import os
CHAT_MODEL    = os.environ.get("WF_MODEL", "ollama/qwen3.5:9b")
RETRIEVAL_K   = 15
