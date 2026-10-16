"""Synthetic rules-only microbenchmark. Not a model-accuracy benchmark."""
from pathlib import Path
import statistics
import time

from anonimo.config import load_policy
from anonimo.engine import Engine

policy = load_policy(Path(__file__).resolve().parents[1] / "policy.yaml")
if policy.model.enabled:
    raise SystemExit("Use the default rules-only policy for this microbenchmark")
engine = Engine(policy)
for chars in [1000, 5000, 20000]:
    text = ("Faktura. Kontakt: anna@example.test. NIP: 5260250274. Netto 1000 PLN.\n" * 400)[:chars]
    samples = []
    for i in range(110):
        before = time.perf_counter()
        engine.sanitize([text])
        elapsed = 1000 * (time.perf_counter() - before)
        if i >= 10:
            samples.append(elapsed)
    print(f"{chars} chars: p50={statistics.median(samples):.2f} ms, p95={sorted(samples)[94]:.2f} ms (100 runs; rules only)")
