from warframe_chatbot.cleaner import clean_wikitext


def test_removes_templates():
    assert "{{" not in clean_wikitext("Text {{stub}} more.")

def test_keeps_inline_template_display():
    assert "Cold" in clean_wikitext("Deals {{D|Cold}} damage.")

def test_wikilink_display_text_kept():
    result = clean_wikitext("See [[Frost|the ice frame]] and [[Rhino]].")
    assert "the ice frame" in result and "Rhino" in result and "[[" not in result

def test_html_tags_stripped():
    result = clean_wikitext("Lasts <span style='color:red'>10 seconds</span>.")
    assert "10 seconds" in result and "<" not in result

def test_headers_stripped_text_kept():
    result = clean_wikitext("== Overview ==\nFrost is cold.\n=== Abilities ===")
    assert "==" not in result and "Overview" in result

def test_bullet_content_kept():
    result = clean_wikitext("* First\n** Nested\n# Numbered")
    assert "First" in result and "Nested" in result and "Numbered" in result

def test_empty_returns_empty():
    assert clean_wikitext("") == ""

def test_collapses_blank_lines():
    assert "\n\n\n" not in clean_wikitext("A\n\n\n\nB")
