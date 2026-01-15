import re
import requests
from datetime import date, datetime, timezone

from app.agent.stays import get_stay_location


def _month_to_dates(month: str):
    """
    month peut être:
    - 'YYYY-MM' -> checkin=15, checkout=16
    - 'YYYY-MM-DD/YYYY-MM-DD' -> (start, end)
    """
    if not month:
        return None, None

    month = month.strip()

    if "/" in month:
        parts = month.split("/")
        if len(parts) == 2 and len(parts[0]) == 10 and len(parts[1]) == 10:
            return parts[0], parts[1]

    if re.fullmatch(r"\d{4}-\d{2}", month):
        y, m = month.split("-")
        y = int(y); m = int(m)
        checkin = date(y, m, 15).isoformat()
        checkout = date(y, m, 16).isoformat()
        return checkin, checkout

    return None, None


def _extract_eur_prices(text: str):
    """
    Extrait des montants € dans un texte.
    Retourne une liste d'int.
    """
    matches = re.findall(r"(\d[\d\s\u202f\u00a0]{0,10})\s?€", text)
    prices = []
    for m in matches:
        m = m.replace("\u202f", " ").replace("\u00a0", " ")
        m = re.sub(r"[^\d]", "", m)
        if m.isdigit():
            prices.append(int(m))
    return prices


def scrape_hotels(city: str, month: str):
    """
    Scraping Kayak stays:
    URL format:
    https://www.kayak.fr/hotels/<slug>-p<pid>/<checkin>/<checkout>/2adults;map?sort=rank_a
    """
    if not city:
        return {"status": "error", "error": "city is required", "source": "Kayak"}
    if not month:
        return {"status": "error", "error": "month is required", "city": city, "source": "Kayak"}

    loc = get_stay_location(city)
    if not loc:
        return {
            "status": "error",
            "error": f"Unknown city for stays mapping: {city}. Add slug/pid in app/agent/stays.py",
            "city": city,
            "source": "Kayak"
        }

    checkin, checkout = _month_to_dates(month)
    if not checkin or not checkout:
        return {
            "status": "error",
            "error": "month must be 'YYYY-MM' or 'YYYY-MM-DD/YYYY-MM-DD'",
            "city": city,
            "month": month,
            "source": "Kayak"
        }

    slug = loc["slug"]
    pid = loc["pid"]

    url = f"https://www.kayak.fr/hotels/{slug}-p{pid}/{checkin}/{checkout}/2adults;map"
    params = {"sort": "rank_a"}

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/121.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
    }

    try:
        r = requests.get(url, params=params, headers=headers, timeout=25, allow_redirects=True)
        r.raise_for_status()

        html = r.text
        prices = sorted(_extract_eur_prices(html))

        # on prend les 10 plus bas comme échantillon (heuristique)
        sample = prices[:10]
        if sample:
            min_price = sample[0]
            avg_price = int(sum(sample) / len(sample))
            found = True
        else:
            min_price = None
            avg_price = None
            found = False

        return {
            "status": "ok",
            "city": city,
            "month_input": month,
            "checkin": checkin,
            "checkout": checkout,
            "min_price_eur": min_price if found else "Prix non trouvé",
            "avg_price_eur": avg_price if found else "Prix non trouvé",
            "sample_size": len(sample),
            "url": r.url,
            "source": "Kayak",
            "scraped_at": datetime.now(timezone.utc).isoformat()
        }

    except Exception as e:
        return {
            "status": "error",
            "city": city,
            "month_input": month,
            "checkin": checkin,
            "checkout": checkout,
            "error": str(e),
            "url": r.url if "r" in locals() else url,
            "source": "Kayak",
            "scraped_at": datetime.now(timezone.utc).isoformat()
        }
