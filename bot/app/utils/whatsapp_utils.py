# Imports are deliberately narrow. This module is imported at Flask startup, so
# every top-level import is paid on every cold start of every replica. gradio,
# pandas, the ffmpeg pip stub and the unused transformers Auto* classes were
# imported here without a single call site; speechbrain and torchaudio are now
# loaded lazily because only identify_language() needs them. The whole voice
# stack (torch, librosa, whisper, soundfile, numpy) is lazy for the same
# reason: nothing on the text path reaches it, and a top-level import of it made
# this module unimportable without a multi-gigabyte install, which is why no
# test could import it.
import importlib
import subprocess
import sys
import os
import logging
import json
import requests
import glob
import uuid
import re
import dateparser
from datetime import datetime, timezone
from unidecode import unidecode
from langdetect import detect
from num2words import num2words
from pydub import AudioSegment
from flask import current_app
from openai import OpenAI
from google.cloud import translate_v3
from transformers import pipeline, VitsTokenizer, VitsModel

from app.services.bot_profile import resolve_preferred_name
from app.services.emergency_contacts import emergency_contact_payload
from app.services.elevenlabs_tts import synthesize_elevenlabs

from app.services.backend_client import backend_base_url, backend_headers
from app.services.button_router import extract_button_id, route_button_reply
from app.services.chat_state import (
    awaiting_her_answer,
    consent_gated,
    emergency_offer,
    pending_place_category,
    reminder_detail_pending,
    reminder_detail_shown,
)
from app.services import consent_hold, intents, menu, pending_notices
from app.services.model_failure import category_for_provider_error
from app.services.feedback import consume_feedback_comment, schedule_feedback
from app.services import health_fact_flow, knowledge, memory_notes, reminder_flow, reminder_update
from app.services.local_time import zone, zone_name_for_wa_id
from app.services import health_facts
from app.services.reminder_status import (
    NO_DETAIL_TEXT,
    extract_cancel_number,
    forget_snapshot,
    handle_cancel_one,
    handle_list_request,
    is_detail_request,
    is_list_request,
    snapshot,
)
from app.services.whatsapp_api import (
    get_text_message_input,
    send_message,
)
from app.utils.anonymity import pseudo_id_for

from .consent_gate import consent_gate_payload

try :
    from TTS.api import TTS
except : 
    pass 

# Set logging level to ERROR to suppress warnings
logging.getLogger("transformers").setLevel(logging.ERROR)
# Configure logging
logging.getLogger("speechbrain").setLevel(logging.ERROR)


class _LazyModule:
    """Stands in for a module that is imported on its first attribute access.

    Every call site keeps working unchanged (`torch.no_grad()`, `sf.write(...)`,
    `librosa.load(...)`, `np.concatenate(...)`): the first one imports the real
    module, and the alias is rebound to it in `globals()`, so later calls skip
    the proxy entirely. Import cost moves from process start to the first voice
    message, which is where it is actually needed.
    """

    def __init__(self, name: str, alias: str | None = None):
        self._name = name
        self._alias = alias
        self._module = None

    def _load(self):
        if self._module is None:
            self._module = importlib.import_module(self._name)
            if self._alias:
                globals()[self._alias] = self._module
        return self._module

    def __getattr__(self, attribute):
        return getattr(self._load(), attribute)


librosa = _LazyModule("librosa")
torch = _LazyModule("torch")
whisper = _LazyModule("whisper")
sf = _LazyModule("soundfile", alias="sf")
np = _LazyModule("numpy", alias="np")


# Uncomment and use this block if you need to install/update packages programmatically
# try:
#     subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])
#     subprocess.check_call([sys.executable, "--version"])
#     subprocess.check_call([sys.executable, "-m", "pip", "install",
#                            "torch", "torchaudio", "transformers", "gradio",
#                            "soundfile", "pydub", "librosa"])
#     print("Packages installed successfully!")
# except subprocess.CalledProcessError:
#     print("Error installing packages")

# Configuration and Environment Variables

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "your-project-id")

### IN IMPROVED VERSION,THIS IN .ENV FILE AND ALL SECRET STORED IN AZURE KEY VAULT
endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "")
deployment_name = os.getenv("DEPLOYMENT_NAME", "your-deployment-name")
api_key = os.getenv("AZURE_OPENAI_API_KEY", "")

# Bounded so a slow Azure call cannot pin a webhook worker thread for the
# SDK default (10 min, with retries).
client = OpenAI(
    base_url=endpoint,
    api_key=api_key,
    timeout=float(os.getenv("OPENAI_TIMEOUT_SECONDS", "20")),
    max_retries=int(os.getenv("OPENAI_MAX_RETRIES", "1")),
)



# Use these for local inference
#model_repo = "Umbaji/HLlama"

#HLtokenizer = AutoTokenizer.from_pretrained(model_repo, trust_remote_code=True)
#HLlama = AutoModelForCausalLM.from_pretrained(model_repo, device_map="auto", torch_dtype=torch.float16, trust_remote_code=True)
#HLlama.eval()
# ASR and TTS models are loaded lazily on first use to keep startup fast.
_ASR_EWE = {"model": None}
_TTS_EWE = {"tokenizer": None, "model": None}
_ASR_EN = {"model": None}
_SLID = {"model": None}
_TTS_KDH = {"tokenizer": None, "model": None}
_TTS_GEJ = {"tokenizer": None, "model": None}
_WHISPER = {"model": None, "engine": None}

# Whisper's own language detection reads the first 30s of audio. WhatsApp voice
# notes are often 2-3s, and on those it guesses wildly: production logs showed
# French notes detected as "ko" and "ru", which routed them into the Ewe branch
# and lost the reply. The audience is francophone, so pin the language by
# default. Set WHISPER_LANGUAGE=auto to restore detection.
WHISPER_MODEL_NAME = os.getenv("WHISPER_MODEL", "small")
WHISPER_LANGUAGE = os.getenv("WHISPER_LANGUAGE", "fr").strip().lower()
# Languages the assistant answers in directly, without the Ewe detour.
DIRECT_LANGUAGES = {"fr", "en"}

# ASR engine. openai-whisper runs the model as FP32 PyTorch and always decodes a
# padded 30s window, so a 3s voice note cost 42s on the container's 2 cores and
# dominated the reply time. faster-whisper runs the same weights through
# CTranslate2 with int8 quantisation and a VAD that skips silence, which is
# several times faster for identical output. openai-whisper stays as fallback.
#   WHISPER_ENGINE        faster (default) | openai
#   WHISPER_COMPUTE_TYPE  int8 (default) | int8_float32 | float32
#   WHISPER_BEAM_SIZE     1 (default, greedy) - higher trades speed for accuracy
WHISPER_ENGINE = os.getenv("WHISPER_ENGINE", "faster").strip().lower()
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
WHISPER_BEAM_SIZE = int(os.getenv("WHISPER_BEAM_SIZE", "1"))


# Torch defaults to one thread per detected host core, but the container is
# capped at 2 CPUs. Oversubscribing makes the threads fight for the quota and
# measurably slows transcription down, so match the allocation. Applied from the
# two entry points to speech, not at import: importing torch is exactly what
# this module now refuses to do on the text path.
def _configure_torch_threads() -> None:
    try:
        _TORCH_THREADS = int(os.getenv("TORCH_NUM_THREADS", "0")) or (os.cpu_count() or 2)
        torch.set_num_threads(max(1, min(_TORCH_THREADS, os.cpu_count() or 2)))
    except Exception as _thread_err:  # pragma: no cover - defensive
        logging.warning(f"Could not set torch thread count: {_thread_err}")


def get_whisper():
    """Loads the ASR model once, preferring faster-whisper over openai-whisper."""
    if _WHISPER["model"] is not None:
        return _WHISPER["model"]
    _configure_torch_threads()

    if WHISPER_ENGINE == "faster":
        try:
            from faster_whisper import WhisperModel
            logging.info(
                f"Loading faster-whisper '{WHISPER_MODEL_NAME}' "
                f"({WHISPER_COMPUTE_TYPE}, {_asr_threads()} threads)..."
            )
            _WHISPER["model"] = WhisperModel(
                WHISPER_MODEL_NAME,
                device="cpu",
                compute_type=WHISPER_COMPUTE_TYPE,
                cpu_threads=_asr_threads(),
            )
            _WHISPER["engine"] = "faster"
            logging.info("faster-whisper ready")
            return _WHISPER["model"]
        except Exception as exc:
            logging.warning(f"faster-whisper unavailable, falling back to openai-whisper: {exc}")

    logging.info(f"Loading openai-whisper '{WHISPER_MODEL_NAME}'...")
    _WHISPER["model"] = whisper.load_model(WHISPER_MODEL_NAME)
    _WHISPER["engine"] = "openai"
    logging.info("openai-whisper ready")
    return _WHISPER["model"]


def _asr_threads() -> int:
    """CPU threads for the ASR model, matching the container's allocation."""
    configured = int(os.getenv("TORCH_NUM_THREADS", "0"))
    return max(1, configured or (os.cpu_count() or 2))


def warm_speech_models() -> None:
    """Loads the speech models up front, off the request path.

    Called from run.py at boot. Without it the first person to send a voice note
    after a new revision waits for the model load on top of their own
    transcription, which was a large part of the perceived slowness.
    """
    try:
        _configure_torch_threads()
        get_whisper()
        # Piper is a subprocess with nothing to preload; only the MMS fallback
        # holds weights in memory, so do not pay for it unless it is in use.
        if TTS_PROVIDER not in {"piper", "elevenlabs"} or _piper_model_path() is None:
            get_tts_fr()
        logging.info(f"Speech models warmed up (TTS provider: {TTS_PROVIDER})")
    except Exception as exc:
        logging.warning(f"Speech model warm-up failed, will load on first use: {exc}")


def get_asr_ewe():
    if _ASR_EWE["model"] is None:
        _ASR_EWE["model"] = pipeline("automatic-speech-recognition", model="abiyo27/whisper-small-ewe")
    return _ASR_EWE["model"]


def get_tts_ewe():
    if _TTS_EWE["model"] is None:
        _TTS_EWE["tokenizer"] = VitsTokenizer.from_pretrained("facebook/mms-tts-ewe")
        _TTS_EWE["model"] = VitsModel.from_pretrained("facebook/mms-tts-ewe")
    return _TTS_EWE["tokenizer"], _TTS_EWE["model"]


def get_asr_english():
    if _ASR_EN["model"] is None:
        _ASR_EN["model"] = pipeline("automatic-speech-recognition", model="openai/whisper-small")
    return _ASR_EN["model"]


def get_slid_model():
    # Imported here rather than at module level: speechbrain pulls a large
    # dependency tree and only identify_language() below uses it, which the
    # WhatsApp flow never calls. Keeping it lazy lets prod drop the package.
    if _SLID["model"] is None:
        from speechbrain.inference import EncoderClassifier
        _SLID["model"] = EncoderClassifier.from_hparams(
            source="speechbrain/lang-id-voxlingua107-ecapa", savedir="tmp/lang-id-commonvoice"
        )
    return _SLID["model"]


