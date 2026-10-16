import argparse
import asyncio
import os
from pathlib import Path
import secrets

import uvicorn

from .api import create_app
from .config import load_policy


def load_or_create_token(path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        token = path.read_text(encoding="utf-8").strip()
    else:
        token = secrets.token_urlsafe(32)
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            file.write(token + "\n")
    if len(token) < 32 or any(x.isspace() for x in token):
        raise ValueError("Invalid token file; expected at least 32 non-space characters")
    return token


def main():
    parser = argparse.ArgumentParser(description="Anonimo local prompt pseudonymizer")
    parser.add_argument("command", choices=["serve", "background", "init-ca", "check-policy"])
    parser.add_argument("--policy", type=Path, default=Path("policy.yaml"))
    parser.add_argument("--token-file", type=Path, default=Path(".local/token"))
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--proxy-port", type=int, default=8877)
    parser.add_argument("--state-dir", type=Path, default=Path(".local/proxy"))
    parser.add_argument("--burp-upstream")
    parser.add_argument("--burp-ca", type=Path)
    args = parser.parse_args()
    if args.command == "init-ca":
        from .proxy import initialize_ca
        initialize_ca(args.state_dir)
        print("Local certificate authority initialized.")
        return
    try:
        policy = load_policy(args.policy)
    except Exception:
        parser.exit(2, "Invalid or unreadable policy. Check the YAML schema and regex rules.\n")
    if args.command == "check-policy":
        print(f"Policy valid: {len(policy.rules)} rules; model {'enabled' if policy.model.enabled else 'disabled'}")
        return
    try:
        token = load_or_create_token(args.token_file)
    except (OSError, ValueError):
        parser.exit(2, "Cannot initialize token file. Check path and permissions.\n")
    if args.command == "background":
        from .proxy import background
        asyncio.run(background(policy, token, args.state_dir, args.port, args.proxy_port,
                               args.burp_upstream, args.burp_ca))
        return
    uvicorn.run(create_app(policy, token), host="127.0.0.1", port=args.port,
                access_log=False, log_level="warning", limit_concurrency=64)


if __name__ == "__main__":
    main()
