"""Background HTTPS proxy. Originals exist only in memory during inspection."""
import asyncio
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

from .adapters import host_matches, sanitize_request, sanitize_websocket
from .detector import DetectionError
from .engine import Blocked, Engine


class AnonimoAddon:
    def __init__(self, engine: Engine):
        self.engine = engine
        self.pending = 0

    def protected(self, flow):
        return host_matches(flow.request.host, self.engine.policy.protected_hosts)

    @staticmethod
    def block(flow, reason):
        from mitmproxy import http
        flow.response = http.Response.make(422, json.dumps({
            "error": "anonimo_blocked", "reason": reason,
            "message": "Anonimo could not safely process this request.",
        }).encode(), {"Content-Type": "application/json", "Cache-Control": "no-store"})
        # Avoid retaining rejected plaintext in the flow object.
        flow.request.content = b""

    def requestheaders(self, flow):
        if not self.protected(flow):
            return
        if flow.request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            encoding = flow.request.headers.get("content-encoding", "identity").lower()
            if encoding != "identity":
                self.block(flow, "compressed_request_unsupported")

    async def request(self, flow):
        if not self.protected(flow) or flow.response is not None:
            return
        if flow.request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
            return
        if self.pending >= 4:
            self.block(flow, "analysis_busy")
            return
        self.pending += 1
        try:
            if len(flow.request.raw_content or b"") > 262144:
                raise Blocked("body_limit_exceeded")
            result = await asyncio.to_thread(
                sanitize_request, self.engine, flow.request.url, flow.request.method,
                flow.request.headers.get("content-type", ""),
                flow.request.get_text(strict=True),
            )
            if result["status"] != "sanitized":
                raise Blocked("unsupported_transport")
            # Mitmproxy updates Content-Length and preserves unrelated headers.
            flow.request.set_text(result["body"])
            flow.metadata["anonimo"] = {"status": "sanitized", "counts": result["counts"]}
        except (Blocked, DetectionError) as exc:
            self.block(flow, str(exc))
        except Exception:
            self.block(flow, "analysis_failed")
        finally:
            self.pending -= 1

    def responseheaders(self, flow):
        # Preserve streaming LLM replies; never buffer an entire SSE response.
        if self.protected(flow) and flow.response is not None and flow.response.status_code != 101:
            flow.response.stream = True

    async def websocket_message(self, flow):
        if not self.protected(flow) or flow.websocket is None:
            return
        message = flow.websocket.messages[-1]
        if not message.from_client:
            return
        if not message.is_text or self.pending >= 4:
            message.drop()
            message.content = b""
            flow.metadata["anonimo"] = {"status": "blocked", "reason": "websocket_binary_or_busy"}
            return
        self.pending += 1
        try:
            clean = await asyncio.to_thread(sanitize_websocket, self.engine, message.content.decode("utf-8"))
            message.content = clean.encode("utf-8")
            flow.metadata["anonimo"] = {"status": "sanitized"}
        except Exception:
            message.drop()
            message.content = b""
            flow.metadata["anonimo"] = {"status": "blocked", "reason": "websocket_analysis_failed"}
        finally:
            self.pending -= 1


def initialize_ca(state_dir: Path):
    from mitmproxy.certs import CertStore
    state_dir.mkdir(parents=True, exist_ok=True)
    CertStore.from_store(state_dir, "mitmproxy", 2048)


async def background(policy, token: str, state_dir: Path, api_port: int, proxy_port: int,
                     burp_upstream: str | None = None, burp_ca: Path | None = None):
    import uvicorn
    from mitmproxy.options import Options
    from mitmproxy.tools.dump import DumpMaster
    from .api import create_app

    kwargs = {}
    if burp_upstream:
        url = urlsplit(burp_upstream)
        if url.scheme != "http" or url.hostname != "127.0.0.1" or not url.port or url.path or url.query or url.fragment or url.username:
            raise ValueError("Burp upstream must be http://127.0.0.1:PORT")
        if burp_ca is None or not burp_ca.is_file():
            raise ValueError("Burp requires its exported PEM CA via --burp-ca")
        kwargs["mode"] = ["upstream:" + burp_upstream]
        kwargs["ssl_verify_upstream_trusted_ca"] = str(burp_ca.resolve())
    patterns = [r"(?:[^.]+\.)+" + re.escape(h[2:]) if h.startswith("*.") else re.escape(h)
                for h in policy.protected_hosts]
    hosts = "^(?:" + "|".join(patterns) + r")\.?(?::\d+)?$"
    options = Options(listen_host="127.0.0.1", listen_port=proxy_port,
                      confdir=str(state_dir.resolve()), allow_hosts=[hosts], **kwargs)
    master = DumpMaster(options, with_termlog=False, with_dumper=False)
    master.options.update(connection_strategy="lazy", body_size_limit="256k")
    master.addons.add(AnonimoAddon(Engine(policy)))
    server = uvicorn.Server(uvicorn.Config(create_app(policy, token), host="127.0.0.1",
                                         port=api_port, access_log=False, log_level="warning"))
    jobs = [asyncio.create_task(master.run()), asyncio.create_task(server.serve())]
    try:
        done, _ = await asyncio.wait(jobs, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            await task
        raise RuntimeError("A background component stopped; restart Anonimo")
    finally:
        master.shutdown()
        server.should_exit = True
        await asyncio.gather(*jobs, return_exceptions=True)
