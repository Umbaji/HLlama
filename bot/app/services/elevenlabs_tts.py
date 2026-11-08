import logging
import os
import re
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path

import requests

from app.services.circuit_breaker import CircuitBreaker


LOGGER = logging.getLogger(__name__)
VOICE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{10,64}$")


class _SessionLocal(threading.local):
    def __init__(self) -> None:
        self.session: requests.Session | None = None


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        LOGGER.warning("Invalid %s; using the default", name)
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        LOGGER.warning("Invalid %s; using the default", name)
        return default


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    return default if value is None else value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class ElevenLabsConfig:
    api_key: str
    voice_id: str
    model_id: str
    output_format: str
    connect_timeout_seconds: float
    read_timeout_seconds: float
    circuit_failure_threshold: int
    circuit_cooldown_seconds: float
    auth_cooldown_seconds: float
    billing_cooldown_seconds: float
    max_audio_bytes: int
    stability: float
    similarity_boost: float
    style: float
    speaker_boost: bool
    speed: float

    @classmethod
    def from_environment(cls) -> "ElevenLabsConfig":
        return cls(
            api_key=os.getenv("ELEVENLABS_API_KEY", "").strip(),
            voice_id=os.getenv("ELEVENLABS_VOICE_ID", "").strip(),
            model_id=os.getenv("ELEVENLABS_MODEL_ID", "eleven_flash_v2_5").strip(),
            output_format=os.getenv("ELEVENLABS_OUTPUT_FORMAT", "mp3_44100_128").strip(),
            connect_timeout_seconds=_env_float("ELEVENLABS_CONNECT_TIMEOUT_SECONDS", 1.5),
            read_timeout_seconds=_env_float("ELEVENLABS_READ_TIMEOUT_SECONDS", 15.0),
            circuit_failure_threshold=_env_int("ELEVENLABS_CIRCUIT_FAILURE_THRESHOLD", 1),
            circuit_cooldown_seconds=_env_float("ELEVENLABS_CIRCUIT_COOLDOWN_SECONDS", 60.0),
            auth_cooldown_seconds=_env_float("ELEVENLABS_AUTH_COOLDOWN_SECONDS", 300.0),
            billing_cooldown_seconds=_env_float(
                "ELEVENLABS_BILLING_COOLDOWN_SECONDS", 1800.0
            ),
            max_audio_bytes=_env_int("ELEVENLABS_MAX_AUDIO_BYTES", 10 * 1024 * 1024),
            stability=_env_float("ELEVENLABS_STABILITY", 0.55),
            similarity_boost=_env_float("ELEVENLABS_SIMILARITY_BOOST", 0.80),
            style=_env_float("ELEVENLABS_STYLE", 0.0),
            speaker_boost=_env_bool("ELEVENLABS_SPEAKER_BOOST", True),
            speed=_env_float("ELEVENLABS_SPEED", 0.95),
        )

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and VOICE_ID_PATTERN.fullmatch(self.voice_id))


class ElevenLabsTTS:
    def __init__(
        self,
        config: ElevenLabsConfig,
        session: requests.Session | None = None,
        circuit_breaker: CircuitBreaker | None = None,
    ) -> None:
        self._config = config
        self._session = session
        self._thread_local = _SessionLocal()
        self._circuit = circuit_breaker or CircuitBreaker(
            config.circuit_failure_threshold,
            config.circuit_cooldown_seconds,
        )

    def synthesize(self, text: str, output_path: str) -> bool:
        if not text or not self._config.is_configured or not self._circuit.acquire():
            return False
        partial_path = Path(f"{output_path}.{uuid.uuid4().hex}.part")
        cooldown: float | None = None
        try:
            with self._get_session().post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{self._config.voice_id}/stream",
                headers={"xi-api-key": self._config.api_key, "Accept": "audio/mpeg"},
                params={"output_format": self._config.output_format},
                json=self._payload(text),
                stream=True,
                timeout=(
                    self._config.connect_timeout_seconds,
                    self._config.read_timeout_seconds,
                ),
            ) as response:
                cooldown = self._failure_cooldown(response)
                response.raise_for_status()
                content_type = response.headers.get("Content-Type", "").lower()
                if not (content_type.startswith("audio/") or "octet-stream" in content_type):
                    raise ValueError("ElevenLabs returned a non-audio response")
                self._write_audio(response, partial_path)
            os.replace(partial_path, output_path)
            self._circuit.record_success()
            return True
        except (OSError, ValueError, requests.RequestException) as exc:
            partial_path.unlink(missing_ok=True)
            self._circuit.record_failure(cooldown)
            LOGGER.warning("ElevenLabs TTS unavailable (%s); using local fallback", type(exc).__name__)
            return False

    def _get_session(self) -> requests.Session:
        if self._session is not None:
            return self._session
        session = self._thread_local.session
        if session is None:
            session = requests.Session()
            self._thread_local.session = session
        return session

    def _payload(self, text: str) -> dict[str, object]:
        return {
            "text": text,
            "model_id": self._config.model_id,
            "voice_settings": {
                "stability": self._config.stability,
                "similarity_boost": self._config.similarity_boost,
                "style": self._config.style,
                "use_speaker_boost": self._config.speaker_boost,
                "speed": self._config.speed,
            },
        }

    def _write_audio(self, response: requests.Response, path: Path) -> None:
        total = 0
        with path.open("wb") as output:
            for chunk in response.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                total += len(chunk)
                if total > self._config.max_audio_bytes:
                    raise ValueError("ElevenLabs audio response exceeded the configured limit")
                output.write(chunk)
        if total == 0:
            raise ValueError("ElevenLabs returned empty audio")

    def _failure_cooldown(self, response: requests.Response) -> float | None:
        if response.status_code in {401, 403}:
            return self._config.auth_cooldown_seconds
        if response.status_code == 402:
            return self._config.billing_cooldown_seconds
        if response.status_code == 429:
            try:
                retry_after = float(response.headers.get("Retry-After", ""))
            except ValueError:
                retry_after = self._config.circuit_cooldown_seconds
            return min(max(1.0, retry_after), self._config.auth_cooldown_seconds)
        return None


_CLIENT = ElevenLabsTTS(ElevenLabsConfig.from_environment())


def synthesize_elevenlabs(text: str, output_path: str) -> bool:
    return _CLIENT.synthesize(text, output_path)
