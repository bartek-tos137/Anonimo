import asyncio
import json

from mitmproxy import http
from mitmproxy.test import tflow

from anonimo.proxy import AnonimoAddon


def flow(url="https://chatgpt.com/backend-api/conversation", body=None):
    item = tflow.tflow()
    item.request = http.Request.make("POST", url, json.dumps(body or {
        "messages": [{"content": {"content_type": "text", "parts": ["a@example.test"]}}]
    }), {"Content-Type": "application/json", "Cookie": "synthetic-session"})
    item.response = None
    return item


def test_proxy_rewrites_and_preserves_session(engine):
    addon, request = AnonimoAddon(engine), flow()
    asyncio.run(addon.request(request))
    assert "a@example.test" not in request.request.text
    assert "[EMAIL_1]" in request.request.text
    assert request.request.headers["Cookie"] == "synthetic-session"
    assert int(request.request.headers["Content-Length"]) == len(request.request.raw_content)
    assert request.response is None


def test_proxy_blocked_request_does_not_retain_body(engine):
    addon, request = AnonimoAddon(engine), flow(body={"messages": ["invalid"]})
    asyncio.run(addon.request(request))
    assert request.response.status_code == 422
    assert request.request.raw_content == b""


def test_nonprotected_host_untouched(engine):
    addon, request = AnonimoAddon(engine), flow("https://example.test/api")
    original = request.request.raw_content
    asyncio.run(addon.request(request))
    assert request.request.raw_content == original


def test_compression_blocked(engine):
    addon = AnonimoAddon(engine)
    for name, value in [("Content-Encoding", "gzip")]:
        request = flow()
        request.request.headers[name] = value
        addon.requestheaders(request)
        assert request.response.status_code == 422


def test_sse_is_streamed(engine):
    request = flow()
    request.response = http.Response.make(200, b"data: event\n\n", {"Content-Type": "text/event-stream"})
    AnonimoAddon(engine).responseheaders(request)
    assert request.response.stream is True


def test_capacity_blocks_without_sending_original(engine):
    addon, request = AnonimoAddon(engine), flow()
    addon.pending = 4
    asyncio.run(addon.request(request))
    assert request.response.status_code == 422
    assert request.request.raw_content == b""


def test_websocket_outbound_sanitized_inbound_untouched(engine):
    from mitmproxy.websocket import WebSocketData, WebSocketMessage
    addon, request = AnonimoAddon(engine), flow("https://copilot.microsoft.com/chat")
    request.websocket = WebSocketData()
    request.websocket.messages.append(WebSocketMessage(1, True, b'{"text":"a@example.test"}\x1e'))
    asyncio.run(addon.websocket_message(request))
    assert b"EMAIL_1" in request.websocket.messages[-1].content
    assert request.websocket.messages[-1].content.endswith(b"\x1e")
    request.websocket.messages.append(WebSocketMessage(1, False, b"response text"))
    asyncio.run(addon.websocket_message(request))
    assert request.websocket.messages[-1].content == b"response text"
    request.websocket.messages.append(WebSocketMessage(2, True, b"binary-private"))
    asyncio.run(addon.websocket_message(request))
    assert request.websocket.messages[-1].dropped
    assert request.websocket.messages[-1].content == b""
