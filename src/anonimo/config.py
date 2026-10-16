from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

import regex
import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Rule(StrictModel):
    id: str = Field(pattern=r"^[a-z0-9_-]+$")
    label: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,39}$")
    pattern: str | None = None
    literal: str | None = None
    case_sensitive: bool = True
    action: Literal["replace", "block"] = "replace"
    priority: int = 0
    validator: Literal["pesel", "nip", "polish_iban"] | None = None

    @model_validator(mode="after")
    def check_pattern(self):
        if bool(self.pattern) == bool(self.literal):
            raise ValueError("A rule needs exactly one nonempty pattern or literal")
        regex.compile(self.pattern or regex.escape(self.literal))
        return self


class ModelConfig(StrictModel):
    enabled: bool = False
    base_url: str = "http://127.0.0.1:8080/v1"
    model: str = "local-dlp"
    timeout_seconds: float = Field(default=6, ge=0.1, le=9)
    labels: list[str] = ["PERSON", "ORGANIZATION", "CONFIDENTIAL"]

    @field_validator("base_url")
    @classmethod
    def local_only(cls, value):
        url = urlsplit(value)
        if (url.scheme != "http" or url.hostname not in {"127.0.0.1", "::1"}
                or url.username or url.password or url.query or url.fragment):
            raise ValueError("Model must use a literal loopback HTTP address")
        return value.rstrip("/")

    @field_validator("labels")
    @classmethod
    def valid_labels(cls, values):
        if not values or any(not regex.fullmatch(r"[A-Z][A-Z0-9_]{0,39}", x) for x in values):
            raise ValueError("Invalid model labels")
        return values


class Policy(StrictModel):
    version: Literal[1] = 1
    protected_hosts: list[str] = ["chatgpt.com", "chat.openai.com", "claude.ai", "gemini.google.com"]
    max_text_chars: int = Field(default=50000, ge=1, le=200000)
    regex_timeout_seconds: float = Field(default=0.03, ge=0.001, le=0.1)
    model: ModelConfig = ModelConfig()
    rules: list[Rule]

    @field_validator("protected_hosts")
    @classmethod
    def valid_hosts(cls, values):
        if not values or any(not regex.fullmatch(r"(?:\*\.)?[a-z0-9]+(?:[.-][a-z0-9]+)*\.[a-z]{2,}", x) for x in values):
            raise ValueError("Use lowercase DNS names, optionally with a leading *.")
        return sorted(set(values))

    @model_validator(mode="after")
    def unique_rules(self):
        if len({r.id for r in self.rules}) != len(self.rules):
            raise ValueError("Rule IDs must be unique")
        return self


def load_policy(path: Path) -> Policy:
    return Policy.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
