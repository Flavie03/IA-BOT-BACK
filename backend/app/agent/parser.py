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
