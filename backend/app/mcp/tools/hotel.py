import requests
from bs4 import BeautifulSoup

def scrape_hotels(city: str, month: str):
    url = f"https://www.booking.com/searchresults.html?ss={city}"

    response = requests.get(url, timeout=10)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    price_tags = soup.find_all("span", class_="fcab3ed991")

    prices = []
    for tag in price_tags[:5]:
        prices.append(tag.text.strip())

    average_price = prices[0] if prices else "Prix non trouvé"

    return {
        "city": city,
        "month": month,
        "average_price": average_price,
        "source": "Booking"
    }
