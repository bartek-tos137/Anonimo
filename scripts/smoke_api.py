"""Read the local token without printing it; exercise the running API."""
import argparse
from pathlib import Path

import httpx

parser = argparse.ArgumentParser()
parser.add_argument("--token-file", type=Path, default=Path(".local/token"))
parser.add_argument("--port", type=int, default=8765)
args = parser.parse_args()
with httpx.Client(base_url=f"http://127.0.0.1:{args.port}", trust_env=False, timeout=12) as client:
    health = client.get("/health")
    health.raise_for_status()
    response = client.post("/v1/sanitize-text", headers={
        "Authorization": "Bearer " + args.token_file.read_text().strip(),
    }, json={"text": "Email: anna@example.test. NIP: 5260250274. Netto: 1000 PLN"})
    response.raise_for_status()
    result = response.json()
    assert result["status"] == "sanitized", result.get("reason", "blocked")
    assert "anna@example.test" not in result["text"]
    assert "5260250274" not in result["text"]
    assert "1000 PLN" in result["text"]
    print("API smoke passed; mode:", health.json()["mode"])
