from warframe_chatbot.crawler import PageMeta, PageContent, parse_allpages_response, parse_content_response


def test_parse_allpages_filters_small_and_redirects():
    raw = {"query": {"pages": {
        "1": {"title": "BigPage", "revisions": [{"revid": 100, "size": 5000}]},
        "2": {"title": "Stub",    "revisions": [{"revid": 101, "size": 100}]},
        "3": {"title": "Redir",   "revisions": [{"revid": 102, "size": 30}], "redirect": True},
    }}}
    pages = parse_allpages_response(raw, min_size=500)
    assert len(pages) == 1
    assert pages[0].title == "BigPage"
    assert pages[0].revid == 100


def test_parse_content_extracts_wikitext():
    raw = {"query": {"pages": {"42": {
        "title": "Frost",
        "revisions": [{"revid": 999, "slots": {"main": {"content": "Frost is cold."}}}],
    }}}}
    result = parse_content_response(raw)
    assert result["Frost"].revid == 999
    assert "Frost is cold" in result["Frost"].wikitext


def test_page_content_url():
    pc = PageContent(title="Snow Globe", revid=1, wikitext="")
    assert "Snow_Globe" in pc.url
    assert pc.url.startswith("https://wiki.warframe.com")


def test_parse_allpages_empty():
    assert parse_allpages_response({"query": {"pages": {}}}) == []
