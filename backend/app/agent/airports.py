AIRPORTS = {
    "paris": "CDG",
    "bangkok": "BKK",
    "lisbonne": "LIS",
    "rome": "FCO",
    "madrid": "MAD",
    "barcelone": "BCN"
}

import re

def get_airport_code(city: str) -> str | None:
    if not city:
        return None

    city = city.lower()
    city = re.sub(r"[^a-zàâçéèêëîïôûùüÿñæœ\-]", "", city)

    return AIRPORTS.get(city)
