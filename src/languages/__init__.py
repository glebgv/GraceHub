# src/languages/__init__.py

from .ru import TEXTS_RU
from .en import TEXTS_EN
from .zh import TEXTS_ZH
from .hi import TEXTS_HI
from .es import TEXTS_ES

LANGS = {
    "ru": TEXTS_RU,
    "en": TEXTS_EN,
    "zh": TEXTS_ZH,   # Chinese (Mandarin)
    "hi": TEXTS_HI,   # Hindi
    "es": TEXTS_ES,   # Spanish
}

