import json
from datetime import datetime
from pathlib import Path

from bs4 import BeautifulSoup
from pydantic import ValidationError

from .models import Offer

REMOTIVE_URL = "https://remotive.com/api/remote-jobs"


def parse_remotive(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
        raise ValueError("Format Remotive inattendu")
    offers, invalid = [], 0
    for job in payload["jobs"]:
        try:
            offers.append(Offer(source="Remotive", source_id=str(job["id"]), title=job["title"],
                company=job["company_name"], location=job.get("candidate_required_location") or "Unknown",
                published_on=datetime.fromisoformat(job["publication_date"].replace("Z", "+00:00")).date(),
                url=job["url"], description=BeautifulSoup(job["description"], "html.parser").get_text(" ", strip=True)))
        except (KeyError, ValueError, TypeError, ValidationError):
            invalid += 1
    if invalid and not offers:
        raise ValueError("Aucune offre Remotive valide : vérifier le format de la source")
    return offers, invalid


def collect(client):
    # Une seule requête par exécution ; pas de visite des pages des offres.
    response = client.get(REMOTIVE_URL, params={"category": "software-dev"})
    response.raise_for_status()
    return parse_remotive(response.json())


def fixture_offers():
    from datetime import date
    return [Offer(source="Demo", source_id="1", title="Stage Python backend", company="Exemple Logiciels",
                  location="Canada", published_on=date.today(), url="https://example.com/stage-python",
                  description="Stage rémunéré Python FastAPI SQL et tests pytest au Canada."),
            Offer(source="Demo", source_id="2", title="Senior Sales Manager", company="Exemple Ventes",
                  location="United States", published_on=date.today(), url="https://example.com/sales",
                  description="Senior sales role, five years of experience.")]
