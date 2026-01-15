from fastapi import APIRouter
import requests
import re
from datetime import date

from app.agent.schemas import AgentQuery, AgentResponse
from app.agent.kb import get_destination_info
from app.agent.parser import extract_destination, normalize_city_for_tool
from app.agent.llm import decide_tools, generate_answer, classify_intent_llm_4cats
from app.agent.intent import classify_intent_rules
from app.agent.airports import get_airport_code

router = APIRouter()

# ----------------------------
#parsing (simple & fiable)
MONTHS_FR_TO_NUM = {
    "janvier": "01",
    "février": "02", "fevrier": "02",
    "mars": "03",
    "avril": "04",
    "mai": "05",
    "juin": "06",
    "juillet": "07",
    "août": "08", "aout": "08",
    "septembre": "09",
    "octobre": "10",
    "novembre": "11",
    "décembre": "12", "decembre": "12",
}

def extract_route_cities(message: str):
    m = message.lower().strip()
    patterns = [
        r"\bde\s+([a-zA-Zéèêàçîôû\-]+)\s+(?:a|à)\s+([a-zA-Zéèêàçîôû\-]+)\b",
        r"\bdepuis\s+([a-zA-Zéèêàçîôû\-]+)\s+(?:vers|pour)\s+([a-zA-Zéèêàçîôû\-]+)\b",
        r"\b([a-zA-Zéèêàçîôû\-]+)\s*(?:->|→)\s*([a-zA-Zéèêàçîôû\-]+)\b",
    ]
    for p in patterns:
        match = re.search(p, m)
        if match:
            return match.group(1), match.group(2)
    return None, None


def extract_month_or_dates(message: str):
    m = message.lower().strip()

    match = re.search(r"\b\d{4}-\d{2}-\d{2}/\d{4}-\d{2}-\d{2}\b", m)
    if match:
        return match.group(0)

    for fr_month, mm in MONTHS_FR_TO_NUM.items():
        if fr_month in m:
            year_match = re.search(r"\b(20\d{2})\b", m)
            yyyy = year_match.group(1) if year_match else str(date.today().year)
            return f"{yyyy}-{mm}"

    match = re.search(r"\b(20\d{2}-\d{2})\b", m)
    if match:
        return match.group(1)

    return None


def need_clarification_for_flights(origin_iata, dest_iata, month):
    if not origin_iata:
        return "Pour chercher des vols, tu pars de quelle ville/aéroport ? (ex: Paris/CDG)"
    if not dest_iata:
        return "Pour chercher des vols, tu vas vers quelle ville/aéroport ?"
    if not month:
        return "Pour quelles dates ou quel mois veux-tu voyager ? (ex: 2026-01 ou 2026-01-30/2026-02-20)"
    return None


def need_clarification_for_hotels(dest_city, month):
    if not dest_city:
        return "Pour chercher des hôtels, dans quelle ville veux-tu dormir ?"
    if not month:
        return "Pour quelles dates ou quel mois veux-tu réserver ? (ex: 2026-01 ou 2026-01-16/2026-01-17)"
    return None


def need_clarification_for_weather(dest_city):
    if not dest_city:
        return "Pour la météo, tu veux la météo de quelle ville ?"
    return None


