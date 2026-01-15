def extract_destination(message: str):
    message = message.lower()

    cities = ["lisbonne", "paris", "rome", "madrid", "barcelone", "bangkok"]

    for city in cities:
        if city in message:
            return city
    return None

def detect_intent(message: str):
    keywords = ["quand", "meilleure période", "partir", "voyager", "aller"]
    message = message.lower()

    return any(k in message for k in keywords)

CITY_MAPPING = {
    "lisbonne": "Lisbon",
    "paris": "Paris",
    "rome": "Rome",
    "madrid": "Madrid",
    "barcelone": "Barcelona",
    "bangkok": "Bangkok"
}

def normalize_city_for_tool(city: str):
    return CITY_MAPPING.get(city.lower(), city)

import re

def extract_origin_city(message: str):
    m = message.lower()
    patterns = [
        r"de\s+([a-zA-Zéèêàçîôû\-]+)\s+a\s+",      # "de paris a bangkok"
        r"depuis\s+([a-zA-Zéèêàçîôû\-]+)\s+",      # "depuis paris"
    ]
    for p in patterns:
        match = re.search(p, m)
        if match:
            return match.group(1)
    return None

MONTHS = ["janvier","février","fevrier","mars","avril","mai","juin","juillet","août","aout","septembre","octobre","novembre","décembre","decembre"]

def extract_month_fr(message: str):
    m = message.lower()
    for month in MONTHS:
        if month in m:
            return month
    # format "2026-01"
    match = re.search(r"\b\d{4}-\d{2}\b", m)
    if match:
        return match.group(0)
    # format "2026-01-30/2026-02-20"
    match = re.search(r"\b\d{4}-\d{2}-\d{2}/\d{4}-\d{2}-\d{2}\b", m)
    if match:
        return match.group(0)
    return None
