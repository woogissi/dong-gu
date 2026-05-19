from __future__ import annotations

import re
from typing import Literal


PrimaryIntent = Literal["GENERAL", "INFO", "PROFANITY"]

_PROFANITY_TERMS = {
    "\uc2dc\ubc1c",
    "\uc2dc\ubc8c",
    "\ubcd1\uc2e0",
    "\uc9c0\ub784",
}

_INFO_HINTS = {
    "\uc218\uac15",
    "\uc218\uac15\uc2e0\uccad",
    "\uc7a5\ud559",
    "\uc7a5\ud559\uae08",
    "\uae30\uc219\uc0ac",
    "\uc0dd\ud65c\uad00",
    "\uc878\uc5c5",
    "\uc131\uc801",
    "\ub4f1\ub85d\uae08",
    "\ud1b5\ud559\ubc84\uc2a4",
    "\ub3c4\uc11c\uad00",
    "\ud559\uc0ac",
    "\ud734\ud559",
    "\ubcf5\ud559",
    "\uc99d\uba85\uc11c",
    "\uc2e0\uccad",
    "\uae30\uac04",
    "\uc77c\uc815",
    "\uc2dc\uac04",
    "\ubc29\ubc95",
    "\uc704\uce58",
    "\uc694\uac74",
    "\ub3d9\uc758\ub300",
    "\ub3d9\uc758\ub300\ud559\uad50",
    "\uc6b4\uc601",
    "\ubcf4\uac15",
    "\uc9c0\uc815\ubcf4\uac15\uc77c",
    "\uad50\uc218",
    "\uad50\uc218\ub2d8",
    "\uc774\uba54\uc77c",
    "\uba54\uc77c",
    "\uc5f0\uad6c\uc2e4",
    "\ud559\uacfc",
    "\uc804\ud654\ubc88\ud638",
    "\uc5f0\ub77d\ucc98",
    "\uac00\ub294 \uae38",
    "\ud589\uc815\uc2e4",
}

_QUESTION_HINTS = {
    "\uc54c\ub824\uc918",
    "\uc54c\ub824\uc8fc\uc138\uc694",
    "\uc5b8\uc81c",
    "\uc5b4\ub514",
    "\uc5b4\ub5bb\uac8c",
    "\ubb34\uc5c7",
    "\ubb50",
    "\uac00\ub2a5",
}


class PrimaryIntentClassifier:
    def classify(self, utterance: str) -> PrimaryIntent:
        text = self._normalize(utterance)
        if not text:
            return "GENERAL"
        if any(term in text for term in _PROFANITY_TERMS):
            return "PROFANITY"
        if any(term in text for term in _INFO_HINTS):
            return "INFO"
        if any(term in text for term in _QUESTION_HINTS) and re.search(r"\d|\?", text):
            return "INFO"
        return "GENERAL"

    def _normalize(self, utterance: str) -> str:
        return " ".join((utterance or "").strip().lower().split())
