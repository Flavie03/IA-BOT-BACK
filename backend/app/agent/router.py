from fastapi import APIRouter
import requests

from app.agent.schemas import AgentQuery, AgentResponse
from app.agent.kb import get_destination_info
from app.agent.parser import extract_destination, normalize_city_for_tool
from app.agent.llm import decide_tools, generate_answer

router = APIRouter()

@router.post("/query", response_model=AgentResponse)
def query_agent(payload: AgentQuery):
    user_message = payload.message

    destination = extract_destination(user_message)           # ex: "lisbonne"
    kb_info = get_destination_info(destination)               # dict ou None

    tools_called = []
    tool_results = {}

    # 1) Décision tool/no-tool via LLM
    llm_decision = decide_tools(
        user_message=user_message,
        destination=destination,
        kb_info=kb_info,
        available_tools=["weather", "flights", "hotels"]
    )

    # 2) Exécuter les tools décidés
    if llm_decision.get("use_tools") and destination:
        for tool in llm_decision.get("tools", []):
            name = tool.get("name")
            params = tool.get("params") or {}

            # Normalisation ville pour tools (Lisbon, Paris, etc.)
            city_for_tool = normalize_city_for_tool(destination)

            try:
                if name == "weather":
                    resp = requests.post(
                        "http://127.0.0.1:8000/mcp/weather",
                        json={"city": city_for_tool},
                        timeout=20
                    )
                    resp.raise_for_status()
                    tool_results["weather"] = resp.json()
                    tools_called.append("weather_scraper")

                elif name == "hotels":
                    month = params.get("month", None)
                    resp = requests.post(
                        "http://127.0.0.1:8000/mcp/hotels",
                        json={"city": city_for_tool, "month": month},
                        timeout=30
                    )
                    resp.raise_for_status()
                    tool_results["hotels"] = resp.json()
                    tools_called.append("hotel_scraper")

                elif name == "flights":
                    origin = params.get("from", None)
                    month = params.get("month", None)
                    resp = requests.post(
                        "http://127.0.0.1:8000/mcp/flights",
                        json={"from": origin, "to": city_for_tool, "month": month},
                        timeout=30
                    )
                    resp.raise_for_status()
                    tool_results["flights"] = resp.json()
                    tools_called.append("flight_scraper")

            except Exception as e:
                tool_results[f"{name}_error"] = str(e)

    # 3) Réponse finale via LLM
    final_answer = generate_answer(
        user_message=user_message,
        destination=destination,
        kb_info=kb_info,
        tool_results=tool_results if tool_results else None
    )

    # 4) Retour (traçable pour la soutenance)
    return AgentResponse(
        answer=final_answer,
        decision={
            "destination": destination,
            "kb_used": bool(kb_info),
            "tools_called": tools_called,
            "llm_decision": llm_decision
        }
    )
