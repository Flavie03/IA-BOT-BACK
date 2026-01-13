from fastapi import APIRouter
from app.mcp.tools.weather import scrape_weather
from app.mcp.tools.flight import scrape_flights
from app.mcp.tools.hotel import scrape_hotels

router = APIRouter(prefix="/mcp")

@router.post("/weather")
def weather_tool(payload: dict):
    city = payload.get("city")
    if not city:
        return {"error": "City is required"}

    data = scrape_weather(city)
    return data

@router.post("/flights")
def flight_tool(payload: dict):
    origin = payload.get("from")
    destination = payload.get("to")
    month = payload.get("month")

    return scrape_flights(origin, destination, month)

from app.mcp.tools.hotel import scrape_hotels

@router.post("/hotels")
def hotel_tool(payload: dict):
    city = payload.get("city")
    month = payload.get("month")

    return scrape_hotels(city, month)
