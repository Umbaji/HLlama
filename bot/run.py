import logging
import os
import threading

from dotenv import load_dotenv


load_dotenv()

from app import create_app
from app.utils.whatsapp_utils import warm_speech_models


app = create_app()

if __name__ == "__main__":
    # Load the speech models in the background so the process starts serving
    # immediately while Whisper and VITS come up. The first voice note used to
    # pay this cost on the request path.
    if os.getenv("WARM_SPEECH_MODELS", "true").lower() not in ("0", "false", "no"):
        threading.Thread(target=warm_speech_models, daemon=True).start()

    logging.info("Flask app started")
    app.run(host="0.0.0.0", port=8000, threaded=True)
