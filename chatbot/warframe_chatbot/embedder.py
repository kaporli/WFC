from functools import lru_cache
from sentence_transformers import SentenceTransformer
from warframe_chatbot.config import EMBED_MODEL


@lru_cache(maxsize=1)
def _model() -> SentenceTransformer:
    return SentenceTransformer(EMBED_MODEL)


def embed(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    return _model().encode(texts, batch_size=64, show_progress_bar=False,
                           normalize_embeddings=True).tolist()
