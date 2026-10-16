"""Version-sensitive web payload adapters. These are not public provider APIs."""
import json
import re
from urllib.parse import parse_qsl, urlencode, urlsplit

from .engine import Blocked, Engine

PROTECTED_HOSTS = {"chatgpt.com", "chat.openai.com", "claude.ai", "gemini.google.com"}


def host_matches(host: str, patterns) -> bool:
    host = host.lower().rstrip(".")
    return any(host == pattern or (pattern.startswith("*.") and host.endswith(pattern[1:])
                                  and host != pattern[2:]) for pattern in patterns)


def provider_for(url: str, method: str, protected_hosts=PROTECTED_HOSTS) -> str | None:
    if method.upper() not in {"POST", "PUT", "PATCH", "DELETE"}:
        return None
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.port not in (None, 443):
        return None
    host, path = parsed.hostname, parsed.path
    if not host_matches(host or "", protected_hosts):
        return None
    if host in {"chatgpt.com", "chat.openai.com"}:
        if re.fullmatch(r"/backend-api/(?:f/)?conversation/?", path):
            return "chatgpt"
        if re.match(r"/backend-api/(?:f/)?files(?:/|$)", path):
            return "upload"
    if host == "claude.ai":
        if re.fullmatch(r"/api/organizations/[^/]+/chat_conversations/[^/]+/completion", path):
            return "claude"
        if re.search(r"/(?:upload|uploads|files)(?:/|$)", path):
            return "upload"
    if host == "gemini.google.com":
        if path.endswith("/BardChatUi/data/assistant.lamda.BardFrontendService/StreamGenerate"):
            return "gemini"
        if re.search(r"/(?:upload|uploads)(?:/|$)", path):
            return "upload"
    # New JSON transports still pass through the engine. Unknown binary or form
    # formats are blocked instead of being silently forwarded by the proxy.
    return "generic_json"


def reject_attachments(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {"attachments", "files", "file_ids", "file_references", "file_data", "image_url", "image", "audio", "images"} and child:
                raise Blocked("attachments_unsupported")
            if key == "type" and child in ("image", "input_image", "input_audio", "input_file", "document"):
                raise Blocked("attachments_unsupported")
            reject_attachments(child)
    elif isinstance(value, list):
        for child in value:
            reject_attachments(child)


def transform_strings(value, engine):
    texts = []

    def collect(node):
        if isinstance(node, str):
            texts.append(node)
        elif isinstance(node, list):
            for child in node:
                collect(child)
        elif isinstance(node, dict):
            for child in node.values():
                collect(child)

    collect(value)
    clean, counts = engine.sanitize(texts)
    values = iter(clean)

    def rebuild(node):
        if isinstance(node, str):
            return next(values)
        if isinstance(node, list):
            return [rebuild(x) for x in node]
        if isinstance(node, dict):
            return {k: rebuild(v) for k, v in node.items()}
        return node

    return rebuild(value), counts


def loads_unique(text):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result
    return json.loads(text, object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite JSON")))


def sanitize_request(engine: Engine, url: str, method: str, content_type: str, body: str) -> dict:
    provider = provider_for(url, method, engine.policy.protected_hosts)
    if provider is None:
        return {"status": "skipped", "body": body, "counts": {}, "reason": "outside_adapter_scope"}
    if provider == "upload":
        raise Blocked("attachments_unsupported")
    if len(body.encode("utf-8")) > 262144:
        raise Blocked("body_limit_exceeded")
    media_type = content_type.split(";", 1)[0].strip().lower()
    try:
        if provider in {"chatgpt", "claude", "generic_json"}:
            if provider == "generic_json" and not body:
                return {"status": "sanitized", "body": "", "counts": {}, "provider": provider}
            if media_type != "application/json":
                raise Blocked("unsupported_content_type")
            payload = loads_unique(body)
            if not isinstance(payload, dict) and not (provider == "generic_json" and isinstance(payload, list)):
                raise Blocked("unsupported_payload")
            if provider == "chatgpt":
                messages = payload.get("messages")
                if not isinstance(messages, list) or not messages:
                    raise Blocked("unsupported_payload")
                for message in messages:
                    content = message.get("content", {})
                    if (content.get("content_type") != "text" or not isinstance(content.get("parts"), list)
                            or not content["parts"] or not all(isinstance(x, str) for x in content["parts"])):
                        raise Blocked("unsupported_payload")
            elif provider == "claude" and not isinstance(payload.get("prompt"), str):
                raise Blocked("unsupported_payload")
            reject_attachments(payload)
            payload, counts = transform_strings(payload, engine)
            clean_body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        else:
            if media_type != "application/x-www-form-urlencoded":
                raise Blocked("unsupported_content_type")
            pairs = parse_qsl(body, keep_blank_values=True, strict_parsing=True, max_num_fields=20)
            if len({k for k, _ in pairs}) != len(pairs) or set(k for k, _ in pairs) - {"f.req", "at"}:
                raise Blocked("unsupported_payload")
            outer = loads_unique(dict(pairs)["f.req"])
            if not isinstance(outer, list) or len(outer) != 2 or outer[0] is not None or not isinstance(outer[1], str):
                raise Blocked("unsupported_payload")
            inner = loads_unique(outer[1])
            if not isinstance(inner, list) or not inner or not isinstance(inner[0], list) or not inner[0] or not isinstance(inner[0][0], str):
                raise Blocked("unsupported_payload")
            # Only the text-only prompt envelope is supported. Other prompt slots may hold files.
            if any(x not in (None, 0, "", []) for x in inner[0][1:]):
                raise Blocked("attachments_or_unknown_prompt_fields")
            reject_attachments(inner)
            inner, counts = transform_strings(inner, engine)
            outer[1] = json.dumps(inner, ensure_ascii=False, separators=(",", ":"))
            encoded = json.dumps(outer, ensure_ascii=False, separators=(",", ":"))
            clean_body = urlencode([(k, encoded if k == "f.req" else v) for k, v in pairs])
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError, IndexError):
        raise Blocked("unsupported_payload") from None
    return {"status": "sanitized", "body": clean_body, "counts": counts, "provider": provider}


def sanitize_websocket(engine: Engine, data: str) -> str:
    """JSON and SignalR JSON records only. Unknown binary protocols are unsupported."""
    if len(data.encode("utf-8")) > 262144:
        raise Blocked("body_limit_exceeded")
    trailing = data.endswith("\x1e")
    records = data[:-1].split("\x1e") if trailing else data.split("\x1e")
    try:
        values = [loads_unique(record) for record in records]
        if any(not isinstance(value, (dict, list)) for value in values):
            raise Blocked("unsupported_websocket_payload")
        reject_attachments(values)
        clean, _ = transform_strings(values, engine)
        return "\x1e".join(json.dumps(value, ensure_ascii=False, separators=(",", ":"))
                           for value in clean) + ("\x1e" if trailing else "")
    except (ValueError, TypeError, RecursionError):
        raise Blocked("unsupported_websocket_payload") from None
