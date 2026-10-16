"""Actual CONNECT/TLS interception test; synthetic provider, no Internet requests."""
import asyncio
import json
from pathlib import Path
import socket
import ssl
import tempfile
from urllib.parse import urlencode

import httpx
from mitmproxy import http
from mitmproxy.options import Options
from mitmproxy.tools.dump import DumpMaster

from anonimo.config import load_policy
from anonimo.engine import Engine
from anonimo.proxy import AnonimoAddon


class SyntheticProvider:
    def __init__(self):
        self.received = []

    def request(self, flow):
        if flow.response is None:
            self.received.append(flow.request.text)
            flow.response = http.Response.make(200, flow.request.raw_content,
                                               {"Content-Type": "application/json"})


async def run():
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="anonimo-tls-test-") as tmp:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        options = Options(listen_host="127.0.0.1", listen_port=port, confdir=tmp)
        master = DumpMaster(options, with_termlog=False, with_dumper=False)
        master.options.update(connection_strategy="lazy", body_size_limit="256k")
        provider = SyntheticProvider()
        master.addons.add(AnonimoAddon(Engine(load_policy(root / "policy.yaml"))), provider)
        task = asyncio.create_task(master.run())
        try:
            for _ in range(100):
                try:
                    _, writer = await asyncio.open_connection("127.0.0.1", port)
                    writer.close()
                    await writer.wait_closed()
                    break
                except OSError:
                    if task.done():
                        await task
                        raise RuntimeError("Proxy stopped")
                    await asyncio.sleep(0.05)
            else:
                raise RuntimeError("Proxy did not start")
            context = ssl.create_default_context(cafile=str(Path(tmp) / "mitmproxy-ca-cert.pem"))
            async with httpx.AsyncClient(proxy=f"http://127.0.0.1:{port}", verify=context,
                                         trust_env=False, timeout=10) as client:
                prompt = "Napisz do anna@example.test. NIP: 5260250274"
                cases = [
                    ("https://chatgpt.com/backend-api/conversation", {"messages": [{"content": {"content_type": "text", "parts": [prompt]}}]}),
                    ("https://claude.ai/api/organizations/org/chat_conversations/chat/completion", {"prompt": prompt}),
                    ("https://chatgpt.com/new-json-transport", {"input": {"text": prompt}}),
                    ("https://api.openai.com/v1/responses", {"input": [{"role": "user", "content": prompt}]}),
                    ("https://api.anthropic.com/v1/messages", {"messages": [{"role": "user", "content": [{"type": "text", "text": prompt}]}]}),
                    ("https://api.individual.githubcopilot.com/chat/completions", {"messages": [{"role": "user", "content": prompt}]}),
                ]
                for url, body in cases:
                    response = await client.post(url, json=body)
                    assert response.status_code == 200, response.status_code
                    assert "anna@example.test" not in response.text and "5260250274" not in response.text
                    assert "[EMAIL_1]" in response.text and "[TAX_ID_1]" in response.text
                gemini = "https://gemini.google.com/_/BardChatUi/data/assistant.lamda.BardFrontendService/StreamGenerate"
                form = urlencode({"f.req": json.dumps([None, json.dumps([[prompt, 0, None]])]), "at": "synthetic-csrf"})
                response = await client.post(gemini, content=form, headers={"Content-Type": "application/x-www-form-urlencoded"})
                assert response.status_code == 200 and "anna%40example.test" not in response.text
                assert "EMAIL_1" in response.text and "TAX_ID_1" in response.text
                for body, media in [(b"private-file", "application/octet-stream"), (b"{broken", "application/json")]:
                    response = await client.post("https://chatgpt.com/new-json-transport", content=body,
                                                 headers={"Content-Type": media})
                    assert response.status_code == 422
                    assert response.json()["error"] == "anonimo_blocked"
            assert len(provider.received) == 7, "Blocked requests must not reach the provider"
            assert all("anna@example.test" not in body for body in provider.received)
            print("TLS proxy smoke: 7 sanitized requests reached the synthetic provider; 2 blocked before forwarding. Certificate verification enabled.")
        finally:
            master.shutdown()
            await task


if __name__ == "__main__":
    asyncio.run(run())
