# ElevenLabs French TTS

## Purpose

HLlama uses ElevenLabs for high-quality French voice replies while preserving local
speech engines as availability fallbacks. Ewé, Mina, and Kabyè remain on the existing
MMS paths because they are not listed among ElevenLabs' supported TTS languages.

## Provider order

For `TTS_PROVIDER=elevenlabs`, French synthesis follows this order:

1. ElevenLabs Flash v2.5 streams MP3 directly to the output file.
2. Piper synthesizes the configured local French voice when ElevenLabs is unavailable.
3. MMS-VITS is the final local fallback when Piper is also unavailable.

The text response is already delivered before TTS starts, so complete TTS failure never
removes the user's written answer.

## Fast fallback contract

- The ElevenLabs request has separate short connection and bounded read timeouts.
- There are no synchronous HTTP retries; a retry would add latency before local fallback.
- A thread-safe circuit breaker opens after the configured number of consecutive failures.
- While open, all requests bypass ElevenLabs and immediately use Piper.
- After cooldown, exactly one request probes ElevenLabs. Other concurrent requests keep
  using Piper until that probe succeeds.
- Authentication failures open the circuit for a longer period because retrying the same
  credential cannot recover.
- Payment-required failures open the circuit for 30 minutes because a local retry cannot
  change the ElevenLabs subscription state.
- Rate limiting respects `Retry-After` when present, within a bounded interval.
- Empty, oversized, or non-audio responses count as provider failures.
- Partial files are removed and never uploaded to WhatsApp.

## Configuration

```env
TTS_PROVIDER=elevenlabs
ELEVENLABS_API_KEY=<secret>
ELEVENLABS_VOICE_ID=<voice-id>
ELEVENLABS_MODEL_ID=eleven_flash_v2_5
ELEVENLABS_OUTPUT_FORMAT=mp3_44100_128
ELEVENLABS_CONNECT_TIMEOUT_SECONDS=1.5
ELEVENLABS_READ_TIMEOUT_SECONDS=15
ELEVENLABS_CIRCUIT_FAILURE_THRESHOLD=1
ELEVENLABS_CIRCUIT_COOLDOWN_SECONDS=60
ELEVENLABS_AUTH_COOLDOWN_SECONDS=300
ELEVENLABS_BILLING_COOLDOWN_SECONDS=1800
ELEVENLABS_MAX_AUDIO_BYTES=10485760
ELEVENLABS_STABILITY=0.55
ELEVENLABS_SIMILARITY_BOOST=0.80
ELEVENLABS_STYLE=0
ELEVENLABS_SPEAKER_BOOST=true
ELEVENLABS_SPEED=0.95
```

`ELEVENLABS_API_KEY` must come from your platform's secret manager. It must never be
committed, logged, returned by an endpoint, or included in a container image.

## API contract

The provider calls:

`POST https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream`

The exact configured voice ID, model, output format, and voice settings are sent for each
request. The API key is passed in the `xi-api-key` header.

Choose a voice in the ElevenLabs dashboard and set its identifier in
`ELEVENLABS_VOICE_ID`. Validate the chosen model and voice with a direct provider call
before enabling it in production.

## Operations

Monitor provider failures, circuit-open messages, fallback usage, response latency, and
ElevenLabs quota. Logs may contain status codes and failure classes but never response
bodies or credentials.
