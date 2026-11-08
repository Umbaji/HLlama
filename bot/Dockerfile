# Use an official Python runtime as a parent image
FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Runtime system deps only. The Google Cloud Python client is installed via pip;
# the gcloud CLI is not needed in the local runtime image.
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        cron \
        libsndfile1 \
        ffmpeg; \
    rm -rf /var/lib/apt/lists/*

# Workdir
WORKDIR /app

# Only the production manifest is copied. requirements.txt is the development
# set (it adds gradio for bot_tester.py); copying it here would bust this layer's
# cache on every dev-only dependency change.
COPY requirements.docker.txt ./

# Python deps
# Install CPU-only PyTorch wheels explicitly; otherwise the default wheel selection
# tends to pull a much heavier stack than this container can use.
# torchaudio is not installed: only identify_language() referenced it, that
# function is never reached from the webhook, and it imports lazily now.
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch \
 && pip install --no-cache-dir -r requirements.docker.txt

# Bake the speech models into the image. Downloaded at first use they cost
# ~460MB (Whisper) plus the VITS weights on every cold start, which showed up as
# 30s+ of latency on the first voice note after each new revision, and made the
# reply depend on the OpenAI CDN and the Hugging Face Hub being reachable.
ENV HF_HOME=/opt/hf \
    XDG_CACHE_HOME=/opt/cache \
    WHISPER_MODEL=small \
    WHISPER_LANGUAGE=fr \
    HF_HUB_DISABLE_TELEMETRY=1 \
    TRANSFORMERS_VERBOSITY=error \
    TOKENIZERS_PARALLELISM=false
# os.cpu_count() reports the host's cores inside a container, not the cgroup
# quota, so leaving this unset makes the ASR threads oversubscribe the 2 vCPU
# the container app allocates and fight each other. Keep it in step with the
# container's `cpu` setting.
ENV WHISPER_ENGINE=faster \
    WHISPER_COMPUTE_TYPE=int8 \
    TORCH_NUM_THREADS=2 \
    OMP_NUM_THREADS=2
RUN python -c "from faster_whisper import WhisperModel; WhisperModel('small', device='cpu', compute_type='int8')" \
 && python -c "import whisper; whisper.load_model('small')" \
 && python -c "from transformers import VitsTokenizer, VitsModel; VitsTokenizer.from_pretrained('facebook/mms-tts-fra'); VitsModel.from_pretrained('facebook/mms-tts-fra')"

# The assistant's voice. mms-tts-fra is a male single-speaker model, so the
# voice notes came back in a man's voice; siwis is a female French voice.
ENV PIPER_VOICE_DIR=/opt/piper-voices \
    PIPER_VOICE=fr_FR-siwis-medium \
    TTS_PROVIDER=piper
RUN set -eux; \
    mkdir -p "$PIPER_VOICE_DIR"; \
    base="https://huggingface.co/rhasspy/piper-voices/resolve/main/fr/fr_FR/siwis/medium"; \
    python -c "import urllib.request,os,sys; b=os.environ['PIPER_VOICE_DIR']; v=os.environ['PIPER_VOICE']; base=sys.argv[1]; [urllib.request.urlretrieve(f'{base}/{v}{ext}?download=true', os.path.join(b, v+ext)) for ext in ('.onnx', '.onnx.json')]" "$base"; \
    ls -la "$PIPER_VOICE_DIR"

# Copy app code last (changes here don't reinstall deps)
COPY . /app

# Ensure data directory exists for TTS outputs
RUN mkdir -p /app/data

# Expose your API port
EXPOSE 8000

# Start your app
CMD ["python3", "run.py"]
