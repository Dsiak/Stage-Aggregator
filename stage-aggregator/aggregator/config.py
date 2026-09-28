from pathlib import Path
import tomllib
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: Literal["remotive", "fixture"] = "remotive"
    evaluator: Literal["rules", "anthropic"] = "rules"
    profile_path: str = "profile.example.txt"
    state_path: str = "state/aggregator.db"
    report_path: str = "reports/latest.json"
    min_score: int = Field(default=60, ge=0, le=100)
    max_evaluations: int = Field(default=10, ge=1, le=100)
    max_age_days: int = Field(default=30, ge=1, le=365)
    require_internship: bool = True
    exclude_unpaid: bool = True
    include_keywords: list[str] = Field(default_factory=lambda: ["python", "backend"])
    locations: list[str] = Field(default_factory=lambda: ["canada", "worldwide"])
    notify_every_days: int = Field(default=1, ge=1, le=30)

    @classmethod
    def load(cls, path):
        path = Path(path).resolve()
        data = tomllib.loads(path.read_text(encoding="utf-8-sig"))
        config = cls(**data)
        for name in ("profile_path", "state_path", "report_path"):
            setattr(config, name, str(path.parent / getattr(config, name)))
        return config