@router.post("/query", response_model=AgentResponse)
def query_agent(payload: AgentQuery):
    user_message = payload.message

    # =========================================================
    # 0) Intention AVANT tout (small talk / hors périmètre)
    # =========================================================
    intent = classify_intent_rules(user_message)
    if intent == "ambigu":
        intent = classify_intent_llm_4cats(user_message)

    if intent == "small_talk":
        return AgentResponse(
            answer=(
                "Salut 🙂 Je peux t’aider à planifier un voyage : "
                "destination, meilleure période, météo actuelle, vols et hôtels. "
                "Tu veux partir où ?"
            ),
            decision={
                "intent": intent,
                "kb_used": False,
                "tools_called": [],
                "llm_decision": {"use_tools": False, "tools": [], "reason": "small_talk"}
            }
        )

    if intent == "hors_perimetre":
        return AgentResponse(
            answer=(
                "Je suis spécialisé dans la planification de voyage (météo, vols, hôtels, période idéale). "
                "Ta demande n’est pas dans ce périmètre. "
                "Pose-moi plutôt une question liée à un déplacement 🙂"
            ),
            decision={
                "intent": intent,
                "kb_used": False,
                "tools_called": [],
                "llm_decision": {"use_tools": False, "tools": [], "reason": "hors_perimetre"}
            }
        )

    # =========================================================
    # 1) Parsing route (origin/destination) & destination métier
    # =========================================================
    origin_city, dest_city = extract_route_cities(user_message)
    destination = dest_city or extract_destination(user_message)  # ex: "bangkok"
    kb_info = get_destination_info(destination)

    tools_called = []
    tool_results = {}

    # =========================================================
    # 2) Décision LLM tool/no-tool
    # =========================================================
    llm_decision = decide_tools(
        user_message=user_message,
        destination=destination,
        kb_info=kb_info,
        available_tools=["weather", "flights", "hotels"]
    )

    # =========================================================
    # 2bis) OVERRIDES RULE-BASED (weather + flights + hotels)
    # =========================================================
    msg = user_message.lower()

    force_weather = any(k in msg for k in ["météo", "meteo", "temps", "aujourd", "actuel", "actuelle", "maintenant", "prévision", "prevision"])
    force_flights = any(k in msg for k in ["vol", "vols", "billet", "billets", "avion", "aéroport", "aeroport", "prix"])
    force_hotels = any(k in msg for k in ["hotel", "hôtel", "logement", "hébergement", "hebergement", "nuit", "nuits", "booking"])

    def _has_tool(decision: dict, tool_name: str) -> bool:
        return any(t.get("name") == tool_name for t in decision.get("tools", []))

    # WEATHER override
    if force_weather and destination:
        if not llm_decision.get("use_tools"):
            llm_decision["use_tools"] = True
            llm_decision["tools"] = [{"name": "weather", "params": {}}]
            llm_decision["reason"] = "Rule-based override: user asked for current weather"
        else:
            if not _has_tool(llm_decision, "weather"):
                llm_decision["tools"].append({"name": "weather", "params": {}})
                llm_decision["reason"] = (llm_decision.get("reason", "") + " + weather override").strip()

    # FLIGHTS override
    if force_flights and destination:
        if not llm_decision.get("use_tools"):
            llm_decision["use_tools"] = True
            llm_decision["tools"] = [{"name": "flights", "params": {}}]
            llm_decision["reason"] = "Rule-based override: user asked for flights/prices"
        else:
            if not _has_tool(llm_decision, "flights"):
                llm_decision["tools"].append({"name": "flights", "params": {}})
                llm_decision["reason"] = (llm_decision.get("reason", "") + " + flights override").strip()

    # HOTELS override
    if force_hotels and destination:
        if not llm_decision.get("use_tools"):
            llm_decision["use_tools"] = True
            llm_decision["tools"] = [{"name": "hotels", "params": {}}]
            llm_decision["reason"] = "Rule-based override: user asked for hotels/accommodation"
        else:
            if not _has_tool(llm_decision, "hotels"):
                llm_decision["tools"].append({"name": "hotels", "params": {}})
                llm_decision["reason"] = (llm_decision.get("reason", "") + " + hotels override").strip()

    # =========================================================
    # 3) Exécuter les tools décidés
    # =========================================================
    if llm_decision.get("use_tools") and destination:
        for tool in llm_decision.get("tools", []):
            name = tool.get("name")
            params = tool.get("params") or {}

            city_for_tool = normalize_city_for_tool(destination)

            try:
                if name == "weather":
                    clarification = need_clarification_for_weather(destination)
                    if clarification:
                        return AgentResponse(
                            answer=clarification,
                            decision={
                                "intent": intent,
                                "destination": destination,
                                "kb_used": bool(kb_info),
                                "tools_called": tools_called,
                                "llm_decision": {
                                    "use_tools": False,
                                    "tools": [],
                                    "reason": f"Missing parameters for weather: {clarification}"
                                }
                            }
                        )

                    resp = requests.post(
                        "http://127.0.0.1:8000/mcp/weather",
                        json={"city": city_for_tool},
                        timeout=20
                    )
                    resp.raise_for_status()
                    tool_results["weather"] = resp.json()
                    tools_called.append("weather_scraper")

                elif name == "hotels":
                    month = params.get("month", None) or extract_month_or_dates(user_message)
                    clarification = need_clarification_for_hotels(destination, month)
                    if clarification:
                        return AgentResponse(
                            answer=clarification,
                            decision={
                                "intent": intent,
                                "destination": destination,
                                "kb_used": bool(kb_info),
                                "tools_called": tools_called,
                                "llm_decision": {
                                    "use_tools": False,
                                    "tools": [],
                                    "reason": f"Missing parameters for hotels: {clarification}"
                                }
                            }
                        )

                    resp = requests.post(
                        "http://127.0.0.1:8000/mcp/hotels",
                        json={"city": destination, "month": month},
                        timeout=45
                    )
                    resp.raise_for_status()
                    tool_results["hotels"] = resp.json()
                    tools_called.append("hotel_scraper")

                elif name == "flights":
                    origin_city_fallback = origin_city
                    dest_city_fallback = dest_city or destination

                    origin_iata = get_airport_code(origin_city_fallback) if origin_city_fallback else None
                    dest_iata = get_airport_code(dest_city_fallback) if dest_city_fallback else None

                    month = params.get("month", None) or extract_month_or_dates(user_message)
                    clarification = need_clarification_for_flights(origin_iata, dest_iata, month)
                    if clarification:
                        return AgentResponse(
                            answer=clarification,
                            decision={
                                "intent": intent,
                                "destination": destination,
                                "kb_used": bool(kb_info),
                                "tools_called": tools_called,
                                "llm_decision": {
                                    "use_tools": False,
                                    "tools": [],
                                    "reason": f"Missing parameters for flights: {clarification}"
                                }
                            }
                        )

                    resp = requests.post(
                        "http://127.0.0.1:8000/mcp/flights",
                        json={"from": origin_iata, "to": dest_iata, "month": month},
                        timeout=45
                    )
                    resp.raise_for_status()
                    tool_results["flights"] = resp.json()
                    tools_called.append("flight_scraper")

            except Exception as e:
                tool_results[f"{name}_error"] = str(e)

    # =========================================================
    # 4) Réponse finale via LLM
    # =========================================================
    final_answer = generate_answer(
        user_message=user_message,
        destination=destination,
        kb_info=kb_info,
        tool_results=tool_results if tool_results else None
    )

    # =========================================================
    # 5) Retour
    # =========================================================
    return AgentResponse(
        answer=final_answer,
        decision={
            "intent": intent,
            "destination": destination,
            "kb_used": bool(kb_info),
            "tools_called": tools_called,
            "llm_decision": llm_decision
        }
    )
