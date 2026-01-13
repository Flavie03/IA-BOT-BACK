import requests
from bs4 import BeautifulSoup

def scrape_weather(city: str):
    url = f"https://wttr.in/{city}?format=3"

    response = requests.get(url, timeout=5)
    response.raise_for_status()

    return {
        "city": city,
        "raw": response.text.strip()
    }
