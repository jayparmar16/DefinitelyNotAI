"""translate tool: machine translation with a number-preservation check and a database cache.

Event: {"text": str, "target_language": str (ISO 639-1, e.g. "es")}.
A translation that drops or changes any number is retried once, then returned flagged
and never cached; the agent must not show a flagged translation as WRI's content.
"""

import hashlib
import os
import re

import boto3

from askwri.tools.db import connect

LANGUAGES = {
    "en": "English",
    "es": "Spanish",
    "pt": "Portuguese",
    "fr": "French",
    "id": "Indonesian",
    "hi": "Hindi",
}
PROMPT = (
    "Translate the text below into {language}. Keep every digit exactly as written (numbers, "
    "years, percentages) and keep [n] citation markers where they are, but translate every word, "
    "including units and words such as 'percent' or 'million'. Reply with only the translation."
    "\n\n{text}"
)
# Spaces are not separators here: "in 2019 15 cities" is two numbers. A French "1 000" then
# reads as two numbers and fails the check, which is the safe direction.
NUMBER = re.compile(r"\d+(?:[.,]\d+)*")


def numbers(text: str) -> list[str]:
    """The numbers in a text as digit strings, sorted. Separators are dropped because they
    legitimately change between languages ("1,000.5" in English is "1.000,5" in Spanish)."""
    return sorted(re.sub(r"\D", "", match) for match in NUMBER.findall(text))


def numbers_preserved(source: str, translation: str) -> list[str]:
    """Numbers in the source that the translation lost or changed (empty when all survive)."""
    remaining = numbers(translation)
    missing = []
    for number in numbers(source):
        if number in remaining:
            remaining.remove(number)
        else:
            missing.append(number)
    return missing


def cache_key(text: str, language: str) -> str:
    """Translations are cached per target language and exact source text."""
    return hashlib.sha256(f"{language}\n{text}".encode()).hexdigest()


def model_translation(text: str, language: str, client=None) -> str:
    """One translation from the model named by ASKWRI_TRANSLATE_MODEL (Converse API)."""
    client = client or boto3.client("bedrock-runtime")
    response = client.converse(
        modelId=os.environ["ASKWRI_TRANSLATE_MODEL"],
        messages=[
            {
                "role": "user",
                "content": [{"text": PROMPT.format(language=LANGUAGES[language], text=text)}],
            }
        ],
        inferenceConfig={"maxTokens": 4096},
    )
    if response["stopReason"] != "end_turn":
        raise RuntimeError(f"translation did not finish: {response['stopReason']}")
    return "".join(
        block.get("text", "") for block in response["output"]["message"]["content"]
    ).strip()


def handler(event: dict, context) -> dict:
    """Return the translation, labelled machine-translated, and whether every number survived."""
    text, language = event["text"], event["target_language"]
    if language not in LANGUAGES:
        raise ValueError(f"target_language must be one of {sorted(LANGUAGES)}")
    key = cache_key(text, language)
    with connect() as connection:
        cached = connection.execute(
            "SELECT text FROM translations WHERE hash = %s", (key,)
        ).fetchone()
        if cached:
            return {
                "translation": cached["text"],
                "machine_translated": True,
                "numbers_preserved": True,
                "cached": True,
            }
        for _ in range(2):
            translation = model_translation(text, language)
            missing = numbers_preserved(text, translation)
            if not missing:
                connection.execute(
                    "INSERT INTO translations (hash, lang, text) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                    (key, language, translation),
                )
                return {
                    "translation": translation,
                    "machine_translated": True,
                    "numbers_preserved": True,
                    "cached": False,
                }
    return {
        "translation": translation,
        "machine_translated": True,
        "numbers_preserved": False,
        "missing_numbers": missing,
        "cached": False,
    }
