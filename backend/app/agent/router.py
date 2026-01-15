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

# Un petit parsing pour les mois yc
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
    """
    Extrait (origin_city, destination_city) depuis une phrase type:
    - "de Paris à Bangkok"
    - "de Paris a Bangkok"
    - "depuis Paris vers Bangkok"
    - "Paris -> Bangkok"
    Retourne (None, None) si non trouvé.
    """
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
    """
    Retourne:
    - 'YYYY-MM' si on détecte un mois (fr) ou un format YYYY-MM
    - 'YYYY-MM-DD/YYYY-MM-DD' si on détecte un range de dates
    - None sinon
    """
    m = message.lower().strip()

    # dates explicites: 2026-01-30/2026-02-20
    match = re.search(r"\b\d{4}-\d{2}-\d{2}/\d{4}-\d{2}-\d{2}\b", m)
    if match:
        return match.group(0)

    # mois en français
    for fr_month, mm in MONTHS_FR_TO_NUM.items():
        if fr_month in m:
            year_match = re.search(r"\b(20\d{2})\b", m)
            yyyy = year_match.group(1) if year_match else str(date.today().year)
            return f"{yyyy}-{mm}"

    # format YYYY-MM
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

    # Destination utilisée pour KB : on prend dest_city si trouvée
    destination = dest_city or extract_destination(user_message)
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
    # 2bis) PATCH: override rule-based si le user parle de vols/prix/billets
    # (sinon le LLM peut choisir use_tools=false et halluciner des prix)
    # =========================================================
    msg = user_message.lower()
    force_flights = any(k in msg for k in ["vol", "vols", "billet", "billets", "avion", "aéroport", "aeroport", "prix"])

    if force_flights and destination:
        # si le LLM n'a pas demandé flights, on force
        has_flights = any(t.get("name") == "flights" for t in llm_decision.get("tools", []))
        if not llm_decision.get("use_tools") or not has_flights:
            llm_decision["use_tools"] = True
            llm_decision["tools"] = [{"name": "flights", "params": {}}]
            llm_decision["reason"] = "Rule-based override: user asked for flights/prices"

    # =========================================================
    # 3) Exécuter les tools décidés
    # =========================================================
    if llm_decision.get("use_tools") and destination:
        for tool in llm_decision.get("tools", []):
            name = tool.get("name")
            params = tool.get("params") or {}

            # normalisation "city" pour weather/hotels
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
                    month = params.get("month", None) or extract_month_or_dates(user_message)
                    resp = requests.post(
                        "http://127.0.0.1:8000/mcp/hotels",
                        json={"city": city_for_tool, "month": month},
                        timeout=30
                    )
                    resp.raise_for_status()
                    tool_results["hotels"] = resp.json()
                    tools_called.append("hotel_scraper")

                elif name == "flights":
                    # ---- IATA mapping ----
                    origin_city_fallback = origin_city  # ex: "paris" si phrase "de paris à bangkok"
                    dest_city_fallback = dest_city or destination  # ex: "bangkok"

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
    # (IMPORTANT: le prompt doit éviter d'inventer des prix si flights absent)
    # =========================================================
    final_answer = generate_answer(
        user_message=user_message,
        destination=destination,
        kb_info=kb_info,
        tool_results=tool_results if tool_results else None
    )

    # =========================================================
    # 5) Retour (traçable pour la soutenance)
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
