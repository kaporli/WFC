from unittest.mock import MagicMock, patch
from warframe_chatbot.chat import build_prompt, format_sources


def test_build_prompt_includes_question():
    from warframe_chatbot.store import SearchResult
    results = [SearchResult(page_title="Shieldgate", section="Mechanics",
                            text="Shields gate grants invulnerability for 1.3s.",
                            url="https://wiki.warframe.com/w/Shieldgate", revid=1, score=0.9)]
    prompt = build_prompt("How does shieldgate work?", results)
    assert "shieldgate" in prompt.lower() and "1.3s" in prompt and "Shieldgate" in prompt


def test_build_prompt_includes_all_sources():
    from warframe_chatbot.store import SearchResult
    results = [
        SearchResult(page_title="Frost", section="", text="Frost is cold.",
                     url="https://wiki.warframe.com/w/Frost", revid=1, score=0.8),
        SearchResult(page_title="Armor", section="", text="Armor reduces damage.",
                     url="https://wiki.warframe.com/w/Armor", revid=1, score=0.7),
    ]
    prompt = build_prompt("Frost armor build", results)
    assert "Frost" in prompt and "Armor" in prompt


def test_format_sources():
    from warframe_chatbot.store import SearchResult
    results = [SearchResult(page_title="Shieldgate", section="Mechanics",
                            text="text", url="https://wiki.warframe.com/w/Shieldgate",
                            revid=1, score=0.9)]
    formatted = format_sources(results)
    assert "Shieldgate" in formatted and "wiki.warframe.com" in formatted


def test_ask_calls_claude(tmp_path):
    from warframe_chatbot.chunker import Chunk
    from warframe_chatbot.store import WikiStore
    store = WikiStore(persist_dir=str(tmp_path / "chroma"))
    store.upsert([Chunk(page_title="Shieldgate", section="Mechanics",
                        text="Shieldgate grants 1.3s invulnerability on shield depletion.",
                        url="https://wiki.warframe.com/w/Shieldgate", revid=1, chunk_index=0)])

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="Shieldgate works by granting invulnerability.")]

    with patch("warframe_chatbot.chat.anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.return_value = mock_response
        from warframe_chatbot.chat import ask
        result = ask("How does shieldgate work?", store=store)

    assert isinstance(result, str) and len(result) > 0
