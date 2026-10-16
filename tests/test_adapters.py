import json
from urllib.parse import parse_qs, urlencode

import pytest

from anonimo.adapters import sanitize_request, host_matches, sanitize_websocket
from anonimo.engine import Blocked

CHATGPT = "https://chatgpt.com/backend-api/conversation"
CLAUDE = "https://claude.ai/api/organizations/org/chat_conversations/chat/completion"
GEMINI = "https://gemini.google.com/_/BardChatUi/data/assistant.lamda.BardFrontendService/StreamGenerate"


def test_chatgpt_history_and_metadata(engine):
    payload = {"messages": [{"id": "id-1", "content": {"content_type": "text", "parts": ["Do ala@example.test"]}},
                            {"id": "id-2", "content": {"content_type": "text", "parts": ["Tak ala@example.test"]}}],
               "model": "test-model", "metadata": {"note": "other@example.test"}}
    result = sanitize_request(engine, CHATGPT, "POST", "application/json", json.dumps(payload))
    body = json.loads(result["body"])
    assert body["model"] == payload["model"]
    assert body["messages"][0]["id"] == "id-1"
    assert body["messages"][0]["content"]["parts"] == ["Do [EMAIL_1]"]
    assert body["messages"][1]["content"]["parts"] == ["Tak [EMAIL_1]"]
    assert body["metadata"]["note"] == "[EMAIL_2]"


def test_claude(engine):
    result = sanitize_request(engine, CLAUDE, "POST", "application/json; charset=utf-8",
                              json.dumps({"prompt": "Mail: a@example.test", "attachments": []}))
    assert json.loads(result["body"])["prompt"] == "Mail: [EMAIL_1]"


def test_gemini_preserves_envelope_and_csrf(engine):
    inner = [["Mail: a@example.test", 0, None], ["pl"], ["conversation-id"]]
    body = urlencode({"f.req": json.dumps([None, json.dumps(inner)]), "at": "csrf-fixture"})
    result = sanitize_request(engine, GEMINI, "POST", "application/x-www-form-urlencoded", body)
    form = parse_qs(result["body"])
    changed = json.loads(json.loads(form["f.req"][0])[1])
    assert changed[0][0] == "Mail: [EMAIL_1]"
    assert changed[1:] == inner[1:]
    assert form["at"] == ["csrf-fixture"]


@pytest.mark.parametrize("payload", [
    {"messages": []}, {"messages": [None]},
    {"messages": [{"content": {"content_type": "image", "parts": ["image"]}}]},
    {"messages": [{"content": {"content_type": "text", "parts": ["hello"]}}], "attachments": [{"id": "x"}]},
])
def test_unsupported_chatgpt_blocked(engine, payload):
    with pytest.raises(Blocked):
        sanitize_request(engine, CHATGPT, "POST", "application/json", json.dumps(payload))


@pytest.mark.parametrize("body", ['{"prompt":"a", "prompt":"b"}', "[1,2,3]", "not json"])
def test_invalid_claude_blocked(engine, body):
    with pytest.raises(Blocked):
        sanitize_request(engine, CLAUDE, "POST", "application/json", body)


def test_generic_json_transport_and_configurable_site(engine):
    engine.policy.protected_hosts.append("chat.example.test")
    result = sanitize_request(engine, "https://chat.example.test/api/chat", "POST", "application/json",
                              '{"input":{"text":"a@example.test"}}')
    assert result["status"] == "sanitized"
    assert json.loads(result["body"])["input"]["text"] == "[EMAIL_1]"


def test_unknown_binary_on_protected_site_is_blocked(engine):
    with pytest.raises(Blocked, match="unsupported_content_type"):
        sanitize_request(engine, "https://chatgpt.com/new-protocol", "POST", "application/octet-stream", "binary")


def test_unprotected_host_not_touched(engine):
    result = sanitize_request(engine, "https://chatgpt.com.evil.test/api", "POST", "application/json", "sensitive")
    assert result["status"] == "skipped"
    assert result["body"] == "sensitive"


def test_gemini_file_slot_is_blocked(engine):
    body = urlencode({"f.req": json.dumps([None, json.dumps([["text", 0, ["file"]]])])})
    with pytest.raises(Blocked, match="attachments_or_unknown"):
        sanitize_request(engine, GEMINI, "POST", "application/x-www-form-urlencoded", body)


@pytest.mark.parametrize("url,body", [
    ("https://api.openai.com/v1/responses", {"input": [{"role": "user", "content": "Email a@example.test"}], "stream": True}),
    ("https://api.anthropic.com/v1/messages", {"messages": [{"role": "user", "content": [{"type": "text", "text": "Email a@example.test"}]}]}),
    ("https://api.individual.githubcopilot.com/chat/completions", {"messages": [{"role": "user", "content": "Email a@example.test"}]}),
])
def test_coding_client_json_protocols(engine, url, body):
    result = sanitize_request(engine, url, "POST", "application/json", json.dumps(body))
    assert result["status"] == "sanitized"
    assert "a@example.test" not in result["body"]
    assert "[EMAIL_1]" in result["body"]


def test_host_wildcard_has_dns_boundaries():
    assert host_matches("api.business.githubcopilot.com", ["*.githubcopilot.com"])
    assert not host_matches("githubcopilot.com.evil.test", ["*.githubcopilot.com"])
    assert not host_matches("fakegithubcopilot.com", ["*.githubcopilot.com"])


def test_signalr_keeps_framing(engine):
    result = sanitize_websocket(engine, '{"protocol":"json","version":1}\x1e{"arguments":[{"message":{"text":"a@example.test"}}]}\x1e')
    assert result.count("\x1e") == 2
    assert "a@example.test" not in result and "[EMAIL_1]" in result


def test_unknown_websocket_is_blocked(engine):
    with pytest.raises(Blocked):
        sanitize_websocket(engine, "binary-ish-protocol-data")