def get_tts_kdh():
    if _TTS_KDH["model"] is None:
        _TTS_KDH["tokenizer"] = VitsTokenizer.from_pretrained("facebook/mms-tts-kdh")
        _TTS_KDH["model"] = VitsModel.from_pretrained("facebook/mms-tts-kdh")
    return _TTS_KDH["tokenizer"], _TTS_KDH["model"]


def get_tts_gej():
    if _TTS_GEJ["model"] is None:
        _TTS_GEJ["tokenizer"] = VitsTokenizer.from_pretrained("facebook/mms-tts-gej")
        _TTS_GEJ["model"] = VitsModel.from_pretrained("facebook/mms-tts-gej")
    return _TTS_GEJ["tokenizer"], _TTS_GEJ["model"]

# The French VITS model used to be loaded here, at import, as ftts_tokenizer /
# ftts_model, next to a generate_fspeech() that nothing called. It was a second
# copy of facebook/mms-tts-fra — get_tts_fr() below already loads and caches the
# same one for the live French path — so every replica paid a HuggingFace
# download at start-up and then held the weights twice. Deleted with the dead
# generator; get_tts_fr() is the single loader.

# Load the model and tokenizer
#tokenizer = AutoTokenizer.from_pretrained("UBC-NLP/toucan-1.2B")
#model = MT5ForConditionalGeneration.from_pretrained("UBC-NLP/toucan-1.2B", torch_dtype=torch.float16, device_map="auto")
#model.eval()

#def translate_to_kabye(text):
#   """
#   Translates text to Kabye using the Toucan-1.2B model.

#   Args:
#     text: The text to translate.

#   Returns:
#     The translated Kabye text.
#   """
#   # Add the language prefix for Kabye translation
#   input_text = f"kbp: {text}"

#   # Tokenize the input text and move to the appropriate device
#   input_ids = tokenizer(input_text, return_tensors="pt", max_length=1024, truncation=True).to(model.device)

#   # Generate the translation
#   with torch.no_grad():
#     generated_ids = model.generate(
#         **input_ids,
#         num_beams=5,
#         max_new_tokens=len(input_text) * 2, # Increase max_new_tokens for longer translations
#         do_sample=True,
#         temperature=0.6,
#         top_p=0.9
#     )

#   # Decode the generated tokens
#   translated_text = tokenizer.batch_decode(generated_ids, skip_special_tokens=True, skip_prompt=True)[0]

#   return translated_text

def generate_mspeech(ewe_text):
    """
    Generates speech from Ewe text and saves it as an audio file.
    """
    tts_tokenizer_, tts_model_ = get_tts_gej()
    inputs = tts_tokenizer_(ewe_text, return_tensors="pt")
    with torch.no_grad():
        output = tts_model_(**inputs).waveform.squeeze().cpu().numpy()
    sf.write("data/output.wav", output, samplerate=16000)
    sound = AudioSegment.from_wav("data/output.wav")
    output_path = "data/output.mp3"
    sound.export(output_path, format="mp3")

    return output_path

def generate_kspeech(ewe_text):
    """
    Generates speech from Ewe text and saves it as an audio file.
    """
    tts_tokenizer_, tts_model_ = get_tts_kdh()
    inputs = tts_tokenizer_(ewe_text, return_tensors="pt")
    with torch.no_grad():
        output = tts_model_(**inputs).waveform.squeeze().cpu().numpy()
    sf.write("data/output.wav", output, samplerate=16000)
    # Convert WAV to MP3 using pydub
    sound = AudioSegment.from_wav("data/output.wav")
    output_path = "data/output.mp3"
    sound.export(output_path, format="mp3")

    return output_path

def identify_language(audio_file):
    """
    Identify the language of a given audio file.

    Args:
        audio_file (str): Path to the audio file.

    Returns:
        str: Identified language label (e.g., 'english' or 'french').
    """
    # Load the audio file
    import torchaudio
    signal, rate = torchaudio.load(audio_file)

    # Perform language identification
    prediction = get_slid_model().classify_batch(signal)

    # Extract the language label
    language = prediction[3][0]  # The predicted language label
    return language

# # Example Usage
# audio_path = "/content/Voices006.wav"
# language = identify_language(audio_path)
# if language == 'en':
#     print("The language of the audio is English.")
# elif language == 'fr':
#     print("The language of the audio is French.")
# else:
#     print(f"Unidentified language: {language}")

# lang = detect(text)
# possible_langs = detect_langs(text)  # returns list of (language: probability)
# print(f"Text: {text}")
# print(f"Detected language: {lang}")
# print(f"Possible languages: {possible_langs}")
# print("-----------")


def transcribe_audio(audio_file, language):
    """
    Transcribes audio using the appropriate model based on the specified language.

    Args:
        audio_file (str): Path to the audio file.
        language (str): Language of the audio ("en" for English, "fr" for French).

    Returns:
        str: The transcribed text.
    """

    if language == "en":
        transcription = get_asr_english()(audio_file)
    elif language == "fr":
        transcription = get_asr_english()(audio_file)
    else:
        return "Unsupported language. Please specify 'en' for English or 'fr' for French."

    return transcription["text"]

# Example usage:
# audio_file_path = "/content/drive/Shareddrives/Vocie conversion/wav/Voices007.wav" # Replace with the actual path to your audio file.
# language = "fr"  # Change to "en" for English transcription

# transcription = transcribe_audio(audio_file_path, language)
# print(f"Transcription: {transcription}")
def translate_text(text: str, target_language_code: str = "fr", source_language_code=  "ee") -> str:
    """
    Translates text from source language to target language using Google Cloud Translation.
    """
    client = translate_v3.TranslationServiceClient()
    parent = f"projects/{PROJECT_ID}/locations/global"
    response = client.translate_text(
        contents=[text],
        target_language_code=target_language_code,
        parent=parent,
        mime_type="text/plain",
        source_language_code=source_language_code,  # Assuming 'ee' is Ewe
    )

    translated_text = response.translations[0].translated_text

    return translated_text


def translate_text_safe(text: str, target_language_code: str = "fr", source_language_code: str = "ee") -> str | None:
    """Best-effort translation. Returns None instead of raising.

    Google Cloud Translation needs Application Default Credentials, which the
    container does not carry: every call raises DefaultCredentialsError. That
    exception used to abort process_audio_message before any reply was sent, so
    a voice note produced complete silence. Translation is an enhancement here,
    never a reason to drop the user's message.
    """
    if not text or not text.strip():
        return None
    try:
        return translate_text(text, target_language_code, source_language_code)
    except Exception as exc:
        logging.warning(
            f"Translation {source_language_code}->{target_language_code} unavailable, "
            f"falling back to the untranslated text: {exc}"
        )
        return None

def etranslate_text(text_to_translate):
    """
    Translates text using the specified API endpoint.

    Args:
        text_to_translate (str): The text to be translated.

    Returns:
        str: The translated text, or an error message if the translation fails.
    """
    api_url = "YOUR_TRANSLATION_API_LINK"
    payload = {"text": text_to_translate}
    json_payload = json.dumps(payload)
    headers = {"Content-Type": "application/json"}

    try:
        response = requests.post(api_url, data=json_payload, headers=headers)

        if response.status_code == 200:
            translation_result = response.json()
            return translation_result.get("translation", "Translation key not found in response.")
        else:
            return f"Error: API request failed with status code {response.status_code}. Response: {response.text}"

    except requests.exceptions.RequestException as e:
        return f"Error: An error occurred during the API request: {e}"
    except json.JSONDecodeError:
        return f"Error: Could not decode JSON response. Response: {response.text}"


def mtranslate_text(text_to_translate):
    """
    Translates text using the specified API endpoint.

    Args:
        text_to_translate (str): The text to be translated.

    Returns:
        str: The translated text, or an error message if the translation fails.
    """
    api_url = "YOUR_TRANSLATION_API_LINK"
    payload = {"text": text_to_translate}
    json_payload = json.dumps(payload)
    headers = {"Content-Type": "application/json"}

    try:
        response = requests.post(api_url, data=json_payload, headers=headers)

        if response.status_code == 200:
            translation_result = response.json()
            return translation_result.get("translation", "Translation key not found in response.")
        else:
            return f"Error: API request failed with status code {response.status_code}. Response: {response.text}"

    except requests.exceptions.RequestException as e:
        return f"Error: An error occurred during the API request: {e}"
    except json.JSONDecodeError:
        return f"Error: Could not decode JSON response. Response: {response.text}"

def ktranslate_text(text_to_translate):
    """
    Translates text using the specified API endpoint.

    Args:
        text_to_translate (str): The text to be translated.

    Returns:
        str: The translated text, or an error message if the translation fails.
    """
    api_url = "YOUR_TRANSLATION_API_LINK"
    payload = {"text": text_to_translate}
    json_payload = json.dumps(payload)
    headers = {"Content-Type": "application/json"}

    try:
        response = requests.post(api_url, data=json_payload, headers=headers)

        if response.status_code == 200:
            translation_result = response.json()
            return translation_result.get("translation", "Translation key not found in response.")
        else:
            return f"Error: API request failed with status code {response.status_code}. Response: {response.text}"

    except requests.exceptions.RequestException as e:
        return f"Error: An error occurred during the API request: {e}"
    except json.JSONDecodeError:
        return f"Error: Could not decode JSON response. Response: {response.text}"




def log_http_response(response):
    """
    Logs HTTP response details.
    """
    logging.info(f"Status: {response.status_code}")
    logging.info(f"Content-type: {response.headers.get('content-type')}")

def show_message_answer(recipient: str, text: str) -> str:
    """
    Constructs a JSON payload for sending a text message via WhatsApp.
    """
    return json.dumps({
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": recipient,
        "type": "text",
        "text": {"preview_url": False, "body": text},
    })


def generate_speech(ewe_text: str) -> str:
    """
    Generates speech from Ewe text and saves it as an audio file.
    """
    tts_tokenizer_, tts_model_ = get_tts_ewe()
    inputs = tts_tokenizer_(ewe_text, return_tensors="pt")
    with torch.no_grad():
        output = tts_model_(**inputs).waveform.squeeze().cpu().numpy()
    sf.write("data/output.wav", output, samplerate=16000)
    # Convert WAV to MP3 using pydub
    sound = AudioSegment.from_wav("data/output.wav")
    output_path = "data/output.mp3"
    sound.export(output_path, format="mp3")

    return output_path


_TTS_FR = {"tokenizer": None, "model": None}

