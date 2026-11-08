import unittest
import uuid
from contextlib import contextmanager
from collections.abc import Iterator
from pathlib import Path

import requests

from app.services.circuit_breaker import CircuitBreaker, CircuitState
from app.services.elevenlabs_tts import ElevenLabsConfig, ElevenLabsTTS


TEST_TEMP_ROOT = Path(__file__).resolve().parent / ".tmp"
TEST_TEMP_ROOT.mkdir(exist_ok=True)


@contextmanager
def temporary_output() -> Iterator[Path]:
    output = TEST_TEMP_ROOT / f"{uuid.uuid4().hex}.mp3"
    try:
        yield output
    finally:
        output.unlink(missing_ok=True)
        for partial in TEST_TEMP_ROOT.glob(f"{output.name}.*.part"):
            partial.unlink(missing_ok=True)


class FakeResponse:
    def __init__(
        self,
        status_code: int = 200,
        chunks: tuple[bytes, ...] = (b"audio",),
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self._chunks = chunks
        self.headers = headers or {"Content-Type": "audio/mpeg"}

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            response = requests.Response()
            response.status_code = self.status_code
            raise requests.HTTPError(response=response)

    def iter_content(self, chunk_size: int) -> tuple[bytes, ...]:
        return self._chunks


class FakeSession:
    def __init__(self, responses: list[FakeResponse | Exception]) -> None:
        self.responses = responses
        self.calls = 0
        self.last_kwargs: dict[str, object] = {}

    def post(self, _url: str, **kwargs: object) -> FakeResponse:
        self.calls += 1
        self.last_kwargs = kwargs
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def make_config(**overrides: object) -> ElevenLabsConfig:
    values: dict[str, object] = {
        "api_key": "secret",
        "voice_id": "test-voice-id",
        "model_id": "eleven_flash_v2_5",
        "output_format": "mp3_44100_128",
        "connect_timeout_seconds": 1.5,
        "read_timeout_seconds": 15.0,
        "circuit_failure_threshold": 1,
        "circuit_cooldown_seconds": 60.0,
        "auth_cooldown_seconds": 300.0,
        "billing_cooldown_seconds": 1800.0,
        "max_audio_bytes": 1024,
        "stability": 0.55,
        "similarity_boost": 0.8,
        "style": 0.0,
        "speaker_boost": True,
        "speed": 0.95,
    }
    values.update(overrides)
    return ElevenLabsConfig(**values)


class ElevenLabsTTSTests(unittest.TestCase):
    def test_success_streams_audio_atomically(self) -> None:
        session = FakeSession([FakeResponse(chunks=(b"one", b"two"))])
        client = ElevenLabsTTS(make_config(), session=session)

        with temporary_output() as output:
            success = client.synthesize("Bonjour", str(output))

            self.assertTrue(success)
            self.assertEqual(output.read_bytes(), b"onetwo")
        self.assertEqual(session.last_kwargs["stream"], True)
        self.assertEqual(session.last_kwargs["timeout"], (1.5, 15.0))

    def test_timeout_opens_circuit_and_next_call_skips_network(self) -> None:
        session = FakeSession([requests.Timeout("slow")])
        circuit = CircuitBreaker(1, 60)
        client = ElevenLabsTTS(make_config(), session=session, circuit_breaker=circuit)

        self.assertFalse(client.synthesize("Bonjour", "unused.mp3"))
        self.assertFalse(client.synthesize("Encore", "unused.mp3"))
        self.assertEqual(session.calls, 1)
        self.assertEqual(circuit.snapshot().state, CircuitState.OPEN)

    def test_rate_limit_uses_retry_after_for_open_circuit(self) -> None:
        response = FakeResponse(429, headers={"Retry-After": "120"})
        session = FakeSession([response])
        circuit = CircuitBreaker(1, 60)
        client = ElevenLabsTTS(make_config(), session=session, circuit_breaker=circuit)

        self.assertFalse(client.synthesize("Bonjour", "unused.mp3"))

        self.assertGreater(circuit.snapshot().retry_after_seconds, 119)

    def test_invalid_audio_response_is_rejected_and_removed(self) -> None:
        response = FakeResponse(headers={"Content-Type": "application/json"})
        client = ElevenLabsTTS(make_config(), session=FakeSession([response]))

        with temporary_output() as output:
            self.assertFalse(client.synthesize("Bonjour", str(output)))
            self.assertFalse(output.exists())
            self.assertEqual(list(TEST_TEMP_ROOT.glob(f"{output.name}.*.part")), [])

    def test_payment_required_opens_long_billing_cooldown(self) -> None:
        session = FakeSession([FakeResponse(402)])
        circuit = CircuitBreaker(1, 60)
        client = ElevenLabsTTS(make_config(), session=session, circuit_breaker=circuit)

        self.assertFalse(client.synthesize("Bonjour", "unused.mp3"))

        self.assertGreater(circuit.snapshot().retry_after_seconds, 1799)


if __name__ == "__main__":
    unittest.main()
