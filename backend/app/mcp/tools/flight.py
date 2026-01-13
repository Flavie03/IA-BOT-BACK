import requests
from bs4 import BeautifulSoup

def scrape_flights(origin: str, destination: str, month: str):
    url = f"https://www.kayak.fr/flights/{origin}-{destination}/{month}"

    response = requests.get(url, timeout=10)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    price_tag = soup.find("span", class_="price-text")

    price = price_tag.text if price_tag else "Prix non trouvé"

    return {
        "origin": origin,
        "destination": destination,
        "month": month,
        "cheapest_price": price,
        "source": "Kayak"
    }