from fastapi import APIRouter
from app.mcp.tools.weather import scrape_weather
from app.mcp.tools.flight import scrape_flights
from app.mcp.tools.hotel import scrape_hotels

router = APIRouter(prefix="/mcp")

@router.post("/weather")
def weather_tool(payload: dict):
    city = payload.get("city")
    return scrape_weather(city)

@router.post("/flights")
def flight_tool(payload: dict):
    origin = payload.get("from")
    destination = payload.get("to")
    month = payload.get("month")
    return scrape_flights(origin, destination, month)

@router.post("/hotels")
def hotel_tool(payload: dict):
    city = payload.get("city")
    month = payload.get("month")
    return scrape_hotels(city, month)
