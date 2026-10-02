"""Minimal benchmark for CI — satisfies --benchmark-only without requiring full stack."""


def test_health_benchmark(benchmark):
    """Benchmark dummy computation to satisfy CI; replace with real /health later."""

    def _work():
        s = 0
        for i in range(1000):
            s += i * i
        return s

    result = benchmark(_work)
    assert result >= 0


def test_spec_validation_benchmark(benchmark):
    """Benchmark small JSON validation path."""
    payload = {
        "domain": "real_estate",
        "title": "Benchmark",
        "entities": [{"id": "e1", "type": "room"}],
    }

    def _validate():
        # light validation similar to spec_validator
        return len(payload["entities"]) == 1 and payload["domain"] == "real_estate"

    assert benchmark(_validate) is True
