from pathlib import Path

CHATBOT_DIR   = Path(__file__).parent.parent
RAW_DIR       = CHATBOT_DIR / "raw"
CHROMA_DIR    = CHATBOT_DIR / "chroma"
STATE_FILE    = CHATBOT_DIR / "state.json"

RAW_DIR.mkdir(exist_ok=True)

WIKI_API      = "https://wiki.warframe.com/api.php"
WIKI_BASE     = "https://wiki.warframe.com/w"
RATE_LIMIT_S  = 1.0
BATCH_SIZE    = 50
MIN_PAGE_SIZE = 500

CHUNK_TOKENS  = 500
CHUNK_OVERLAP = 50

EMBED_MODEL   = "all-MiniLM-L6-v2"
EMBED_DIM     = 384

COLLECTION    = "warframe_wiki"

CLAUDE_MODEL  = "claude-sonnet-4-6"
RETRIEVAL_K   = 6
