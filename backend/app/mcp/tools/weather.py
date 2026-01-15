"""import requests
from bs4 import BeautifulSoup

def scrape_weather(city: str):
    url = f"https://wttr.in/{city}?format=3"

    response = requests.get(url, timeout=5)
    response.raise_for_status()

    return {
        "city": city,
        "raw": response.text.strip()
    }
"""

import requests
from datetime import datetime, timezone

def scrape_weather(city: str):
    """
    Tool météo simple via wttr.in
    - city: str (ex: 'Bangkok', 'Lisbon')
    Retourne un JSON standardisé.
    """
    if not city:
        return {"status": "error", "error": "city is required", "source": "wttr.in"}

    url = f"https://wttr.in/{city}"
    params = {"format": "3", "lang": "fr"}

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/121.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
    }

    try:
        r = requests.get(url, params=params, headers=headers, timeout=10)
        r.raise_for_status()

        raw = r.text.strip()

        return {
            "status": "ok",
            "city": city,
            "raw": raw,
            "url": r.url,
            "source": "wttr.in",
            "scraped_at": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        return {
            "status": "error",
            "city": city,
            "error": str(e),
            "url": url,
            "source": "wttr.in",
            "scraped_at": datetime.now(timezone.utc).isoformat()
        }
