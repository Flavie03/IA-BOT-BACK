from fastapi import APIRouter
import requests

from app.agent.schemas import AgentQuery, AgentResponse
from app.agent.kb import get_destination_info
from app.agent.parser import extract_destination, normalize_city_for_tool
from app.agent.decision import needs_weather_info

router = APIRouter()

@router.post("/query", response_model=AgentResponse)
def query_agent(payload: AgentQuery):
    user_message = payload.message

    destination = extract_destination(user_message)
    kb_info = get_destination_info(destination)

    tools_called = []

    # CAS 1 : besoin météo actuelle
    if destination and needs_weather_info(user_message):
        city_for_tool = normalize_city_for_tool(destination)

        response = requests.post(
            "http://127.0.0.1:8000/mcp/weather",
            json={"city": city_for_tool},
            timeout=5
        )
        weather_data = response.json()

        tools_called.append("weather_scraper")

        answer = (
            f"Météo actuelle à {destination.capitalize()} : "
            f"{weather_data['raw']}"
        )

        return AgentResponse(
            answer=answer,
            decision={
                "kb_used": False,
                "tools_called": tools_called
            }
        )

    # CAS 2 : KB suffisante
    if kb_info:
        answer = (
            f"Pour {destination.capitalize()}, "
            f"les meilleures périodes sont {', '.join(kb_info['best_periods'])}. "
            f"Climat : {kb_info['climate']}."
        )

        return AgentResponse(
            answer=answer,
            decision={
                "kb_used": True,
                "tools_called": tools_called
            }
        )

    # CAS 3 : insuffisant
    return AgentResponse(
        answer="Je n’ai pas assez d’informations pour répondre.",
        decision={
            "kb_used": False,
            "tools_called": tools_called
        }
    )
