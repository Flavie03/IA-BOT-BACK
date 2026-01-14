import re
import unicodedata
from typing import Literal

Intent = Literal["small_talk", "intent_metier", "hors_perimetre", "ambigu"]

SMALL_TALK_PATTERNS = [
    "bonjour", "salut", "hello", "bonsoir",
    "ça va", "comment ça va", "merci", "merci beaucoup",
    "au revoir", "a bientôt", "à bientôt",
    "tu es qui", "qui es-tu", "comment tu t'appelles",
]

# Verbes / mots-clés "métier" (voyage)
TRAVEL_KEYWORDS = [
    "partir", "voyage", "voyager", "aller", "visiter", "destination",
    "vol", "vols", "avion", "train", "bus",
    "hotel", "hôtel", "logement", "hébergement",
    "météo", "temps", "budget", "prix", "réserver", "reservation", "réservation",
    "itinéraire", "itineraire", "dates", "mois","météo", "temps", "climat","meteo",
]

def _normalize(text: str) -> str:
    text = text.lower().strip()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

def classify_intent_rules(message: str) -> Intent:
    m = _normalize(message)

    # 1) small talk direct
    if any(p in m for p in SMALL_TALK_PATTERNS):
        return "small_talk"

    # 2) signaux faibles small talk
    words = m.split()
    if len(words) <= 4 and not any(k in m for k in TRAVEL_KEYWORDS):
        # "ok", "super", "merci", "cool" -> small talk
        if any(w in ["ok", "super", "cool", "merci", "top"] for w in words):
            return "small_talk"

    # 3) métier voyage ?
    if any(k in m for k in TRAVEL_KEYWORDS):
        return "intent_metier"

    # 4) Ambigu si très court mais contient un nom propre/ville possible
    if len(words) <= 2:
        return "ambigu"

    # 5) sinon hors périmètre
    return "hors_perimetre"