# MMS-VITS speaks fast and flat at its defaults, which is what makes the voice
# replies sound rushed and hard to follow. speaking_rate below 1.0 slows the
# delivery down; noise_scale controls how much prosodic variation is sampled.
TTS_SPEAKING_RATE = float(os.getenv("TTS_SPEAKING_RATE", "0.85"))
TTS_NOISE_SCALE = float(os.getenv("TTS_NOISE_SCALE", "0.667"))


def get_tts_fr():
    if _TTS_FR["tokenizer"] is None:
        _TTS_FR["tokenizer"] = VitsTokenizer.from_pretrained("facebook/mms-tts-fra")
        model = VitsModel.from_pretrained("facebook/mms-tts-fra")
        model.speaking_rate = TTS_SPEAKING_RATE
        model.noise_scale = TTS_NOISE_SCALE
        model.eval()
        _TTS_FR["model"] = model
    return _TTS_FR["tokenizer"], _TTS_FR["model"]

# VITS degrades badly past a few hundred characters and the resulting voice note
# is too long to be useful on WhatsApp. Longer answers stay text-only.
TTS_MAX_CHARS = int(os.getenv("TTS_MAX_CHARS", "600"))

# Emoji and markdown are vocalised as noise by VITS, which is part of why the
# voice replies came out garbled. Strip them and normalise the spacing.
_EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF←-⇿⬀-⯿️‍]+"
)
_MARKDOWN_RE = re.compile(r"[*_`#>|~\[\]]+")


def _clean_for_tts(text: str) -> str:
    """Reduces a chat answer to something a speech model can read aloud."""
    text = (text or "").strip()
    if not text:
        return ""
    text = _EMOJI_RE.sub(" ", text)
    text = _MARKDOWN_RE.sub(" ", text)
    text = re.sub(r"https?://\S+", " ", text)
    # Give the model a real pause instead of a bullet glyph.
    text = re.sub(r"^\s*[-•]\s*", ". ", text, flags=re.MULTILINE)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r"([,.;:])\1+", r"\1", text)
    return text.strip(" .,;:").strip()


# --- Voice of the assistant --------------------------------------------------
# HLlama addresses women and girls about intimate health, so the voice she
# answers in matters. facebook/mms-tts-fra is a single-speaker MALE model with
# no female variant, which is why the voice notes came back in a man's voice.
#
# Piper's fr_FR-siwis-medium is a female French voice, and it also synthesises
# several times faster than VITS on CPU. It is the default; MMS stays as the
# fallback so a missing Piper install degrades instead of breaking the reply.
#   TTS_PROVIDER=elevenlabs | piper (default) | mms
#   PIPER_VOICE      voice name, must exist under PIPER_VOICE_DIR
#   PIPER_LENGTH_SCALE  >1 speaks slower (1.15 reads calmly, which is what the
#                       health context wants)
TTS_PROVIDER = os.getenv("TTS_PROVIDER", "piper").strip().lower()
PIPER_VOICE = os.getenv("PIPER_VOICE", "fr_FR-siwis-medium")
PIPER_VOICE_DIR = os.getenv("PIPER_VOICE_DIR", "/opt/piper-voices")
PIPER_LENGTH_SCALE = os.getenv("PIPER_LENGTH_SCALE", "1.15")


def _piper_model_path() -> str | None:
    """Returns the configured Piper voice file, or None when it is absent."""
    candidate = os.path.join(PIPER_VOICE_DIR, f"{PIPER_VOICE}.onnx")
    return candidate if os.path.isfile(candidate) else None


