import os
import json
import re
import requests
from typing import Optional, Dict, Any, List

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:1.5b")
OLLAMA_TEMPERATURE = float(os.getenv("OLLAMA_TEMPERATURE", "0.2"))
OLLAMA_TIMEOUT_SECONDS = int(os.getenv("OLLAMA_TIMEOUT_SECONDS", "120"))
OLLAMA_MAX_TOKENS = int(os.getenv("OLLAMA_MAX_TOKENS", "220"))  # ~6-10 lignes


def _ollama_chat(system_prompt: str, user_prompt: str) -> str:
    url = f"{OLLAMA_BASE_URL}/api/chat"

    strict_system = (
        system_prompt.strip()
        + "\n\nIMPORTANT:\n"
          "- Réponds UNIQUEMENT avec la réponse finale.\n"
          "- Ne fournis jamais d'analyse, de raisonnement, ni d'étapes.\n"
          "- Pas de contenu caché, pas de 'thinking'.\n"
    )

    payload = {
        "model": OLLAMA_MODEL,
        "stream": False,
        "messages": [
            {"role": "system", "content": strict_system},
            {"role": "user", "content": user_prompt},
        ],
        "options": {
            "temperature": OLLAMA_TEMPERATURE,
            "num_predict": OLLAMA_MAX_TOKENS,
        },
    }

    try:
        r = requests.post(url, json=payload, timeout=OLLAMA_TIMEOUT_SECONDS)
        r.raise_for_status()
        data = r.json()
        return (data.get("message", {}).get("content", "") or "").strip()
    except requests.RequestException as e:
        raise RuntimeError(f"Ollama request failed: {e}") from e
    except ValueError as e:
        raise RuntimeError(f"Ollama returned invalid JSON: {e}") from e


def _extract_json_object(text: str) -> Dict[str, Any]:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)

    try:
        return json.loads(text)
    except Exception:
        pass

    m = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not m:
        raise ValueError(f"No JSON object found in LLM output: {text[:200]}...")
    return json.loads(m.group(0))


# --- Ancienne classification (optionnelle) ---
def classify_intent(message: str) -> str:
    system = (
        "Tu es un classificateur d'intention utilisateur.\n"
        "Réponds STRICTEMENT par un seul mot en minuscules: social OU travel.\n"
        "travel = voyage/transport/destination/période/météo/vol/hôtel/budget.\n"
        "Aucun autre texte."
    )
    out = _ollama_chat(system, f"Message utilisateur: {message}").lower().strip()
    return "travel" if "travel" in out else "social"


# --- Nouvelle classification recommandée (4 catégories) ---
def classify_intent_llm_4cats(message: str) -> str:
    system = (
        "Tu es un classificateur d'intention.\n"
        "Tu dois répondre STRICTEMENT par UNE SEULE catégorie parmi:\n"
        "- small_talk\n"
        "- intent_metier\n"
        "- hors_perimetre\n"
        "- ambigu\n\n"
        "Définitions:\n"
        "small_talk: salutations, remerciements, politesse, conversation légère.\n"
        "intent_metier: planification voyage (destination, période, météo, vols, hôtels, budget, itinéraire).\n"
        "hors_perimetre: tout le reste (math, code, questions générales hors voyage).\n"
        "ambigu: trop court ou manque d'infos pour décider.\n\n"
        "Règles:\n"
        "- Réponds uniquement par le mot exact de la catégorie (sans ponctuation).\n"
        "- Ne justifie pas.\n"
    )

    out = _ollama_chat(system, f"Message: {message}").strip().lower()
    allowed = {"small_talk", "intent_metier", "hors_perimetre", "ambigu"}

    if out in allowed:
        return out

    for cat in allowed:
        if cat in out:
            return cat

    return "ambigu"


