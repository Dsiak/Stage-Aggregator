import re
from datetime import date, timedelta
from .models import normalize


def filter_reason(offer, config, today=None):
    today = today or date.today()
    text = normalize(offer.title + " " + offer.description)
    if offer.published_on and (offer.published_on > today or offer.published_on < today - timedelta(days=config.max_age_days)):
        return "Date hors fenêtre"
    if config.require_internship and not re.search(r"\b(stage|stagiaire|intern|internship|co-op|coop)\b", text):
        return "Pas de stage explicite"
    if config.exclude_unpaid and re.search(r"\b(unpaid|non remunere|non remuneree|benevolat|volunteer)\b", text):
        return "Non rémunéré explicitement"
    if config.include_keywords and not any(normalize(k) in text for k in config.include_keywords):
        return "Aucun mot-clé pertinent"
    location = normalize(offer.location)
    if config.locations and not any(normalize(place) in location for place in config.locations):
        return "Localisation hors critères ou inconnue"
    return None
