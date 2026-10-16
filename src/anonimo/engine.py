from collections import Counter
from dataclasses import dataclass
from datetime import date
from time import monotonic

import regex

from .config import Policy
from .detector import LocalDetector


class Blocked(Exception):
    """Only static reason codes may be exposed outside the engine."""


@dataclass(frozen=True)
class Finding:
    start: int
    end: int
    label: str
    priority: int
    action: str = "replace"


def valid_pesel(value: str) -> bool:
    digits = [int(x) for x in value]
    if len(digits) != 11 or (10 - sum(a*b for a, b in zip(digits[:10], [1,3,7,9,1,3,7,9,1,3])) % 10) % 10 != digits[10]:
        return False
    month = int(value[2:4])
    century = {0: 1900, 1: 2000, 2: 2100, 3: 2200, 4: 1800}.get(month // 20)
    try:
        date(century + int(value[:2]), month % 20, int(value[4:6]))
        return True
    except (ValueError, TypeError):
        return False


def valid_nip(value: str) -> bool:
    digits = [int(x) for x in value if x.isascii() and x.isdigit()]
    return len(digits) == 10 and len(set(digits)) > 1 and sum(a*b for a, b in zip(digits[:9], [6,5,7,2,3,4,5,6,7])) % 11 == digits[-1]


def valid_polish_iban(value: str) -> bool:
    digits = "".join(x for x in value if x.isascii() and x.isdigit())
    return len(digits) == 26 and int(digits[2:] + "2521" + digits[:2]) % 97 == 1


def merge_findings(findings: list[Finding]) -> list[Finding]:
    """Union overlaps: a partial higher-priority match must not leak the remainder."""
    groups: list[list[Finding]] = []
    group_end = -1
    for finding in sorted(findings, key=lambda f: (f.start, f.end)):
        if groups and finding.start < group_end:
            groups[-1].append(finding)
            group_end = max(group_end, finding.end)
        else:
            groups.append([finding])
            group_end = finding.end
    result = []
    for group in groups:
        best = max(group, key=lambda f: (f.priority, f.end - f.start, f.label))
        result.append(Finding(min(f.start for f in group), max(f.end for f in group),
                              best.label, best.priority))
    return result


class Engine:
    def __init__(self, policy: Policy, detector=None):
        self.policy = policy
        self.detector = detector if detector is not None else (LocalDetector(policy.model) if policy.model.enabled else None)
        self.rules = [(r, regex.compile(r.pattern or regex.escape(r.literal),
                                       0 if r.case_sensitive else regex.IGNORECASE)) for r in policy.rules]

    def sanitize(self, texts: list[str]) -> tuple[list[str], dict[str, int]]:
        if len(texts) > 2000 or sum(map(len, texts)) > self.policy.max_text_chars:
            raise Blocked("text_limit_exceeded")
        findings: list[list[Finding]] = [[] for _ in texts]
        finding_count = 0
        deadline = monotonic() + 1
        try:
            for item, text in enumerate(texts):
                for rule, pattern in self.rules:
                    if monotonic() > deadline:
                        raise Blocked("rule_budget_exceeded")
                    for match in pattern.finditer(text, timeout=self.policy.regex_timeout_seconds):
                        if match.end() == match.start():
                            continue
                        validators = {"pesel": valid_pesel, "nip": valid_nip, "polish_iban": valid_polish_iban}
                        if rule.validator and not validators[rule.validator](match.group()):
                            continue
                        if rule.action == "block":
                            raise Blocked("policy_block")
                        finding_count += 1
                        if finding_count > 4000:
                            raise Blocked("finding_limit_exceeded")
                        findings[item].append(Finding(match.start(), match.end(), rule.label, rule.priority))
        except TimeoutError:
            raise Blocked("rule_timeout") from None
        if self.detector is not None and any(texts):
            for span in self.detector.detect(texts):
                findings[span.item].append(Finding(span.start, span.end, span.label, -1))

        # Request-scoped mapping only. Never returned, persisted or reused across users.
        replacements: dict[tuple[str, str], str] = {}
        counters, counts = Counter(), Counter()
        reserved = set(regex.findall(r"\[[A-Z][A-Z0-9_]*_\d+\]", "\n".join(texts)))
        output = []
        for text, detected in zip(texts, findings):
            cursor, parts = 0, []
            for finding in merge_findings(detected):
                key = (finding.label, text[finding.start:finding.end])
                if key not in replacements:
                    while True:
                        counters[finding.label] += 1
                        placeholder = f"[{finding.label}_{counters[finding.label]}]"
                        if placeholder not in reserved:
                            break
                    reserved.add(placeholder)
                    replacements[key] = placeholder
                parts.extend((text[cursor:finding.start], replacements[key]))
                cursor = finding.end
                counts[finding.label] += 1
            parts.append(text[cursor:])
            output.append("".join(parts))
        return output, dict(counts)
