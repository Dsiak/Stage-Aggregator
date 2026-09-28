import hashlib
import re
import unicodedata
from datetime import date
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


def normalize(text):
    text = unicodedata.normalize("NFKD", text.casefold())
    return re.sub(r"\s+", " ", "".join(c for c in text if not unicodedata.combining(c))).strip()


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


class Offer(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    source: str = Field(min_length=1, max_length=100)
    source_id: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=200)
    company: str = Field(min_length=1, max_length=200)
    location: str = Field(min_length=1, max_length=200)
    published_on: date | None = None
    url: HttpUrl
    description: str = Field(min_length=1, max_length=100000)

    @property
    def fingerprint(self):
        # Conservateur : une republication du même poste au même lieu reste une offre.
        return digest("|".join(normalize(x) for x in (self.title, self.company, self.location)))

    @property
    def external_id(self):
        return "agg:" + self.fingerprint


class Evaluation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    score: int = Field(ge=0, le=100)
    reason: str = Field(min_length=1, max_length=500)
