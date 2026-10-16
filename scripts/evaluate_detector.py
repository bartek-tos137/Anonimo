"""Local detector evaluation; never print dataset text or model responses."""
import argparse
from collections import Counter
import json
from pathlib import Path
import statistics
import time

from anonimo.config import load_policy
from anonimo.detector import DetectionError, LocalDetector


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    args = parser.parse_args()
    policy = load_policy(args.policy)
    if not policy.model.enabled:
        parser.error("Enable the local model in the evaluation policy first")
    detector = LocalDetector(policy.model)
    counts, latency = Counter(), []
    by_label = {label: Counter() for label in policy.model.labels}
    for line in args.dataset.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        text = record["text"]
        if len(text) > policy.max_text_chars:
            parser.error("Dataset contains a sample over the configured text limit")
        gold = {(e["start"], e["end"], e["label"]) for e in record["entities"]}
        if any(not (isinstance(a, int) and isinstance(b, int) and 0 <= a < b <= len(text))
               or label not in by_label for a, b, label in gold):
            parser.error("Dataset contains invalid spans or labels")
        start = time.perf_counter()
        try:
            predicted = {(span.start, span.end, span.label) for span in detector.detect([text])}
        except DetectionError:
            counts["errors"] += 1
            predicted = set()
        latency.append(1000 * (time.perf_counter() - start))
        counts["samples"] += 1
        for label, metrics in by_label.items():
            actual = {x for x in gold if x[2] == label}
            found = {x for x in predicted if x[2] == label}
            metrics.update(tp=len(actual & found), fp=len(found - actual), fn=len(actual - found))
    if not latency:
        parser.error("Dataset is empty")
    result = {"samples": counts["samples"], "model_errors": counts["errors"], "per_label": {}}
    for label, c in by_label.items():
        precision = c["tp"] / (c["tp"] + c["fp"]) if c["tp"] + c["fp"] else None
        recall = c["tp"] / (c["tp"] + c["fn"]) if c["tp"] + c["fn"] else None
        result["per_label"][label] = {**dict(c), "precision": precision, "recall": recall}
    result["latency_ms"] = {"p50": statistics.median(latency), "p95": sorted(latency)[max(0, (95 * len(latency) + 99) // 100 - 1)]}
    print(json.dumps(result, indent=2))
    return 1 if counts["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
