import os
import json
import re
import requests
from typing import Optional, Dict, Any, List

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:1.5b")
OLLAMA_TEMPERATURE = float(os.getenv("OLLAMA_TEMPERATURE", "0.2"))
OLLAMA_TIMEOUT_SECONDS = int(os.getenv("OLLAMA_TIMEOUT_SECONDS", "120"))


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
        "options": {"temperature": OLLAMA_TEMPERATURE},
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
    # Enlève ```json ... ```
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
    """
    Classifie le message dans UNE SEULE catégorie parmi:
    - small_talk : salutations, remerciements, small talk, discussion légère
    - intent_metier : questions liées à la planification de voyage/transport
    - hors_perimetre : questions sans rapport (math, dev, politique, etc.)
    - ambigu : pas assez d'info / message trop vague
    Retourne uniquement l'un de ces 4 mots.
    """
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

    # fallback robuste si le modèle renvoie une phrase
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

    JSON attendu:
    {
      "use_tools": true/false,
      "tools": [
        {"name": "weather|flights|hotels", "params": {...}}
      ],
      "reason": "..."
    }
    """
    if available_tools is None:
        available_tools = ["weather", "flights", "hotels"]

    system = (
        "Tu es le module de décision d'un agent de voyage.\n"
        "Ta mission: décider si des données temps réel sont nécessaires.\n"
        "Tu dois répondre STRICTEMENT en JSON valide (pas de texte autour).\n\n"
        "RÈGLES:\n"
        "- Si la KB suffit: use_tools=false.\n"
        "- Si l'utilisateur demande météo actuelle => tool weather.\n"
        "- Si l'utilisateur demande prix / horaires / disponibilité vols => tool flights.\n"
        "- Si l'utilisateur demande hôtels / prix / disponibilité hébergements => tool hotels.\n"
        "- Si destination inconnue => use_tools=false.\n"
        "- N'invente pas de ville.\n"
        "- Si l'utilisateur ne donne pas de mois, mets month=null.\n"
        "- Pour flights, si l'utilisateur ne donne pas d'origine, mets from=null.\n\n"
        f"TOOLS POSSIBLES: {available_tools}\n\n"
        "FORMAT JSON EXACT:\n"
        "{\n"
        '  "use_tools": true|false,\n'
        '  "tools": [\n'
        '    {"name": "weather|flights|hotels", "params": { ... }}\n'
        "  ],\n"
        '  "reason": "string courte"\n'
        "}\n"
    )

    context = {
        "user_message": user_message,
        "destination": destination,  # ex: "lisbonne"
        "kb_info_available": bool(kb_info),
        "kb_info": kb_info,
        "available_tools": available_tools,
        "expected_params_by_tool": {
            "weather": {"city": "string"},
            "flights": {"from": "string|null", "to": "string", "month": "string|null"},
            "hotels": {"city": "string", "month": "string|null"},
        },
        "note": (
            "La destination est en minuscule (ex: lisbonne). "
            "Le backend normalise pour le tool (ex: Lisbon). "
            "Ne change pas la destination, réutilise-la."
        ),
    }

    user_prompt = (
        "Contexte (JSON):\n"
        f"{json.dumps(context, ensure_ascii=False, indent=2)}\n\n"
        "Décide maintenant et retourne uniquement le JSON."
    )

    raw = _ollama_chat(system, user_prompt)
    decision = _extract_json_object(raw)

    # Validation + fallback safe
    use_tools = bool(decision.get("use_tools", False))
    tools = decision.get("tools", [])
    reason = decision.get("reason", "No reason provided")

    if not isinstance(tools, list):
        tools = []

    # Si destination absente, on force no-tool (sécurité)
    if not destination:
        return {"use_tools": False, "tools": [], "reason": "No destination detected"}

    # Filtre outils inconnus
    allowed = {t.lower() for t in available_tools}
    cleaned_tools = []
    for t in tools:
        name = (t.get("name") or "").lower().strip()
        params = t.get("params") or {}
        if name not in allowed:
            continue

        # Nettoyage params selon tool
        if name == "weather":
            cleaned_tools.append({"name": "weather", "params": {"city": destination}})
        elif name == "hotels":
            month = params.get("month", None)
            cleaned_tools.append({"name": "hotels", "params": {"city": destination, "month": month}})
        elif name == "flights":
            origin = params.get("from", None)
            month = params.get("month", None)
            cleaned_tools.append({"name": "flights", "params": {"from": origin, "to": destination, "month": month}})

    if not use_tools:
        cleaned_tools = []

    return {
        "use_tools": use_tools,
        "tools": cleaned_tools,
        "reason": reason
    }


def generate_answer(
    user_message: str,
    destination: Optional[str],
    kb_info: Optional[Dict[str, Any]],
    tool_results: Optional[Dict[str, Any]],
) -> str:
    system = (
        "Tu es un agent de planification de voyage.\n"
        "Objectif: réponse utile, claire, actionnable.\n"
        "Contraintes:\n"
        "1) Utilise les infos de la KB si disponibles.\n"
        "2) Utilise les résultats live si fournis.\n"
        "3) Si info manquante, dis-le et propose la prochaine étape.\n"
        "4) Réponse concise: 6 à 10 lignes max.\n"
        "5) Ne mentionne jamais 'KB', 'MCP', 'tool', 'outil', 'scraping'.\n"
    )

    context = {
        "user_message": user_message,
        "destination": destination,
        "kb_info": kb_info,
        "tool_results": tool_results,
    }

    user_prompt = (
        "Voici le contexte (JSON) à utiliser pour répondre:\n"
        f"{json.dumps(context, ensure_ascii=False, indent=2)}\n\n"
        "Rédige la meilleure réponse possible pour l'utilisateur."
    )

    return _ollama_chat(system, user_prompt)
