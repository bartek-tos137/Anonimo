import json
import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from anonimo.api import create_app
from anonimo.config import ModelConfig
from anonimo.detector import DetectionError, LocalDetector

TOKEN = "synthetic-test-token-" + "x" * 32


def detector_response(findings, finish_reason="stop"):
    return httpx.Response(200, json={"choices": [{"finish_reason": finish_reason, "message": {
        "content": json.dumps({"findings": findings})}}]})


def test_local_model_span_and_unicode():
    def endpoint(request):
        assert request.url.host == "127.0.0.1"
        assert "😀 Anna" in json.loads(request.content)["messages"][1]["content"]
        return detector_response([{"item": 0, "start": 2, "end": 6, "text": "Anna", "label": "PERSON"}])
    detector = LocalDetector(ModelConfig(enabled=True), httpx.MockTransport(endpoint))
    assert detector.detect(["😀 Anna"])[0].text == "Anna"


@pytest.mark.parametrize("bad", [
    {"item": 0, "start": 0, "end": 100, "text": "Anna", "label": "PERSON"},
    {"item": 2, "start": 0, "end": 4, "text": "Anna", "label": "PERSON"},
    {"item": 0, "start": 0, "end": 4, "text": "wrong", "label": "PERSON"},
    {"item": 0, "start": 0, "end": 4, "text": "Anna", "label": "UNTRUSTED"},
])
def test_invalid_model_output_is_blocked(bad):
    detector = LocalDetector(ModelConfig(enabled=True), httpx.MockTransport(lambda _: detector_response([bad])))
    with pytest.raises(DetectionError):
        detector.detect(["Anna"])


def test_truncated_model_output_is_blocked():
    detector = LocalDetector(ModelConfig(enabled=True), httpx.MockTransport(lambda _: detector_response([], "length")))
    with pytest.raises(DetectionError):
        detector.detect(["Anna"])


def test_model_redirect_is_not_followed():
    seen = []
    def endpoint(request):
        seen.append(str(request.url))
        return httpx.Response(302, headers={"Location": "https://external.invalid"})
    detector = LocalDetector(ModelConfig(enabled=True), httpx.MockTransport(endpoint))
    with pytest.raises(DetectionError):
        detector.detect(["sensitive"])
    assert len(seen) == 1


@pytest.mark.parametrize("url", ["https://example.com/v1", "http://localhost/v1", "http://127.0.0.1.evil/v1"])
def test_model_cannot_use_external_server(url):
    with pytest.raises(ValidationError):
        ModelConfig(base_url=url)


def test_authenticated_api_does_not_echo_errors(policy):
    with TestClient(create_app(policy, TOKEN), base_url="http://127.0.0.1") as client:
        assert client.get("/health").json()["mode"] == "rules_only"
        assert client.post("/v1/sanitize-text", json={"text": "secret"}).status_code == 401
        headers = {"Authorization": "Bearer " + TOKEN}
        result = client.post("/v1/sanitize-text", headers=headers, json={"text": "a@example.test"})
        assert result.json()["text"] == "[EMAIL_1]"
        invalid = client.post("/v1/sanitize-text", headers=headers, json={"text": {"secret": "private-value"}})
        assert invalid.status_code == 422
        assert "private-value" not in invalid.text
        assert client.get("/health", headers={"Host": "evil.test"}).status_code == 400
        assert client.post("/v1/sanitize-text", content=b"x" * 1048577).status_code == 413


def test_model_failure_blocks_api_request(policy):
    def fail(request):
        raise httpx.ConnectError("sensitive error must not escape")
    detector = LocalDetector(ModelConfig(enabled=True), httpx.MockTransport(fail))
    with TestClient(create_app(policy, TOKEN, detector), base_url="http://127.0.0.1") as client:
        result = client.post("/v1/sanitize-text", headers={"Authorization": "Bearer " + TOKEN}, json={"text": "private"}).json()
        assert result["status"] == "blocked"
        assert result["body"] is None
        assert "private" not in json.dumps(result)


def test_model_has_total_deadline():
    async def slow(request):
        await asyncio.sleep(0.5)
        return detector_response([])
    detector = LocalDetector(ModelConfig(enabled=True, timeout_seconds=0.1), httpx.MockTransport(slow))
    with pytest.raises(DetectionError):
        detector.detect(["sensitive"])
