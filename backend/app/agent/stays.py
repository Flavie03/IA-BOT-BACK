# backend/app/agent/stays.py

STAYS = {
    # slug Kayak + pid Kayak
    "bangkok": {"slug": "Bangkok,Province-de-Bangkok,Thailande", "pid": "18056"},
    "paris": {"slug": "Paris,Ile-de-France,France", "pid": "36014"},
    "lisbonne": {"slug": "Lisbonne,Region-de-Lisbonne,Portugal", "pid": "2172"},
    "rome": {"slug": "Rome,Latium,Italie", "pid": "25465"},
    "madrid": {"slug": "Madrid,Communaute-de-Madrid,Espagne", "pid": "32213"},
    "barcelone": {"slug": "Barcelone,Catalogne,Espagne", "pid": "22567"},
}

def get_stay_location(city: str):
    """
    Retourne dict {slug, pid} ou None
    """
    if not city:
        return None
    return STAYS.get(city.lower())
