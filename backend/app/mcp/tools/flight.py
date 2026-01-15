"""import requests
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
    }"""

# backend/app/mcp/tools/flight.py
import re
import requests
from datetime import date
from bs4 import BeautifulSoup

def _month_to_dates(month: str):
    """
    month peut être:
    - 'YYYY-MM'  -> (YYYY-MM-15, YYYY-MM-22)
    - 'YYYY-MM-DD/YYYY-MM-DD' -> (start, end)
    """
    if not month:
        return None, None

    month = month.strip()

    # cas "2026-01-30/2026-02-20"
    if "/" in month:
        parts = month.split("/")
        if len(parts) == 2 and len(parts[0]) == 10 and len(parts[1]) == 10:
            return parts[0], parts[1]

    # cas "2026-01"
    if re.fullmatch(r"\d{4}-\d{2}", month):
        y, m = month.split("-")
        y = int(y); m = int(m)
        depart = date(y, m, 15).isoformat()
        ret = date(y, m, 22).isoformat()
        return depart, ret

    # fallback: si le format est inconnu
    return None, None


def _pick_price_from_text(text: str) -> str | None:
    """
    Fallback simple: cherche un prix en € dans le HTML.
    """
    # Ex: "1 234 €" ou "123 €"
    m = re.search(r"(\d[\d\s]{1,10})\s?€", text)
    if not m:
        return None
    return m.group(0).strip()


def scrape_flights(origin: str, destination: str, month: str):
    """
    origin/destination doivent être des IATA (CDG, BKK, etc.)
    month peut être 'YYYY-MM' ou 'YYYY-MM-DD/YYYY-MM-DD'
    """
    depart_date, return_date = _month_to_dates(month)

    if not origin or not destination:
        return {
            "status": "error",
            "error": "origin and destination (IATA) are required",
            "source": "Kayak"
        }

    if not depart_date or not return_date:
        return {
            "status": "error",
            "error": "month must be 'YYYY-MM' or 'YYYY-MM-DD/YYYY-MM-DD'",
            "origin": origin,
            "destination": destination,
            "month": month,
            "source": "Kayak"
        }

    # URL Kayak formatée comme l'exemple
    url = f"https://www.kayak.fr/flights/{origin}-{destination}/{depart_date}/{return_date}"
    # On garde un query string minimal (sinon Kayak peut rediriger / changer)
    params = {"sort": "bestflight_a"}

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/121.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
    }

    response = requests.get(url, headers=headers, params=params, timeout=20)
    response.raise_for_status()

    html = response.text
    soup = BeautifulSoup(html, "html.parser")

    # Tentatives de sélecteurs (Kayak change souvent)
    selectors = [
        ("div", {"data-testid": "resultPrice"}),        # parfois
        ("span", {"class": re.compile(r".*price.*", re.I)}),  # heuristique
    ]

    found_price = None

    # 1) selectors
    for tag_name, attrs in selectors:
        try:
            el = soup.find(tag_name, attrs=attrs)
            if el and el.get_text(strip=True):
                txt = el.get_text(" ", strip=True)
                p = _pick_price_from_text(txt)
                if p:
                    found_price = p
                    break
        except Exception:
            pass

    # 2) fallback regex global
    if not found_price:
        found_price = _pick_price_from_text(html)

    return {
        "status": "ok",
        "origin": origin,
        "destination": destination,
        "depart_date": depart_date,
        "return_date": return_date,
        "month_input": month,
        "cheapest_price": found_price if found_price else "Prix non trouvé",
        "url": response.url,
        "source": "Kayak"
    }
