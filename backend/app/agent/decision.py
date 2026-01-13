def needs_weather_info(message: str) -> bool:
    keywords = ["météo", "temps", "aujourd'hui", "actuel", "maintenant"]
    message = message.lower()

    return any(word in message for word in keywords)
