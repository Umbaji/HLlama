import unittest

from app.services.circuit_breaker import CircuitBreaker, CircuitState


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class CircuitBreakerTests(unittest.TestCase):
    def test_open_circuit_allows_only_one_half_open_probe(self) -> None:
        clock = FakeClock()
        circuit = CircuitBreaker(1, 30, clock)

        circuit.record_failure()
        self.assertFalse(circuit.acquire())
        self.assertEqual(circuit.snapshot().state, CircuitState.OPEN)

        clock.now = 30
        self.assertTrue(circuit.acquire())
        self.assertFalse(circuit.acquire())
        self.assertEqual(circuit.snapshot().state, CircuitState.HALF_OPEN)

        circuit.record_success()
        self.assertTrue(circuit.acquire())
        self.assertEqual(circuit.snapshot().state, CircuitState.CLOSED)

    def test_custom_failure_cooldown_is_applied(self) -> None:
        clock = FakeClock()
        circuit = CircuitBreaker(1, 30, clock)

        circuit.record_failure(120)

        self.assertEqual(circuit.snapshot().retry_after_seconds, 120)


if __name__ == "__main__":
    unittest.main()