def decide_tools(
    user_message: str,
    destination: Optional[str],
    kb_info: Optional[Dict[str, Any]],
    available_tools: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Décide s'il faut appeler un tool MCP et avec quels paramètres.

    Tools MCP existants (server.py):
    - weather: POST /mcp/weather  payload: {"city": "<CityName>"}
    - flights: POST /mcp/flights payload: {"from": "<origin>", "to": "<destination>", "month": "<month>"}
    - hotels: POST /mcp/hotels   payload: {"city": "<CityName>", "month": "<month>"}
    """
    if available_tools is None:
        available_tools = ["weather", "flights", "hotels"]

    system = (
        "Tu es le module de décision d'un agent de voyage.\n"
        "Tu dois répondre STRICTEMENT en JSON valide (aucun texte autour).\n\n"
        "RÈGLES IMPÉRATIVES:\n"
        "- Si le message parle de vols / billets / avion / prix => use_tools=true et tool='flights'.\n"
        "- Si le message parle de météo actuelle => use_tools=true et tool='weather'.\n"
        "- Si le message parle d'hôtels/logement/prix hôtel => use_tools=true et tool='hotels'.\n"
        "- Si la question porte uniquement sur période/climat/conseils et que la KB contient la réponse => use_tools=false.\n"
        "- Si destination inconnue => use_tools=false.\n"
        "- Si mois/dates manquent, mets month=null.\n"
        "- Pour flights, si origine manque, mets from=null.\n\n"
        f"TOOLS POSSIBLES: {available_tools}\n\n"
        "FORMAT JSON EXACT:\n"
        '{ "use_tools": true|false, "tools": [{"name": "weather|flights|hotels", "params": {...}}], "reason": "..." }'
    )

    # Contexte allégé (plus rapide)
    context = {
        "user_message": user_message,
        "destination": destination,
        "kb_available": bool(kb_info),
        "available_tools": available_tools,
    }

    user_prompt = (
        "Contexte (JSON):\n"
        f"{json.dumps(context, ensure_ascii=False)}\n\n"
        "Décide maintenant et retourne uniquement le JSON."
    )

    raw = _ollama_chat(system, user_prompt)
    decision = _extract_json_object(raw)

    use_tools = bool(decision.get("use_tools", False))
    tools = decision.get("tools", [])
    reason = decision.get("reason", "No reason provided")

    if not isinstance(tools, list):
        tools = []

    if not destination:
        return {"use_tools": False, "tools": [], "reason": "No destination detected"}

    allowed = {t.lower() for t in available_tools}
    cleaned_tools = []

    for t in tools:
        name = (t.get("name") or "").lower().strip()
        params = t.get("params") or {}

        if name not in allowed:
            continue

        if name == "weather":
            cleaned_tools.append({"name": "weather", "params": {"city": destination}})
        elif name == "hotels":
            cleaned_tools.append({"name": "hotels", "params": {"city": destination, "month": params.get("month", None)}})
        elif name == "flights":
            cleaned_tools.append({"name": "flights", "params": {"from": params.get("from", None), "to": destination, "month": params.get("month", None)}})

    if not use_tools:
        cleaned_tools = []

    return {"use_tools": use_tools, "tools": cleaned_tools, "reason": reason}


def _safe_get(d: Optional[Dict[str, Any]], *keys, default=None):
    cur = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def generate_answer(
    user_message: str,
    destination: Optional[str],
    kb_info: Optional[Dict[str, Any]],
    tool_results: Optional[Dict[str, Any]],
) -> str:
    """
    Génère la réponse finale.
    - Anti-hallucination prix: si aucun tool_results.flights => ne donne aucun prix.
    - Ajoute Source (url) si disponible.
    - Formulation: 'de ORIGINE à DESTINATION' (pas 'à Paris à Bangkok').
    """
    flights = _safe_get(tool_results, "flights", default=None) if tool_results else None
    weather = _safe_get(tool_results, "weather", default=None) if tool_results else None
    hotels = _safe_get(tool_results, "hotels", default=None) if tool_results else None

    system = (
        "Tu es un assistant de planification de voyage.\n"
        "Réponds de manière utile, claire et actionnable.\n"
        "6 à 10 lignes maximum.\n"
        "Ne mentionne jamais 'KB', 'MCP', 'tool', 'outil', 'scraping'.\n\n"
        "RÈGLES ANTI-HALLUCINATION:\n"
        "- Si aucune donnée de vol n'est fournie (tool_results.flights absent), ne donne AUCUN prix.\n"
        "- Si des données de vol sont fournies, utilise uniquement ces données pour le prix et les dates.\n"
        "- Si une URL source est fournie, ajoute une ligne 'Source: <url>' à la fin.\n"
        "- Quand tu exprimes un itinéraire, écris 'de ORIGINE à DESTINATION'.\n"
    )

    # Contexte compact
    context = {
        "user_message": user_message,
        "destination": destination,
        "kb_info": kb_info,
        "tool_results": {
            "flights": flights,
            "weather": weather,
            "hotels": hotels,
        }
    }

    user_prompt = (
        "Voici le contexte JSON à utiliser:\n"
        f"{json.dumps(context, ensure_ascii=False, indent=2)}\n\n"
        "Rédige la meilleure réponse possible pour l'utilisateur."
    )

    return _ollama_chat(system, user_prompt)
