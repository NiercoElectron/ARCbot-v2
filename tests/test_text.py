from types import SimpleNamespace

from utils.text import render_template, render_welcome, split_message, truncate


def test_split_message_short_text_is_untouched():
    assert split_message('olá') == ['olá']
    assert split_message('') == []


def test_split_message_respects_limit_and_prefers_newlines():
    text = 'a' * 8 + '\n' + 'b' * 8
    assert split_message(text, limit=10) == ['a' * 8, 'b' * 8]


def test_split_message_falls_back_to_spaces_then_hard_cut():
    assert split_message('aaaa bbbb cccc', limit=9) == ['aaaa bbbb', 'cccc']
    assert split_message('x' * 25, limit=10) == ['x' * 10, 'x' * 10, 'x' * 5]


def test_split_message_never_exceeds_limit():
    text = ('palavra ' * 50 + '\n') * 20
    chunks = split_message(text, limit=100)
    assert all(0 < len(chunk) <= 100 for chunk in chunks)


def test_split_message_leading_newline_does_not_produce_empty_chunk():
    chunks = split_message('\n' + 'x' * 15, limit=10)
    assert all(chunks)


def test_truncate():
    assert truncate('abc', 5) == 'abc'
    assert truncate('abcdef', 5) == 'abcd…'


def test_render_template_ignores_unknown_braces():
    assert render_template('Oi {member}! {x} {0}', member='Ana') == 'Oi Ana! {x} {0}'


def test_render_welcome():
    member = SimpleNamespace(display_name='Ana', mention='<@1>', guild=SimpleNamespace(name='ARC'))
    assert render_welcome('{mention} ({member}) entrou em {server}', member) == '<@1> (Ana) entrou em ARC'
