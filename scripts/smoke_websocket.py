"""Real WSS/CONNECT test against a local TLS origin, with certificate verification."""
import asyncio
from pathlib import Path
import socket
import ssl
import tempfile

from cryptography.hazmat.primitives import serialization
from mitmproxy.certs import CertStore
from mitmproxy.options import Options
from mitmproxy.tools.dump import DumpMaster
from websockets.asyncio.client import connect
from websockets.asyncio.server import serve

from anonimo.config import load_policy
from anonimo.engine import Engine
from anonimo.proxy import AnonimoAddon


async def run():
    received = []
    async def echo(connection):
        async for message in connection:
            received.append(message)
            await connection.send(message)

    with tempfile.TemporaryDirectory(prefix="anonimo-wss-test-") as tmp:
        directory = Path(tmp)
        store = CertStore.from_store(directory, "mitmproxy", 2048)
        certificate = store.get_cert("copilot.microsoft.com", ["copilot.microsoft.com"])
        (directory / "origin.pem").write_bytes(certificate.cert.to_pem())
        (directory / "origin.key").write_bytes(certificate.privatekey.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption()))
        origin_tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        origin_tls.load_cert_chain(directory / "origin.pem", directory / "origin.key")
        ca = directory / "mitmproxy-ca-cert.pem"
        async with serve(echo, "127.0.0.1", 0, ssl=origin_tls) as origin:
            origin_port = origin.sockets[0].getsockname()[1]
            class RouteToLocalOrigin:
                def error(self, flow):
                    print("Synthetic WSS fixture transport error:", flow.error)

                def server_connect(self, data):
                    if data.server.address[0] == "copilot.microsoft.com":
                        data.server.address = ("127.0.0.1", origin_port)
                        data.server.sni = "copilot.microsoft.com"
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                proxy_port = sock.getsockname()[1]
            master = DumpMaster(Options(listen_host="127.0.0.1", listen_port=proxy_port, confdir=tmp,
                                        ssl_verify_upstream_trusted_ca=str(ca)),
                                with_termlog=False, with_dumper=False)
            master.options.update(connection_strategy="lazy")
            policy = load_policy(Path(__file__).resolve().parents[1] / "policy.yaml")
            master.addons.add(AnonimoAddon(Engine(policy)), RouteToLocalOrigin())
            task = asyncio.create_task(master.run())
            try:
                for _ in range(100):
                    try:
                        _, writer = await asyncio.open_connection("127.0.0.1", proxy_port)
                        writer.close()
                        await writer.wait_closed()
                        break
                    except OSError:
                        if task.done():
                            await task
                        await asyncio.sleep(0.05)
                client_tls = ssl.create_default_context(cafile=str(ca))
                async with connect("wss://copilot.microsoft.com/chat", proxy=f"http://127.0.0.1:{proxy_port}",
                                   ssl=client_tls, open_timeout=10, compression=None) as client:
                    await client.send('{"arguments":[{"text":"anna@example.test"}]}\x1e')
                    response = await asyncio.wait_for(client.recv(), timeout=5)
                    assert "EMAIL_1" in response and "anna@example.test" not in response
                    assert response.endswith("\x1e")
                    await client.send(b"binary-private-data")
                    try:
                        await asyncio.wait_for(client.recv(), timeout=0.25)
                        raise AssertionError("Binary request reached origin")
                    except asyncio.TimeoutError:
                        pass
                assert len(received) == 1 and "anna@example.test" not in received[0]
                print("WSS proxy smoke: JSON/SignalR redacted; binary message blocked; TLS verified on both connections.")
            finally:
                master.shutdown()
                await task


if __name__ == "__main__":
    asyncio.run(run())
