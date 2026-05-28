from __future__ import annotations

from typing import Literal

from backend.app.utils.profanity_filter import contains_profanity
from rag.preprocess.primary_intent import PrimaryIntentClassifier as RagPrimaryIntentClassifier

PrimaryIntent = Literal["GENERAL", "INFO", "PROFANITY"]


class PrimaryIntentClassifier:
    """Backend-facing primary intent classifier.

    Keep the public return labels stable while sharing the richer university
    domain rules with the RAG preprocessing package.
    """

    def __init__(self) -> None:
        self._rag_classifier = RagPrimaryIntentClassifier()

    def normalize_text(self, text: str) -> str:
        return " ".join((text or "").strip().lower().split())

    def classify(self, utterance: str) -> PrimaryIntent:
        text = self.normalize_text(utterance)
        if contains_profanity(text):
            return "PROFANITY"
        return self._rag_classifier.classify(text)
