from urllib.parse import urlsplit
import httpx
from .models import digest, normalize


class Tracker:
    def __init__(self, client):
        self.client = client

    def check(self):
        response = self.client.get("/openapi.json")
        response.raise_for_status()
        schemas = response.json()["components"]["schemas"]
        if "a_considerer" not in schemas["Status"]["enum"] or "external_id" not in schemas["ApplicationCreate"]["properties"]:
            raise ValueError("stage-tracker 2.1 et migration 0003 requis")
        response = self.client.get("/companies", params={"limit": 1})
        response.raise_for_status()

    def find_application(self, external_id):
        response = self.client.get("/applications", params={"external_id": external_id, "limit": 1})
        response.raise_for_status()
        items = response.json()
        return items[0] if items else None

    def company(self, offer):
        external_id = "agg-company:" + digest(normalize(offer.company) + "|" + normalize(offer.location))
        response = self.client.get("/companies", params={"external_id": external_id, "limit": 1})
        response.raise_for_status()
        if response.json():
            return response.json()[0]["id"]
        offset = 0
        while True:
            response = self.client.get("/companies", params={"q": offer.company, "offset": offset, "limit": 100})
            response.raise_for_status()
            items = response.json()
            for item in items:
                if normalize(item["name"]) == normalize(offer.company) and (not item.get("city") or normalize(item["city"]) == normalize(offer.location)):
                    return item["id"]
            if len(items) < 100:
                break
            offset += 100
        response = self.client.post("/companies", json={"name": offer.company, "city": offer.location, "external_id": external_id})
        if response.status_code == 409:
            response = self.client.get("/companies", params={"external_id": external_id, "limit": 1})
            response.raise_for_status()
            if not response.json():
                raise ValueError("Conflit entreprise non résolu")
            return response.json()[0]["id"]
        response.raise_for_status()
        return response.json()["id"]

    def import_offer(self, offer, evaluation, evaluator):
        existing = self.find_application(offer.external_id)
        if existing:
            return existing["id"]
        company_id = self.company(offer)
        notes = (f"Source : {offer.source} — {offer.url}\nLieu : {offer.location}\n"
                 f"Publication : {offer.published_on or 'inconnue'}\n"
                 f"Score ({evaluator}) : {evaluation.score}/100 — {evaluation.reason}\n"
                 f"Description : {offer.description[:7000]}")
        response = self.client.post("/applications", json={"company_id": company_id,
            "position": offer.title, "status": "a_considerer", "sent_on": None,
            "external_id": offer.external_id, "source_url": str(offer.url), "notes": notes[:10000]})
        if response.status_code == 409:
            existing = self.find_application(offer.external_id)
            if existing:
                return existing["id"]
        response.raise_for_status()
        return response.json()["id"]


def validate_tracker_url(url):
    parsed = urlsplit(url)
    if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", "/"):
        raise ValueError("STAGE_TRACKER_URL doit être une origine sans identifiants ni chemin")
    if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in ("localhost", "127.0.0.1", "::1")):
        raise ValueError("HTTPS requis sauf pour le développement local")
    if not parsed.hostname:
        raise ValueError("STAGE_TRACKER_URL invalide")
    return url.rstrip("/")
