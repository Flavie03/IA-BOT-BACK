KB = {
    "destinations": {
        "lisbonne": {
            "best_periods": ["mars", "avril", "mai"],
            "climate": "doux et ensoleillé",
            "tips": [
                "Ville très marchable",
                "Transports publics abordables",
                "Printemps idéal pour éviter la foule"
            ]
        },
        "paris": {
            "best_periods": ["mai", "juin", "septembre"],
            "climate": "tempéré",
            "tips": [
                "Éviter août pour les fermetures",
                "Beaucoup de musées gratuits certains jours",
                "Printemps et automne plus agréables"
            ]
        },
        "rome": {
            "best_periods": ["avril", "mai", "septembre", "octobre"],
            "climate": "méditerranéen",
            "tips": [
                "Été très chaud",
                "Beaucoup de sites à pied",
                "Réserver les monuments à l’avance"
            ]
        },
        "madrid": {
            "best_periods": ["avril", "mai", "septembre"],
            "climate": "sec et chaud",
            "tips": [
                "Été caniculaire",
                "Ville animée toute l’année",
                "Musées majeurs concentrés"
            ]
        },
        "barcelone": {
            "best_periods": ["mai", "juin", "septembre"],
            "climate": "méditerranéen",
            "tips": [
                "Mélange plage et culture",
                "Éviter août pour la foule",
                "Transports très efficaces"
            ]
        },
        "bangkok": {
            "best_periods": ["novembre", "décembre", "janvier", "février"],
            "climate": "tropical",
            "tips": [
                "Éviter la saison des pluies",
                "Ville très dense",
                "Climatisation omniprésente"
            ]
        }
    }
}
def get_destination_info(destination: str):
    if not destination:
        return None
    return KB["destinations"].get(destination.lower())
