# src/languages/__init__.py

from .en import TEXTS_EN
from .es import TEXTS_ES
from .hi import TEXTS_HI
from .ru import TEXTS_RU
from .zh import TEXTS_ZH

LANGS = {
    "ru": TEXTS_RU,
    "en": TEXTS_EN,
    "zh": TEXTS_ZH,  # Chinese (Mandarin)
    "hi": TEXTS_HI,  # Hindi
    "es": TEXTS_ES,  # Spanish
}
