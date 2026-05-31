from __future__ import annotations
import re

_INLINE_TMPL = re.compile(r'\{\{(?:D|M|WF|Weapon|Companion|Mod|Icon|Stat)\|([^|}]+)(?:\|[^}]*)?\}\}', re.IGNORECASE)
_TMPL_ALL    = re.compile(r'\{\{[^{}]*\}\}', re.DOTALL)
_FILE_LINK   = re.compile(r'\[\[(?:File|Image):[^\]]+\]\]', re.IGNORECASE)
_WIKILINK    = re.compile(r'\[\[(?:[^\]|]+\|)?([^\]]+)\]\]')
_EXT_LINK    = re.compile(r'\[https?://\S+(?:\s+([^\]]+))?\]')
_HEADER      = re.compile(r'^={1,6}\s*(.+?)\s*={1,6}\s*$', re.MULTILINE)
_HTML_TAG    = re.compile(r'<[^>]+>')
_REF         = re.compile(r'<ref[^>]*>.*?</ref>', re.DOTALL | re.IGNORECASE)
_REF_SELF    = re.compile(r'<ref[^/]*/>', re.IGNORECASE)
_TABLE_ROW   = re.compile(r'^\s*[\|!{].*$', re.MULTILINE)
_LIST_MARK   = re.compile(r'^[*#:;]+\s*', re.MULTILINE)
_FORMAT      = re.compile(r"'{2,3}")
_TOC         = re.compile(r'__(?:TOC|NOTOC|FORCETOC)__')
_HR          = re.compile(r'^-{4,}$', re.MULTILINE)


def _strip_templates(text: str) -> str:
    text = _INLINE_TMPL.sub(r'\1', text)
    for _ in range(6):
        prev = text
        text = _TMPL_ALL.sub('', text)
        if text == prev:
            break
    return text


def clean_wikitext(wikitext: str) -> str:
    if not wikitext:
        return ""
    t = wikitext
    t = _FILE_LINK.sub('', t)
    t = _REF.sub('', t)
    t = _REF_SELF.sub('', t)
    t = _strip_templates(t)
    t = _WIKILINK.sub(r'\1', t)
    t = _EXT_LINK.sub(lambda m: m.group(1) or '', t)
    t = _HEADER.sub(r'\1', t)
    t = _HTML_TAG.sub('', t)
    t = _TABLE_ROW.sub('', t)
    t = _FORMAT.sub('', t)
    t = _LIST_MARK.sub('', t)
    t = _TOC.sub('', t)
    t = _HR.sub('', t)
    t = re.sub(r'\n{3,}', '\n\n', t)
    t = re.sub(r'[ \t]+', ' ', t)
    return t.strip()