def _synthesize_piper(text: str, wav_path: str) -> bool:
    """Synthesises `text` with Piper. Returns False if Piper is unusable.

    The CLI is used rather than the Python API because the latter renamed its
    synthesis entry point between releases, while the command line has stayed
    stable.
    """
    model_path = _piper_model_path()
    if not model_path:
        logging.warning(
            f"Piper voice '{PIPER_VOICE}' not found in {PIPER_VOICE_DIR}, falling back to MMS"
        )
        return False
    try:
        result = subprocess.run(
            [sys.executable, "-m", "piper",
             "--model", model_path,
             "--length_scale", PIPER_LENGTH_SCALE,
             "--output_file", wav_path],
            input=text.encode("utf-8"),
            capture_output=True,
            timeout=120,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        logging.warning(f"Piper synthesis failed, falling back to MMS: {exc}")
        return False
    if result.returncode != 0 or not os.path.isfile(wav_path):
        logging.warning(
            f"Piper exited {result.returncode}, falling back to MMS: "
            f"{result.stderr.decode('utf-8', 'replace')[:300]}"
        )
        return False
    return True


def _synthesize_mms(text: str, wav_path: str) -> bool:
    """Synthesises `text` with the MMS VITS model (male voice)."""
    tts_tokenizer_, tts_model_ = get_tts_fr()
    inputs = tts_tokenizer_(text, return_tensors="pt")
    with torch.no_grad():
        output = tts_model_(**inputs).waveform.squeeze().cpu().numpy()
    sf.write(wav_path, output, samplerate=tts_model_.config.sampling_rate)
    return True


def generate_speech_fr(text: str, tag: str | None = None) -> str | None:
    """Renders a French voice note for `text`, or None when it should stay text.

    `tag` keeps the output paths unique: the webhook handles each message on its
    own thread and up to 10 replicas share the layout, so a fixed
    data/tts_output.wav meant two simultaneous voice notes overwrote each
    other's audio and one user received the other's reply.
    """
    text = _clean_for_tts(text)
    if not text:
        return None
    if len(text) > TTS_MAX_CHARS:
        logging.info(f"Skipping TTS: reply is {len(text)} chars (limit {TTS_MAX_CHARS})")
        return None

    os.makedirs("data", exist_ok=True)
    suffix = tag or uuid.uuid4().hex
    wav_path = f"data/tts_{suffix}.wav"
    mp3_path = f"data/tts_{suffix}.mp3"

    try:
        if TTS_PROVIDER == "elevenlabs" and synthesize_elevenlabs(text, mp3_path):
            return mp3_path

        rendered = False
        if TTS_PROVIDER in {"elevenlabs", "piper"}:
            rendered = _synthesize_piper(text, wav_path)
        if not rendered:
            rendered = _synthesize_mms(text, wav_path)
        if not rendered:
            return None

        # WhatsApp needs an encoded audio payload, not raw PCM.
        AudioSegment.from_wav(wav_path).export(mp3_path, format="mp3")
        return mp3_path
    finally:
        _safe_unlink(wav_path)


def _safe_unlink(path: str | None) -> None:
    """Removes a scratch file, ignoring the case where it is already gone."""
    if not path:
        return
    try:
        os.remove(path)
    except OSError:
        pass


def transcribe_speech(audio_path: str) -> str:
    """
    Transcribes speech from an audio file using the ASR pipeline.
    """
    y, sr = librosa.load(audio_path, sr=None)
    y = y.astype(np.float32)
    y /= np.max(np.abs(y))
    transcription = get_asr_ewe()({"sampling_rate": sr, "raw": y})["text"]
    return transcription.replace("<|startoftranscript|><|yo|><|transcribe|><|notimestamps|>", "").strip()

def process_ee_audio_prompt(audio_path: str) -> str:
    """
    Processes an audio prompt in Ewe, transcribes it, and translates it.
    """
    ee_text = transcribe_speech(audio_path)
    prompt = translate_text(ee_text, "fr")
    return prompt

def get_media_url(media_id, access_token):
    url = f"https://graph.facebook.com/v21.0/{media_id}/"
    headers = {
        "Authorization": f"Bearer {access_token}"
    }
    response = requests.get(url, headers=headers, timeout=15)
    response.raise_for_status()
    media_info = response.json()
    media_url = media_info.get("url")
    if not media_url:
        raise ValueError("No URL in media response")
    logging.info("Media URL retrieved")
    return media_url

def download_media(media_url, access_token, output_file_path):
    headers = {
        "Authorization": f"Bearer {access_token}"
    }
    os.makedirs(os.path.dirname(output_file_path) or ".", exist_ok=True)
    response = requests.get(media_url, headers=headers, stream=True, timeout=(10, 60))
    response.raise_for_status()
    with open(output_file_path, 'wb') as media_file:
        for chunk in response.iter_content(chunk_size=8192):
            media_file.write(chunk)
    file_size = os.path.getsize(output_file_path)
    logging.info(f"Media downloaded to {output_file_path} ({file_size} bytes)")
    if file_size == 0:
        raise IOError(f"Downloaded file is empty: {output_file_path}")

def get_media_id(audio_file_path: str) -> dict | None:
    """
    Uploads an audio file to WhatsApp and retrieves the media ID.

    Returns None when the upload fails. The previous version only assigned
    `media_response` on the success path, so any failure raised
    UnboundLocalError from the return statement and hid the actual cause.
    """
    url = f"https://graph.facebook.com/{current_app.config['VERSION']}/{current_app.config['PHONE_NUMBER_ID']}/media"
    headers = {
        "Authorization": f"Bearer {current_app.config['ACCESS_TOKEN']}",
    }
    data = {
        "type": "audio/mpeg",
        "messaging_product": "whatsapp",
    }

    try:
        with open(audio_file_path, 'rb') as file:
            files = {'file': ('file.mp3', file, 'audio/mpeg')}
            response = requests.post(url, headers=headers, data=data, files=files, timeout=60)
            response.raise_for_status()
            media_response = response.json()
            logging.info(f"Media uploaded, id={media_response.get('id')}")
            return media_response
    except requests.exceptions.HTTPError as http_err:
        logging.error(f"Media upload HTTP error: {http_err}")
        status = http_err.response.status_code if http_err.response is not None else "n/a"
        logging.error("Media upload failed with status %s", status)
    except Exception as err:
        logging.error(f"Media upload failed: {err}")
    return None


def get_location_message_input(recipient: str, latitude: float, longitude: float, name: str, address: str) -> str:
    """
    Constructs a JSON payload for sending a location message via WhatsApp.
    """
    return json.dumps({
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": recipient,
        "type": "location",
        "location": {
            "latitude": latitude,
            "longitude": longitude,
            "name": name,
            "address": address
        }
    })



def show_media_response(media_response: dict) -> str:
    """
    Constructs a JSON payload for sending an audio message via WhatsApp.
    """
    return json.dumps({
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": current_app.config['RECIPIENT_WAID'],
        "type": "audio",
        "audio": {
            "id": media_response.get("id", "")
        }
    })

def send_location_request(recipient: str) -> str:
    return json.dumps({
"messaging_product": "whatsapp",
"recipient_type": "individual",
"type": "interactive",
"to": recipient,
"interactive": {
    "type": "location_request_message",
    "body": {
    "text": "Afin de répondre à votre question, merci de nous envoyer votre localisation",
    },
    "action": {
    "name": "send_location",
    }
}
})

def get_audio_message_input(recipient: str, media_response: dict) -> str:
    """
    Constructs a JSON payload for sending an audio message via WhatsApp.
    """
    return json.dumps({
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": recipient,
        "type": "audio",
        "audio": {
            "id": media_response["id"]
        }
    })


def generate_response(
    user_input: str,
    wa_id: str = "",
    context: str = "",
    preferred_name: str | None = None,
) -> str:
    """
    Generates a response using Azure OpenAI.

    `context` is the conversation memory. It is passed as its own system turn
    rather than appended to the user's message: glued onto the user text, the
    past "Q: ... | R: ..." lines read as part of what the person just said, and
    the model would restate them before answering.
    """
    from app.services.conversation_response import generate_structured_response

    emergency_response = emergency_contact_payload(user_input, wa_id)
    if emergency_response is not None:
        # She was offered the nearest service: her next message may be the
        # answer.
        emergency_offer.set(pseudo_id_for(wa_id))
        return emergency_response

    file_path = os.path.join(os.path.dirname(__file__), 'system_prompt.txt')
    return generate_structured_response(
        client, deployment_name, user_input, load_text_from_file(file_path),
        build_current_time_note(wa_id), context=context, preferred_name=preferred_name,
        notes=(
            build_reminder_notes(wa_id)
            + build_knowledge_notes(user_input)
            + build_health_fact_notes(wa_id)
        ),
    )


def build_reminder_notes(wa_id: str) -> tuple[str, ...]:
    """The trusted notes about her own reminders, empty when they are unknown.

    Without this the model held no reminder data at all and answered "j'ai quoi
    de pr�vu ?" from imagination. An unreachable backend yields no note rather
    than a note claiming she has none.
    """
    note = memory_notes.reminder_note(snapshot(wa_id), zone_name_for_wa_id(wa_id))
    return (note,) if note else ()


def build_health_fact_notes(wa_id: str) -> tuple[str, ...]:
    """The health facts she declared, with her agreement.

    Without them the assistant asks the same questions again and again, and she
    has to answer them every time.
    """
    note = health_facts.facts_note(health_facts.fetch_facts(pseudo_id_for(wa_id)))
    return (note,) if note else ()


def build_knowledge_notes(user_input: str) -> tuple[str, ...]:
    """The passages of the documentary base about her question.

    The model used to invent figures - a dosage, a price, a duration - because
    it had no document to quote. The passages are the only source it may use,
    and there is no note at all when the base has nothing about her question.
    """
    note = knowledge.knowledge_note(knowledge.search_extracts(user_input))
    return (note,) if note else ()



def build_current_time_note(wa_id: str = "") -> str:
    """Builds the system note giving the model the real current local time."""
    zone_name = zone_name_for_wa_id(wa_id)
    now_local = datetime.now(zone(zone_name))
    return (
        "IMPORTANT: The current real date and time is "
        f"{now_local.strftime('%Y-%m-%dT%H:%M:%S')} in the user's local timezone "
        f"({zone_name}). The user speaks in their local time. "
        "Always compute scheduled_at relative to this exact local date and time, "
        "never from your own training data. Output scheduled_at as a naive "
        "YYYY-MM-DDTHH:MM:SS value in the user's local timezone."
    )


def load_text_from_file(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            text = file.read()
        return text
    except FileNotFoundError:
        logging.error("System prompt file was not found")
        return None
    except Exception as e:
        logging.error("System prompt could not be read: %s", type(e).__name__)
        return None



def detect_language(text):
    """
    Detect the main language of the input text.
    Returns either 'en' or 'fr' (defaults to 'en' if detection is unclear).
    """
    try:
        lang = detect(text)
        if lang.startswith('fr'):
            return 'fr'
        else:
            return 'en'
    except:
        return 'en'  # fallback to English

def parse_date_str(date_str, lang='en'):
    """
    Try to parse the given date string using dateparser with an appropriate
    date order (to handle ISO, DMY, MDY, etc.). Returns a datetime object or None.
    """
    # If it looks like YYYY-MM-DD or YYYY/MM/DD, we can assume YMD order:
    #    e.g., 2025-01-14 or 2025/01/14
    # If you want to handle more patterns, adapt this logic or add more tries.
    iso_like = re.match(r'^\d{4}[-/]\d{1,2}[-/]\d{1,2}$', date_str)

    if iso_like:
        parsed = dateparser.parse(
            date_str,
            languages=[lang],
            settings={
                'DATE_ORDER': 'YMD',          # Force year–month–day
                'PREFER_DAY_OF_MONTH': 'first'
            }
        )
        return parsed

    # Otherwise, try multiple date orders to see if we get a valid parse
    for date_order in ['DMY', 'MDY', 'YMD']:
        parsed = dateparser.parse(
            date_str,
            languages=[lang],
            settings={
                'DATE_ORDER': date_order,
                'PREFER_DAY_OF_MONTH': 'first'
            }
        )
        if parsed:
            return parsed

    # If all fails, return None
    return None

# The only categories the backend's /api/nearest/{category} route accepts. Any
# other value is rejected with 400 INVALID_PLACE_CATEGORY before a search runs.
PLACE_CATEGORIES = ("pharmacy", "hospital", "clinic")
DEFAULT_PLACE_CATEGORY = "pharmacy"

# Checked in order, first match wins. Pharmacy comes first so that "pharmacie de
# l'hôpital" still resolves to what the person is actually looking for.
_PLACE_CATEGORY_KEYWORDS = (
    ("pharmacy", re.compile(r"pharma|medicament|drug")),
    ("hospital", re.compile(r"hopital|hospital|\bchu\b|\bchr\b|urgence|emergency")),
    ("clinic", re.compile(
        r"clinique|clinic|centre (de )?sante|centre medical|dispensaire|cabinet"
        r"|medecin|docteur|doctor|gyneco|sage.femme|\bcms\b|\bcsps\b|\busp\b"
    )),
)


def normalize_place_category(raw: str | None) -> str:
    """Maps whatever the model put in request_content to a backend category.

    The model is told to emit pharmacy, hospital or clinic, but in production it
    writes the user's own words: "pharmacie", "clinique", "centre de santé",
    "pharmacies proches de Agbalepedo". Every one of those reached the backend
    verbatim and came back 400, so no nearest-place search had succeeded at
    all. Accept free French or English text and fall back to a pharmacy, the
    most common request, rather than failing.
    """
    text = unidecode(str(raw or "")).lower().strip()
    if text in PLACE_CATEGORIES:
        return text
    for category, pattern in _PLACE_CATEGORY_KEYWORDS:
        if pattern.search(text):
            return category
    return DEFAULT_PLACE_CATEGORY


def get_nearest(category: str, latitude: float, longitude: float, radius_km: float):
    """
    Makes a GET request to the nearest endpoint with the given parameters.

    Args:
        category (str): The category of the search, normalized before use.
        latitude (float): The latitude coordinate.
        longitude (float): The longitude coordinate.
        radius_km (float): The search radius in kilometers.

    Returns:
        dict: The JSON response from the server, or an error envelope whose
        "status" mirrors the HTTP status (503 when the backend is unreachable).
    """
    base_url = backend_base_url()
    category = normalize_place_category(category)
    url = f"{base_url}/api/nearest/{category}"
    params = {"latitude": latitude, "longitude": longitude, "radius_km": radius_km}

    # Without a timeout a stalled backend held the webhook thread forever, and
    # a connection error raised straight out of process_location_message, whose
    # handler only catches malformed payloads, so the user got no reply at all.
    try:
        response = requests.get(
            url, params=params, headers=backend_headers(), timeout=15
        )
    except requests.RequestException as exc:
        logging.error("Nearest-place request failed: %s", type(exc).__name__)
        return {"status": 503, "error": True, "message": "REQUEST_FAILED", "data": None}

    if response.status_code == 200:
        return response.json()
    else:
        return {
            "status": response.status_code,
            "error": True,
            "message": "REQUEST_FAILED",
            "data": None,
            "meta": {},
        }


_MAPS_LINK_RE = re.compile(
    r"https?://(?:maps\.app\.goo\.gl/[A-Za-z0-9_-]+|(?:www\.|maps\.)?google\.[a-z.]{2,}/maps?[^\s]*|goo\.gl/maps/[^\s]*)",
    re.IGNORECASE,
)


def _resolve_google_maps_url(url: str) -> str:
    """Suits the Google Maps redirect chain and unwraps the consent wrapper."""
    try:
        resp = requests.get(
            url,
            allow_redirects=True,
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        )
        final = resp.url
    except requests.RequestException as exc:
        logging.warning("Could not resolve maps URL: %s", type(exc).__name__)
        return url
    match = re.search(r"[?&]continue=([^&]+)", final)
    if match:
        unwrapped = requests.utils.unquote(match.group(1))
        if "google.com/maps" in unwrapped:
            return unwrapped
    return final


def _coordinates_from_url(url: str):
    """Returns (lat, lng) when the Google Maps URL embeds them, else None."""
    patterns = [
        r"!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)",
        r"@(-?\d+\.\d+),(-?\d+\.\d+)",
        r"[?&]ll=(-?\d+\.\d+),(-?\d+\.\d+)",
        r"[?&]q=(-?\d+\.\d+),(-?\d+\.\d+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return float(match.group(1)), float(match.group(2))
    return None


def _place_query_from_url(url: str):
    """Extracts a human-readable place query from a Google Maps URL, else None."""
    match = re.search(r"[?&]q=([^&]+)", url)
    if match:
        query = requests.utils.unquote(match.group(1)).replace("+", " ").strip()
        if query and not re.fullmatch(r"-?\d+\.\d+,\s*-?\d+\.\d+", query):
            return query
    match = re.search(r"/(?:place|search)/([^/@?]+)", url)
    if match:
        query = requests.utils.unquote(match.group(1)).replace("+", " ").strip()
        if query:
            return query
    return None


def geocode_place(query: str):
    """Asks the backend to geocode a place name into coordinates."""
    base_url = backend_base_url()
    try:
        response = requests.get(
            f"{base_url}/api/geocode",
            params={"q": query},
            headers=backend_headers(),
            timeout=15,
        )
        if response.status_code == 200:
            payload = response.json()
            data = payload.get("data") if isinstance(payload, dict) else None
            if isinstance(data, dict) and data.get("latitude") is not None:
                return data
    except requests.RequestException as exc:
        logging.error("geocode_place failed: %s", type(exc).__name__)
    return None


def is_maps_link(text: str) -> bool:
    """True quand le texte contient un lien Google Maps partagé."""
    return _MAPS_LINK_RE.search(text) is not None


def extract_maps_location(text: str):
    """Returns a synthesized location message from a Google Maps link in text, else None."""
    match = _MAPS_LINK_RE.search(text)
    if not match:
        return None
    resolved = _resolve_google_maps_url(match.group(0))
    coords = _coordinates_from_url(resolved)
    if coords:
        lat, lng = coords
        name = _place_query_from_url(resolved) or "Position partagée"
    else:
        place_query = _place_query_from_url(resolved)
        if not place_query:
            return None
        geo = geocode_place(place_query)
        if not geo:
            return None
        lat, lng = geo["latitude"], geo["longitude"]
        name = geo.get("address") or place_query
    return {"location": {"latitude": lat, "longitude": lng, "name": name}}


_backend_headers = backend_headers


def fetch_exchange_history(wa_id, limit=8):
    """Retrieves the last `limit` exchanges for a user via their pseudo_id."""
    from app.utils.anonymity import pseudo_id_for
    pseudo_id = pseudo_id_for(wa_id)
    base_url = os.getenv("NEAREST_API_URL", "")
    url = f"{base_url}/api/bot/users/{pseudo_id}/history"
    try:
        response = requests.get(url, params={"limit": limit}, headers=_backend_headers(), timeout=10)
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, dict) and not data.get("error"):
                return data.get("data", []) or []
        return []
    except requests.RequestException as e:
        logging.error("fetch_exchange_history failed: %s", type(e).__name__)
        return []


def search_exchange_history(wa_id, query, top_k=3):
    """Semantically searches past exchanges for a user via their pseudo_id."""
    from app.utils.anonymity import pseudo_id_for
    pseudo_id = pseudo_id_for(wa_id)
    base_url = os.getenv("NEAREST_API_URL", "")
    url = f"{base_url}/api/bot/users/{pseudo_id}/search"
    try:
        response = requests.get(url, params={"q": query, "top_k": top_k}, headers=_backend_headers(), timeout=10)
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, dict) and not data.get("error"):
                return data.get("data", []) or []
        return []
    except requests.RequestException as e:
        logging.error("search_exchange_history failed: %s", type(e).__name__)
        return []


def build_context_memory(wa_id, user_input, recent_limit=8, top_k=3, max_chars=1500):
    """
    Builds a bounded, token-efficient memory snippet for the LLM prompt.

    Combines the most recent exchanges (sliding window) with semantic matches
    for the current input (RAG), deduplicates them, and truncates everything
    to `max_chars`. Returns an empty string when there is no memory (or the
    backend is unreachable), so prompt building degrades gracefully.

    Each line carries the moment of the exchange in her local time: the merge
    of "recent" and "semantically close" has no chronology of its own, so
    without a stamp the model could not tell last night from last month.
    """
    recent = fetch_exchange_history(wa_id, limit=recent_limit)
    matches = search_exchange_history(wa_id, user_input, top_k=top_k) if user_input else []

    merged = {}
    for item in matches + recent:
        key = item.get("id") if isinstance(item, dict) else str(item)
        if key and key not in merged:
            merged[key] = item

    return memory_notes.history_note(
        merged.values(),
        datetime.now(timezone.utc),
        zone_name_for_wa_id(wa_id),
        max_chars=max_chars,
    )


def push_exchange_to_backend(wa_id, question, response=None, request_type=None):
    """Persists a bot exchange (question + response) to the backend.

    The user is identified by their deterministic `pseudo_id`; the raw
    `wa_id` is forwarded once so the backend can store the (encrypted)
    number it needs for timezone resolution and reminder delivery.
    """
    from app.utils.anonymity import pseudo_id_for
    pseudo_id = pseudo_id_for(wa_id)
    base_url = os.getenv("NEAREST_API_URL", "")
    url = f"{base_url}/api/bot/exchanges"
    payload = {"pseudo_id": pseudo_id, "telnumber": wa_id, "question": question, "response": response, "request_type": request_type}
    try:
        response = requests.post(url, json=payload, headers=_backend_headers(), timeout=10)
        if response.status_code >= 400:
            logging.error("push_exchange_to_backend failed: %s", response.status_code)
        else:
            schedule_feedback(wa_id)
        return response.status_code
    except requests.RequestException as e:
        logging.error("push_exchange_to_backend failed: %s", type(e).__name__)
        return None


def cancel_pending_reminders_for_user(wa_id):
    """Cancels all pending reminders of a user via the backend bot endpoint."""
    from app.utils.anonymity import pseudo_id_for
    pseudo_id = pseudo_id_for(wa_id)
    base_url = os.getenv("NEAREST_API_URL", "")
    url = f"{base_url}/api/bot/reminders/cancel-by-pseudo-id"
    try:
        response = requests.post(url, params={"pseudo_id": pseudo_id}, headers=_backend_headers(), timeout=10)
        if response.status_code == 200:
            body = response.json()
            return body.get("data") if isinstance(body, dict) else []
        logging.error("cancel_pending_reminders failed: %s", response.status_code)
    except requests.RequestException as e:
        logging.error("cancel_pending_reminders failed: %s", type(e).__name__)
    return []


_REMINDER_OPTOUTS = {
    "stop",
    "arret",
    "arrêt",
    "cancel",
    "annule",
    "annuler",
    "stop rappels",
    "annuler les rappels",
    "arrete les rappels",
    "arrête les rappels",
}


def is_reminder_optout(text):
    """True when the user asks to cancel their scheduled reminders."""
    cleaned = text.strip().strip(".,!?").lower()
    return cleaned in _REMINDER_OPTOUTS


def convert_date_to_text(date_obj, lang='en'):
    """
    Given a datetime object, convert it into a textual date string
    in either English or French style.
    """
    day = date_obj.day
    month = date_obj.month
    year = date_obj.year

    # Convert the year to words using num2words
    year_in_words = num2words(year, lang=lang)

    if lang == 'fr':
        # -- French style: "le quatorze janvier deux mille vingt-cinq"
        # or "le premier janvier deux mille vingt-cinq" for day=1

        # Spell out the day in French: "un", "deux", "trois", "quatorze", etc.
        # For day=1, French often says "1er" or "premier" in text form.
        if day == 1:
            day_str = "premier"
        else:
            # "quatorze" for 14, "deux" for 2, etc.
            day_str = num2words(day, lang='fr')

        # Map month to French month names
        french_months = [
            "janvier", "février", "mars", "avril", "mai", "juin",
            "juillet", "août", "septembre", "octobre", "novembre", "décembre"
        ]
        month_name = french_months[month - 1]

        return f"le {day_str} {month_name} {year_in_words}"

    else:
        # -- English style: "January fourteenth, two thousand twenty-five"
        # day in ordinal words: "first", "second", "fourteenth", etc.
        day_ordinal = num2words(day, ordinal=True, lang='en')

        english_months = [
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December"
        ]
        month_name = english_months[month - 1]

        return f"{month_name} {day_ordinal}, {year_in_words}"

def replace_date_match(match, lang='en'):
    """
    Regex callback to parse a matched date string and return its textual form
    in the specified language.
    """
    date_str = match.group(0)
    parsed_date = parse_date_str(date_str, lang=lang)
    if parsed_date:
        return convert_date_to_text(parsed_date, lang=lang)
    else:
        # If parsing fails, return the original text
        return date_str

def replace_number_match(match, lang='en'):
    """
    Regex callback to convert a matched standalone number into words
    in the specified language.
    """
    number_str = match.group(0)
    try:
        return num2words(int(number_str), lang=lang)
    except ValueError:
        return number_str  # If parsing fails, return original

def transform_text(text):
    """
    1. Detect whether the text is primarily French or English.
    2. Replace recognized dates with textual dates in that language.
    3. Replace standalone numbers with words in that language.
    """
    lang = detect_language(text)
    # 1) Replace date occurrences
    date_pattern = r'\b(?:\d{1,4}[/-]\d{1,2}[/-]\d{1,4})\b'
    text_with_dates = re.sub(
        date_pattern,
        lambda m: replace_date_match(m, lang=lang),
        text
    )

    # 2) Replace standalone numbers
    number_pattern = r'\b\d+\b'
    transformed_text = re.sub(
        number_pattern,
        lambda m: replace_number_match(m, lang=lang),
        text_with_dates
    )
    return transformed_text

#Optional: Function to change pitch
def change_pitch(audio_path: str, semitones: float) -> str:
    """
    Changes the pitch of an audio file (supports various formats).
    """
    try:
        sound = AudioSegment.from_file(audio_path)
    except Exception:
        wav_path = "temp.wav"
        try:
            subprocess.run(["ffmpeg", "-i", audio_path, wav_path], check=True)
            sound = AudioSegment.from_wav(wav_path)
        except Exception as e:
            logging.error(f"Error loading or converting audio: {e}")
            return None

    new_sample_rate = int(sound.frame_rate * (2 ** (semitones / 12)))
    new_sound = sound._spawn(sound.raw_data, overrides={'frame_rate': new_sample_rate})
    output_path = "output_pitched.wav"
    new_sound.export(output_path, format="wav")
    sound = AudioSegment.from_wav("output_pitched.wav")
    output_path = "data/output_pitched.mp3"
    sound.export(output_path, format="mp3")

    if os.path.exists("temp.wav"):
        os.remove("temp.wav")


    return output_path


# ——— Patterns for numbers & isolated Roman numerals ———
arabic_pattern = re.compile(r"\b\d+\b")

# List of supported languages
SUPPORTED_LANGUAGES = [
    # Languages from your dataset
    "BASSAR", "EN", "EWE", "FON", "FRENCH", "KABYE", "KONKONBA", "LINGUALA", "MINA", "MOBA", "TEM",
    
    # Additional languages you requested
    "ADJA", "NAWDEM", "LAMBA",
    
    # Languages covered by ChatGPT (based on available sources)
    "ALBANIAN", "AMHARIC", "ARABIC", "ARMENIAN", "AWADHI", "AZERBAIJANI", "BASHKIR", "BASQUE",
    "BELARUSIAN", "BENGALI", "BHOJPURI", "BOSNIAN", "BRAZILIAN PORTUGUESE", "BULGARIAN", "BURMESE",
    "CANTONESE", "CATALAN", "CHHATTISGARHI", "CHINESE", "CROATIAN", "CZECH", "DANISH", "DOGRI",
    "DUTCH", "ENGLISH", "ESTONIAN", "FAROESE", "FINNISH", "FRENCH", "GALICIAN", "GEORGIAN",
    "GERMAN", "GREEK", "GUJARATI", "HARYANVI", "HINDI", "HUNGARIAN", "ICELANDIC", "INDONESIAN",
    "IRISH", "ITALIAN", "JAPANESE", "JAVANESE", "KANNADA", "KASHMIRI", "KAZAKH", "KONKANI",
    "KOREAN", "KURDISH", "KYRGYZ", "LAO", "LATVIAN", "LITHUANIAN", "LUXEMBOURGISH", "MACEDONIAN",
    "MALAY", "MALAYALAM", "MALTESE", "MAORI", "MARATHI", "MONGOLIAN", "NEPALI", "NORWEGIAN",
    "ORIYA", "PASHTO", "PERSIAN", "POLISH", "PORTUGUESE", "PUNJABI", "ROMANIAN", "RUSSIAN",
    "SERBIAN", "SINHALA", "SLOVAK", "SLOVENIAN", "SPANISH", "SUNDANESE", "SWAHILI", "SWEDISH",
    "TAMIL", "TELUGU", "THAI", "TURKISH", "UKRAINIAN", "URDU", "UZBEK", "VIETNAMESE", "WELSH",
    "XHOSA", "YIDDISH", "YORUBA", "ZULU"
]

# # only match if the entire token is made of Roman letters,
# # and not embedded inside another word
# roman_pattern = re.compile(r"(?<=\s|^)[MDCLXVI]+(?=\s|$)", re.IGNORECASE)


def post_process_numbers_in_ewe(ewe_text, translate_text_fn):
    """
    In the Ewe text, find any standalone Arabic numbers or isolated
    Roman‐numeral tokens, convert them to French words, translate those
    French words back into Ewe, and substitute them in place.
    """
    def repl_arabic(m):
        french = num2words(int(m.group(0)), lang="fr")
        return translate_text_fn(french, "ee", "fr")

    # def repl_roman(m):
    #     rn = m.group(0).upper()
    #     try:
    #         val = roman.fromRoman(rn)
    #         french = num2words(val, lang="fr")
    #         return translate_text_fn(french, "ee", "fr")
    #     except roman.InvalidRomanNumeralError:
    #         return rn  # leave it alone if it isn’t a valid Roman numeral

    # replace Arabic first, then Roman
    out = arabic_pattern.sub(repl_arabic, ewe_text)
    # out = roman_pattern.sub(repl_roman, out)
    return out


def tts_from_translated_ewe(
    translated_folder,
    audio_folder,
    translate_text_fn,
    tts_model_name="facebook/mms-tts-ewe"
):
    os.makedirs(audio_folder, exist_ok=True)

    # ——— Load TTS pipeline ———
    tokenizer = VitsTokenizer.from_pretrained(tts_model_name)
    model     = VitsModel.from_pretrained(tts_model_name)
    tts       = pipeline("text-to-speech", model=model, tokenizer=tokenizer)

    txt_paths = glob.glob(os.path.join(translated_folder, "*.txt"))
    for path in txt_paths:
        base = os.path.splitext(os.path.basename(path))[0]

        # — read the Ewe text
        with open(path, "r", encoding="utf-8") as f:
            ewe_raw = f.read()

        # — normalize any numbers or isolated Roman numerals
        ewe_norm = post_process_numbers_in_ewe(ewe_raw, translate_text_fn)

        # — split back into sentences for chunked TTS
        sentences = re.split(
            r'(?<!\w\.\w.)(?<![A-Z][a-z]\.)(?<=\.|\?)\s', ewe_norm
        )

        audio_chunks = []
        sr_ref = None

        for sent in sentences:
            sent = sent.strip()
            if not sent:
                continue

            out = tts(sent)
            wav = out.get("wav", out.get("audio"))
            sr  = out.get("sample_rate", out.get("sampling_rate"))

            if sr_ref is None:
                sr_ref = sr
            elif sr != sr_ref:
                raise RuntimeError(f"Sample‐rate mismatch: {sr} vs {sr_ref}")

            audio_chunks.append(wav)

        # — concatenate & write out
        if audio_chunks:
            full = np.concatenate(audio_chunks, axis=0)
            wav_path = os.path.join(audio_folder, f"{base}.wav")
            sf.write(wav_path, full, sr_ref)
            return wav_path

processed_message_ids = set()
processed_audio_ids = set()

def process_whatsapp_message(body: dict):
    """
    Processes incoming WhatsApp messages and responds according to the structured JSON-based request types.
    """
    try:
        message = body["entry"][0]["changes"][0]["value"]["messages"][0]
        wa_id = message["from"]
        message_id = message.get("id")  # Unique identifier for the message

        # Prevent duplicate message processing
        if not _remember_processed(processed_message_ids, message_id):
            logging.info(f"Message with ID {message_id} has already been processed.")
            return

    except (IndexError, KeyError) as e:
        logging.error(f"Invalid message format: {e}")
        return

    # Verrou de consentement (ferme par defaut) : tant que le backend ne
    # confirme pas "accepted", on renvoie le formulaire (ou "service
    # indisponible"), jamais l'assistant. Exception : le message de
    # confirmation renvoye par la page web elle-meme, qui n'appelle pas le LLM.
    is_consent_confirmation_message = (
        message.get("type") == "text"
        and message.get("text", {}).get("body", "").strip() in CONSENT_CONFIRMATION_REPLIES
    )
    if not is_consent_confirmation_message:
        gate_payload = consent_gate_payload(wa_id)
        if gate_payload:
            send_message(gate_payload)
            consent_gated.set(pseudo_id_for(wa_id))
            if consent_hold.hold(wa_id, message, CONSENT_CONFIRMATION_REPLIES):
                send_message(get_text_message_input(wa_id, consent_hold.KEPT_NOTICE))
            return
    # First message since she accepted on the form: the confirmation queued by
    # the backend goes out now, before anything else, instead of landing after
    # the answer at the next reminder poll. The wa.me confirmation text gets its
    # own reply in process_text_message.
    if consent_gated.pop(pseudo_id_for(wa_id)) and not is_consent_confirmation_message:
        pending_notices.deliver_now(wa_id, send_message)
    if consent_hold.supersedes(message, CONSENT_CONFIRMATION_REPLIES):
        consent_hold.discard(wa_id)
    else:
        consent_hold.replay(
            wa_id,
            lambda text: send_message(get_text_message_input(wa_id, text)),
            lambda body: process_text_message(wa_id, {"type": "text", "text": {"body": body}}),
        )

    # Process based on message type
    message_type = message.get("type", "unknown")

    if route_button_reply(wa_id, extract_button_id(message), send_message):
        return

    # She answered a discreet reminder: show its detail, then handle her
    # message as usual.
    for detail_payload in reminder_detail_pending.pop(pseudo_id_for(wa_id)) or []:
        send_message(detail_payload)
        reminder_detail_shown.set(pseudo_id_for(wa_id))

    if message_type == "button":
        # Template quick reply that is not a bot action: treat it as text.
        message_type = "text"
        message = {"type": "text", "text": {"body": (message.get("button") or {}).get("text", "")}}

    if message_type == "text":
        process_text_message(wa_id, message)

    elif message_type == "audio":
        process_audio_message(wa_id, message)

    elif message_type == "interactive":
        process_interactive_message(wa_id, message)

    elif message_type == "location":
        process_location_message(wa_id, message)

    else:
        logging.error(f"Unsupported message type: {message_type}")


def handle_request(wa_id, structured_json):
    # Clean markdown formatting from JSON string
    if isinstance(structured_json, str):
        # Remove ```json, ```, and any language identifiers after ```
        clean_json = re.sub(r'^```(?:json)?\s*', '', structured_json.strip())
        clean_json = re.sub(r'\s*```$', '', clean_json)
        clean_json = clean_json.strip()
        
        # Parse the cleaned JSON
        try:
            json_f = json.loads(clean_json)
        except json.JSONDecodeError as e:
            logging.error(f"Failed to parse JSON: {e}")
            return
    else:
        json_f = structured_json
    
    request_type = json_f.get("request_type", "unknown")
    
    if request_type == "question":
        handle_question_request(wa_id, json_f)
    elif request_type == "translation":
        handle_translation_request(wa_id, json_f)
    elif request_type == "agent_action":
        handle_agent_action_request(wa_id, json_f)
    elif request_type == "location_request":
        handle_location_request(wa_id, json_f)
    elif request_type == "reminder":
        reminder_flow.start_from_structured(wa_id, json_f, send_message)
    elif request_type == "reminder_update":
        reminder_update.start_from_structured(wa_id, json_f, send_message)
    elif request_type == "health_fact":
        health_fact_flow.start_from_structured(wa_id, json_f, send_message)
    elif request_type == "helpline_request":
        handle_helpline_request(wa_id, json_f)
    else:
        logging.error(f"Unknown request type: {request_type}")

def parse_structured_response(structured_json):
    """Parses the model's structured answer, tolerating ```json fences."""
    if isinstance(structured_json, dict):
        return structured_json
    if not isinstance(structured_json, str):
        return {}
    cleaned = re.sub(r"^```(?:json)?\s*", "", structured_json.strip())
    cleaned = re.sub(r"\s*```$", "", cleaned).strip()
    try:
        parsed = json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


GENERATION_FALLBACK_MESSAGE = (
    "Je suis désolée, je n'arrive pas à répondre pour le moment. "
    "Pouvez-vous réessayer dans quelques instants ?"
)

# Messages pre-remplis renvoyes par la page web de consentement (bouton wa.me
# apres soumission du formulaire) - repondus directement, sans passer par le LLM.
CONSENT_CONFIRMATION_REPLIES = {
    "J'ai donne mon consentement ✅": (
        "Merci ! Votre consentement a bien ete enregistre. Je suis la pour vous "
        "accompagner sur toutes vos questions de sante sexuelle et reproductive. \U0001F49B"
    ),
    "J'ai refuse de donner mon consentement": (
        "D'accord, votre choix a ete respecte. Vous pouvez revenir a tout moment "
        "et redonner votre accord si vous changez d'avis. Prenez soin de vous. \U0001F49B"
    ),
}


def send_menu(wa_id) -> None:
    """Send the menu as a native list, falling back to text if WhatsApp refuses.

    A list is refused outside the 24h window, and an interactive message that
    does not go through must not leave her without a menu at all.
    """
    response = send_message(menu.build_payload(wa_id))
    if response is not None and response.status_code < 400:
        return
    logging.warning("Interactive menu refused, falling back to text.")
    send_message(get_text_message_input(wa_id, menu.TEXT_FALLBACK))


def _accepts(text: str) -> bool:
    """Whether she accepted the offer of the nearest health service."""
    from app.services.when_fr import normalize

    answer = normalize(text or "").rstrip(" !.")
    return answer in {
        "oui", "ok", "oui merci", "merci", "oui stp", "oui s il te plait",
        "trouve", "trouve le plus proche", "le plus proche", "oui trouve",
        "vas y", "allez", "yes",
    }


def process_text_message(wa_id, message):
    """Handles text message input, ensuring proper JSON processing.

    Returns the reply text that was sent to the user, so callers such as
    process_audio_message can voice the answer itself rather than the raw
    JSON envelope the model produces.
    """
    raw_body = message["text"]["body"]

    confirmation_reply = CONSENT_CONFIRMATION_REPLIES.get(raw_body.strip())
    if confirmation_reply:
        send_message(get_text_message_input(wa_id, confirmation_reply))
        if raw_body.strip() == "J'ai donne mon consentement ✅":
            send_menu(wa_id)
        return None

    # A question the bot asked comes first: her answer to it must not be read
    # as a menu choice. "menu" stays an escape hatch out of any flow.
    answering = awaiting_her_answer(pseudo_id_for(wa_id))

    number = menu.number_in(raw_body)
    if number and not answering and menu.act(wa_id, number, send_message):
        return None

    # A short message that names a feature is served straight away, whether she
    # picked it in the menu or typed it in her own words.
    intent = intents.detect(raw_body)
    if intent == intents.MENU:
        send_menu(wa_id)
        return None
    if intent and not answering and menu.act_on_intent(wa_id, intent, send_message):
        return None

    # A reminder being prepared owns her next message: the date she types,
    # or « annuler », which drops that draft and not her reminders.
    if reminder_flow.consume_text(wa_id, raw_body, send_message):
        return None

    # She was offered the nearest health service after the emergency numbers,
    # and she answered yes: the location is what finds it.
    if emergency_offer.pop(pseudo_id_for(wa_id)) and _accepts(raw_body):
        pending_place_category.set(wa_id, "hospital")
        send_message(send_location_request(wa_id))
        return None

    # A reminder being moved owns her next message too: which one, and to when.
    if reminder_update.consume_text(wa_id, raw_body, send_message):
        return None

    # "Quel est le message ?" after a discreet notice: the detail was just sent
    # above, or there is none. Either way the model has nothing to say about it,
    # and it used to answer with the out-of-scope redirect.
    if is_detail_request(raw_body):
        if reminder_detail_shown.pop(pseudo_id_for(wa_id)):
            return None
        send_message(get_text_message_input(wa_id, NO_DETAIL_TEXT))
        push_exchange_to_backend(wa_id, raw_body, response=NO_DETAIL_TEXT, request_type="reminder")
        return NO_DETAIL_TEXT

    # A numbered cancellation ("annule le rappel 2") needs the last shown list
    # and is served directly; "annule tout" stays the global opt-out below.
    cancel_number = extract_cancel_number(raw_body)
    if cancel_number is not None:
        response_text = handle_cancel_one(wa_id, cancel_number, send_message)
        push_exchange_to_backend(wa_id, raw_body, response=response_text, request_type="reminder")
        return response_text

    if is_reminder_optout(raw_body):
        forget_snapshot(wa_id)
        cancelled = cancel_pending_reminders_for_user(wa_id)
        if cancelled:
            response_text = "D'accord, j'ai annulé tous vos rappels programmés."
        else:
            response_text = "Vous n'avez aucun rappel programmé à annuler."
        send_message(get_text_message_input(wa_id, response_text))
        push_exchange_to_backend(wa_id, raw_body, response=response_text, request_type="reminder")
        return response_text

    # "Quels sont mes rappels ?" is answered from the real data, never guessed
    # by the model: it hallucinated an empty list when it had no context.
    if is_list_request(raw_body):
        response_text = handle_list_request(wa_id, send_message)
        push_exchange_to_backend(wa_id, raw_body, response=response_text, request_type="reminder")
        return response_text

    if consume_feedback_comment(wa_id, raw_body, send_message):
        return None

    if is_maps_link(raw_body):
        location_message = extract_maps_location(raw_body)
        if location_message:
            process_location_message(wa_id, location_message)
            loc = location_message["location"]
            push_exchange_to_backend(
                wa_id,
                raw_body,
                response=f"📍 Localisation reçue — {loc.get('name', 'Position partagée')}",
                request_type="location",
            )
            return None
        response_text = (
            "📍 Merci pour votre localisation. Le service de géolocalisation est "
            "momentanément indisponible : je n'ai pas pu déterminer le lieu le plus "
            "proche. Réessayez dans quelques minutes, ou indiquez-moi votre quartier "
            "en toutes lettres (ex. « Pharmacie près de Lomé »)."
        )
        send_message(get_text_message_input(wa_id, response_text))
        push_exchange_to_backend(wa_id, raw_body, response=response_text, request_type="location")
        return response_text

    preferred_name = resolve_preferred_name(wa_id, raw_body)
    context = build_context_memory(wa_id, raw_body)
    generation_failed = False
    try:
        structured_json = generate_response(
            raw_body,
            wa_id,
            context=context,
            preferred_name=preferred_name,
        )
        parsed = parse_structured_response(structured_json)
    except Exception as exc:
        generation_failed = True
        logging.error(
            "Response generation failed: category=%s exception=%s",
            category_for_provider_error(exc),
            type(exc).__name__,
        )
        parsed = {}

    if not parsed:
        if not generation_failed:
            logging.warning("Response generation failed: category=invalid_response")
        response_text = GENERATION_FALLBACK_MESSAGE
        send_message(get_text_message_input(wa_id, response_text))
        return response_text

    handle_request(wa_id, parsed)

    response = parsed.get("response") if isinstance(parsed, dict) else None
    request_type = parsed.get("request_type") if isinstance(parsed, dict) else None
    response_empty = response is None or str(response).strip().lower() in ("", "n/a", "na", "none", "null")
    if response_empty:
        if request_type == "location_request":
            response = "📍 Localisation demandée — merci d'envoyer votre position."
        else:
            response = None
    push_exchange_to_backend(wa_id, raw_body, response=response, request_type=request_type)
    return response

# Sent when the voice note cannot be turned into an answer. Silence used to be
# the only outcome of any failure in this handler, which reads to the user as a
# dead bot; an explicit apology at least invites a retry.
VOICE_FALLBACK_MESSAGE = (
    "🎙️ Je n'ai pas réussi à comprendre votre message vocal. "
    "Pouvez-vous réessayer en parlant un peu plus lentement, "
    "ou m'écrire votre question en texte ?"
)

# Cap on the de-duplication sets. They are per-replica and never expired, so
# without a bound a long-lived replica leaks memory for every message it sees.
_PROCESSED_IDS_MAX = 5000


def _remember_processed(seen: set, item_id: str) -> bool:
    """Records `item_id`; returns False when it was already handled."""
    if item_id in seen:
        return False
    if len(seen) >= _PROCESSED_IDS_MAX:
        seen.clear()
    seen.add(item_id)
    return True


def _transcribe_voice_note(audio_path: str) -> tuple[str, str]:
    """Returns (text, language) for a downloaded voice note.

    WHISPER_LANGUAGE pins the decoding language (default French). Detection is
    only used when it is explicitly set to "auto", because on the 2-3s clips
    people actually send, Whisper's detector is close to a coin flip.
    """
    forced = WHISPER_LANGUAGE if WHISPER_LANGUAGE not in ("", "auto") else None
    model = get_whisper()

    if _WHISPER["engine"] == "faster":
        # vad_filter drops the silence WhatsApp pads voice notes with, so the
        # decoder only sees speech. Pinning temperature to 0 disables the
        # fallback loop that re-decodes the clip up to six times at rising
        # temperatures whenever the output looks poor - on noisy short notes
        # that loop was most of the 42s.
        segments, info = model.transcribe(
            audio_path,
            language=forced,
            beam_size=WHISPER_BEAM_SIZE,
            temperature=0.0,
            vad_filter=True,
            condition_on_previous_text=False,
        )
        text = "".join(segment.text for segment in segments).strip()
        language = (getattr(info, "language", None) or forced or "fr").lower()
        return text, language

    result = model.transcribe(audio_path, language=forced, fp16=False)
    text = (result.get("text") or "").strip()
    language = (result.get("language") or forced or "fr").lower()
    return text, language


def process_audio_message(wa_id, message):
    """Handles a WhatsApp voice note: transcribe, answer, then voice the answer."""
    audio_path = None
    tts_path = None
    try:
        audio_id = message["audio"]["id"]
    except (KeyError, TypeError):
        logging.error("Invalid audio message: missing audio ID.")
        return

    if not _remember_processed(processed_audio_ids, audio_id):
        logging.info(f"Audio with ID {audio_id} has already been processed.")
        return

    try:
        os.makedirs("data", exist_ok=True)
        # One file per message. The previous fixed data/downloaded_audio.wav was
        # shared by every worker thread and every replica, so two voice notes
        # arriving together overwrote each other before transcription.
        # WhatsApp sends OGG/Opus, not WAV; name it accordingly so the decoders
        # that trust the extension (pydub, librosa) do not misread the header.
        audio_path = os.path.join("data", f"voice_{audio_id}.ogg")

        media_url = get_media_url(audio_id, current_app.config['ACCESS_TOKEN'])
        download_media(media_url, current_app.config['ACCESS_TOKEN'], audio_path)
        # No sleep here: download_media streams to completion and raises on an
        # empty file, so the old time.sleep(10) only added 10s of latency.

        user_text, language = _transcribe_voice_note(audio_path)
        logging.info("Voice note transcribed: lang=%s", language)

        if language not in DIRECT_LANGUAGES:
            # Fall back to the Ewe pipeline, but never let it lose the message:
            # if either the Ewe ASR or the translation is unavailable, keep
            # whatever Whisper produced and answer that.
            logging.info(f"Non-FR/EN voice note ({language}), trying the Ewe pipeline")
            try:
                ewe_text = transcribe_speech(audio_path)
                logging.info("Ewe ASR completed")
            except Exception as asr_err:
                logging.warning(f"Ewe ASR unavailable, keeping the Whisper transcription: {asr_err}")
                ewe_text = ""
            translated = translate_text_safe(ewe_text, target_language_code="fr", source_language_code="ee")
            if translated:
                logging.info("Voice transcription translated to French")
                user_text = translated
            elif ewe_text and not user_text:
                user_text = ewe_text

        if not user_text.strip():
            send_message(get_text_message_input(wa_id, VOICE_FALLBACK_MESSAGE))
            push_exchange_to_backend(wa_id, "[note vocale]", response=VOICE_FALLBACK_MESSAGE, request_type="audio")
            return

        # Run the transcription through the normal text pipeline. Passing the
        # transcription (and not, as before, the JSON the model returned for it)
        # is what keeps this to a single model call and makes the user receive
        # an answer to what they actually said.
        response_text = process_text_message(wa_id, {"text": {"body": user_text}})

        if not response_text or not str(response_text).strip():
            return

        try:
            tts_path = generate_speech_fr(str(response_text), tag=audio_id)
            if tts_path:
                media_resp = get_media_id(tts_path)
                if media_resp and "id" in media_resp:
                    send_message(get_audio_message_input(wa_id, media_resp))
                else:
                    logging.warning("Voice reply upload failed; the text reply was already sent.")
        except Exception as tts_err:
            logging.warning(f"TTS reply failed (text already sent): {tts_err}")

    except Exception as e:
        logging.exception(f"Error processing audio message {audio_id}: {e}")
        try:
            send_message(get_text_message_input(wa_id, VOICE_FALLBACK_MESSAGE))
        except Exception as notify_err:
            logging.error(f"Could not notify the user of the voice failure: {notify_err}")
    finally:
        _safe_unlink(audio_path)
        _safe_unlink(tts_path)


def process_interactive_message(wa_id, message):
     """Handles interactive button responses."""
     button_title = message["interactive"]["button_reply"]["title"]
     preferred_name = resolve_preferred_name(wa_id, button_title)
     try:
         structured_json = generate_response(
             button_title,
             wa_id,
             preferred_name=preferred_name,
         )
         parsed = parse_structured_response(structured_json)
     except Exception as exc:
         logging.error("Interactive response generation failed: %s", type(exc).__name__)
         parsed = {}
     if not parsed:
         send_message(get_text_message_input(wa_id, GENERATION_FALLBACK_MESSAGE))
         return
     completed = complete_json(parsed)
     handle_request(wa_id, completed)
     response = completed.get("response")
     push_exchange_to_backend(
         wa_id,
         button_title,
         response=response if response not in ("N/A", "") else None,
         request_type=completed.get("request_type"),
     )

# Category each person asked for, waiting for the location they share next.
# This used to be the module global temp_, shared by every user and every
# webhook thread: whoever asked last decided what everyone else's shared
# location was searched for. Keyed by wa_id now, and consumed on use.

_PLACE_LABELS_FR = {
    "pharmacy": "pharmacie",
    "hospital": "hôpital",
    "clinic": "centre de santé",
}


def process_location_message(wa_id, message):
     """Handles location-based requests and finds nearest relevant locations."""
     try:
         lat = message["location"]["latitude"]
         long = message["location"]["longitude"]

         category = pending_place_category.pop(wa_id) or DEFAULT_PLACE_CATEGORY
         nearest = get_nearest(category, lat, long, 10)
         status = nearest.get("status", 500)

         if status >= 400:
             label = _PLACE_LABELS_FR.get(category, "lieu")
             if status == 404:
                 # A genuine empty result: the search ran and found nothing.
                 response_text = (
                     f"📍 Merci pour votre position ! Je n'ai trouvé aucun(e) {label} "
                     "dans un rayon de 10 km autour de vous. Voulez-vous que je vous "
                     "indique plutôt un autre type de structure de santé ?"
                 )
             else:
                 # 400 means the request itself was malformed, which after
                 # normalisation is a bug on our side, and 5xx is the backend.
                 # Neither says anything about what exists near the user, so do
                 # not claim that nothing was found.
                 logging.error(
                     f"Nearest-place lookup failed with {status} for '{category}': "
                     f"{(nearest.get('meta') or {}).get('detail', '')[:300]}"
                 )
                 response_text = (
                     "📍 Localisation reçue — merci ! Le service de géolocalisation est "
                     "momentanément indisponible : je n'ai pas pu calculer le lieu le plus "
                     "proche. Réessayez dans quelques minutes."
                 )
             data = get_text_message_input(wa_id, response_text)
             send_message(data)
             return

         data = get_location_message_input(
             wa_id,
             nearest["data"]["result"]["latitude"],
             nearest["data"]["result"]["longitude"],
             nearest["data"]["result"]["name"],
             nearest["data"]["result"]["google_maps_url"]
         )
         send_message(data)

     except (KeyError, IndexError):
         logging.error("Invalid location format.")

# Additional Helper Functions

def complete_json(structured_json):
    """Refines missing fields in JSON input according to structured processing."""
    if structured_json.get("request_type") == "translation" and structured_json.get("target_language") == "N/A":
        structured_json["target_language"] = infer_target_language(structured_json["request_content"])
    return structured_json

def infer_target_language(request_content):
    """Infers the target language based on content patterns."""
    if "anglais" in request_content:
        return "French"
    elif "Ewè" in request_content:
        return "Ewè"
    elif "Kabyè" in request_content:
        return "Kabyè"
    return "N/A"

def handle_location_request(wa_id, structured_json):
    pending_place_category.set(
        wa_id, normalize_place_category(structured_json.get("request_content", ""))
    )
    data = send_location_request(wa_id)
    send_message(data)

HELPLINES_PATH = os.path.join(os.path.dirname(__file__), 'helplines.json')

def load_helplines():
    with open(HELPLINES_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)

def handle_helpline_request(wa_id, structured_json):
    """Sends the phone number of the relevant Togolese helpline (VBG, sexual health, child protection)."""
    category = structured_json.get("request_content", "")
    helplines = load_helplines()
    helpline = helplines.get(category, helplines["sante_sexuelle"])
    response = f"{helpline['name']} : {helpline['number']}\n{helpline['description']}"
    data = get_text_message_input(wa_id, response)
    send_message(data)

def handle_question_request(wa_id, structured_json):
    """Handles question-type requests and sends AI-generated responses."""
    response = structured_json.get("response", "I'm here to help, but I need more details.")
    data = get_text_message_input(wa_id, response)
    send_message(data)

def handle_agent_action_request(wa_id, structured_json):
    """Handles agent action requests (reserved for future use)."""
    response = structured_json.get("response") or "Cette fonctionnalite sera bientot disponible."
    data = get_text_message_input(wa_id, response)
    send_message(data)

def handle_translation_request(wa_id, structured_json):
    """Handles translation requests with correct language & format handling."""
    target_lang = structured_json.get("target_language", "N/A")
    target_lang = unidecode(target_lang).upper()
    target_format = structured_json.get("target_format", "text")
    request_content = structured_json.get("request_content", "")
    structured_json["response"]

    if target_lang == "N/A":
        response = "Please specify the target language.//Précisez la langue d'arrivée"
        structured_json["response"] = response
        data = get_text_message_input(wa_id, response)

    elif target_lang not in SUPPORTED_LANGUAGES:
        response = "We do not cover this language yet."
        response = "Please specify the target language."
        structured_json["response"] = response
        data = get_text_message_input(wa_id, response)
    else:
        data = translate_content(wa_id,request_content, target_lang, target_format,structured_json["response"])

    send_message(data)




def translate_content(wa_id, request_content, target_lang, target_format, response):
    """Translates text or speech based on requested language and format."""
    if target_format == "audio" and target_lang == "EWE":
        try:
            source_lang = detect_language(request_content) # Detect language of processed text
            processed_text = transform_text(request_content)
            ewe_translation = translate_text(processed_text, target_language_code ="ee", source_language_code = source_lang)

            # Call your actual TTS function
            ewe_norm = post_process_numbers_in_ewe(ewe_translation, translate_text)
            ee_speech_path = generate_speech(ewe_norm)
            ee_speech_path = change_pitch(ee_speech_path,+2.5)
            media_response = get_media_id(ee_speech_path)
            data = get_audio_message_input(wa_id, media_response)

            return data

        except Exception as e:
            logging.error("Ewe audio request failed: %s", type(e).__name__)
            return None

    if target_format == "audio" and target_lang == "MINA":
        try:
            mresponse = mtranslate_text(request_content)

            m_speech_path = generate_mspeech(mresponse)
            m_speech_path = change_pitch(m_speech_path,+2.5)
            media_response = get_media_id(m_speech_path)
            data = get_audio_message_input(wa_id, media_response)

            return data

        except Exception as e:
            logging.error("Mina audio request failed: %s", type(e).__name__)
            return None 
    if target_format == "audio" and target_lang == "TEM":
        try:

            tresponse = ktranslate_text(request_content)

            # Kabye text, so the Kabye voice: generate_kspeech is the
            # get_tts_kdh() wrapper that returns the mp3 path. It used to be
            # spelled generate_tspeech(), which exists nowhere, so every TEM
            # voice note died on a NameError that the broad except below turned
            # into a silent None.
            t_speech_path = generate_kspeech(tresponse)
            t_speech_path = change_pitch(t_speech_path,+2.5)
            media_response = get_media_id(t_speech_path)
            data = get_audio_message_input(wa_id, media_response)

            return data

        except Exception as e:
            logging.error("Tem audio request failed: %s", type(e).__name__)
            return None

    if target_format == "audio" and target_lang == "FR":
        try :
            device = "cuda" if torch.cuda.is_available() else "cpu"

            # List available 🐸TTS models

            # Init TTS
            tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(device)

            tgtext = request_content

            fr_speech_path = "data/output.wav"
            # Text to speech to a file
            tts.tts_to_file(text= tgtext, speaker_wav="data/Voices007.wav", language="fr", file_path=fr_speech_path)

            media_response = get_media_id(fr_speech_path)
            data = get_audio_message_input(wa_id, media_response)

            return data

        except Exception as e:
            logging.error("French audio request failed: %s", type(e).__name__)
            # Handle the error as appropriate, e.g., send an error message back
            return None  # Or 


# You need to define or import the following functions used in the code:
# transform_text(text) -> processes input text
# detect_language(text) -> detects language of text (should return a language code compatible with translate_text)
# translate_text(text, src_lang, tgt_lang) -> translates text
# tts_from_ewe_translation(text_file_path, output_dir) -> generates speech from Ewe text file
# get_media_id(audio_file_path) -> gets media ID for message
# get_audio_message_input(recipient, media_id) -> formats message data
# change_pitch(audio_file_path, pitch_change) -> optional pitch modification
# message["from"] -> assumed to be available from incoming message data
    elif target_format == "text":
    #    if target_lang == "KABYE":
    #   src_lang = detect_language(request_content)
    #   en_translation = request_content
    #   if src_lang != "en":
    #       en_translation = translate_text(request_content, target_language_code ="en", source_language_code = src_lang)
    #   kbp_t = translate_to_kabye(en_translation)
    #   data = get_text_message_input(wa_id, kbp_t)
    #   return data
        if target_lang == "EWE": 

            eresponse = etranslate_text(request_content)
            data = get_text_message_input(wa_id, eresponse)
            return data
        if target_lang == "MINA": 

            mresponse = mtranslate_text(request_content)
            data = get_text_message_input(wa_id, mresponse)
            return data
        if target_lang == "TEM":
            tresponse = ktranslate_text(request_content)
            data = get_text_message_input(wa_id, tresponse)
            return data
        elif response =="N/A" or response =="We do not cover this language yet.":
            translation = "Service indsiponible"
            data = get_text_message_input(wa_id, translation)
            return data
        else :
            data = get_text_message_input(wa_id, response)
            return data

    return "Invalid format specified."


def is_valid_whatsapp_message(body: dict) -> bool:
    """
    Validates the structure of the incoming WhatsApp message.
    """
    return (
        body.get("object") == "whatsapp_business_account" and
        "entry" in body and
        len(body["entry"]) > 0 and
        "changes" in body["entry"][0] and
        len(body["entry"][0]["changes"]) > 0 and
        "value" in body["entry"][0]["changes"][0] and
        "messages" in body["entry"][0]["changes"][0]["value"] and
        len(body["entry"][0]["changes"][0]["value"]["messages"]) > 0
    )

# Example Flask route to handle incoming messages
# from flask import Flask, request

# app = Flask(__name__)

# @app.route('/webhook', methods=['POST'])
# def webhook():
#     body = request.get_json()
#     if is_valid_whatsapp_message(body):
#         process_whatsapp_message(body)
#         return jsonify({"status": "success"}), 200
#     else:
#         return jsonify({"status": "invalid message"}), 400

# if __name__ == '__main__':
#     app.run(debug=True)
