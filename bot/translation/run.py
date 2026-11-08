# Imports the Google Cloud Translation library
import os
import logging

from google.cloud import translate_v3

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "your-project-id")

# Same translate_text function
def translate_text(
    text: str = "Hello",
    language_code: str = "fr",
) -> translate_v3.TranslationServiceClient:
    client = translate_v3.TranslationServiceClient()
    parent = f"projects/{PROJECT_ID}/locations/global"  # Ensure this is properly formatted
    
    response = client.translate_text(
        contents=[text],
        target_language_code=language_code,
        parent=parent,
        mime_type="text/plain",
        source_language_code="fr-Fr",
    )

    # for translation in response.translations:
    #     print(f"Translated text: {translation.translated_text}")
    translated_texts = [translation.translated_text for translation in response.translations][0]
    print(f"{translated_texts}")

    return response

# Test the translation
if __name__ == "__main__":
    # Translate "Hello" to French
    translate_text("J'ai besoin que tu passe chez moi demain pour qu'on discute", "ee")