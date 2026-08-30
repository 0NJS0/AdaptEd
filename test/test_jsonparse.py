"""Tests for robust JSON recovery from messy LLM output (offline, no deps)."""

from __future__ import annotations

from adapted.llm.jsonparse import extract_json


def test_plain_json():
    assert extract_json('{"a": 1}') == {"a": 1}


def test_markdown_fenced():
    assert extract_json('```json\n{"chapters": []}\n```') == {"chapters": []}
    assert extract_json("```\n{\"x\": true}\n```") == {"x": True}


def test_prose_wrapped():
    txt = 'Sure! Here is the JSON:\n{"questions": [1, 2]}\nHope that helps.'
    assert extract_json(txt) == {"questions": [1, 2]}


def test_json_array():
    assert extract_json("Here: [1, 2, 3]") == [1, 2, 3]


def test_empty_or_whitespace_returns_none():
    # this is the exact case behind "Expecting value: line 1 column 1 (char 0)"
    assert extract_json("") is None
    assert extract_json("   \n  ") is None
    assert extract_json(None) is None


def test_garbage_returns_none():
    assert extract_json("I cannot answer that.") is None


def test_nested_object_recovered():
    txt = 'prefix {"a": {"b": [1, {"c": 2}]}} suffix'
    assert extract_json(txt) == {"a": {"b": [1, {"c": 2}]}}
