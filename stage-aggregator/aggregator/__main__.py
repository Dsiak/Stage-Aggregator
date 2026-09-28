import argparse
import json
import os
from contextlib import ExitStack
from pathlib import Path

import httpx
from filelock import FileLock

from .config import Config
from .evaluation import AnthropicEvaluator, RulesEvaluator
from .notify import notify_pending
from .pipeline import run_pipeline
from .sources import collect, fixture_offers
from .state import State
from .tracker import Tracker, validate_tracker_url


def main():
    parser = argparse.ArgumentParser(description="Agrégateur de stages — indépendant de stage-tracker")
    parser.add_argument("--config", default="config.toml")
    parser.add_argument("--demo", action="store_true", help="Offres fictives, score par règles, sans réseau ni état durable")
    parser.add_argument("--sync", action="store_true", help="Importer les offres retenues via HTTP")
    parser.add_argument("--notify", action="store_true", help="Envoyer le résumé des imports en attente par SMTP")
    args = parser.parse_args()
    if args.demo and (args.sync or args.notify):
        parser.error("--demo ne peut pas importer ni envoyer de courriel")
    config = Config.load(args.config)
    if args.demo:
        config.evaluator = "rules"
    profile = Path(config.profile_path).read_text(encoding="utf-8-sig")
    path = Path(config.state_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Verrou interprocessus local ; GitHub Actions ajoute sa propre exclusion mutuelle.
    with FileLock(str(path) + ".lock", timeout=0), ExitStack() as stack:
        source_client = stack.enter_context(httpx.Client(timeout=30, follow_redirects=False,
                                   headers={"User-Agent": "StageAggregator/1.0 personal-study-project"}))
        state = State(":memory:" if args.demo else str(path))
        stack.callback(state.close)
        tracker = None
        if args.sync:
            base_url = validate_tracker_url(os.environ.get("STAGE_TRACKER_URL", ""))
            key = os.environ.get("STAGE_TRACKER_API_KEY", "")
            if not key:
                raise ValueError("STAGE_TRACKER_API_KEY requis")
            client = stack.enter_context(httpx.Client(base_url=base_url, timeout=30, follow_redirects=False,
                                                      headers={"X-API-Key": key}))
            tracker = Tracker(client)
            tracker.check()
        evaluator = (RulesEvaluator() if config.evaluator == "rules" else
                     AnthropicEvaluator(source_client, os.getenv("ANTHROPIC_API_KEY"), os.getenv("ANTHROPIC_MODEL")))
        if args.demo or config.source == "fixture":
            offers, invalid = fixture_offers(), 0
        else:
            offers, invalid = collect(source_client)
        result = run_pipeline(offers, config, profile, state, evaluator, tracker)
        result["invalid_source_rows"] = invalid
        result["notified"] = 0
        if args.notify:
            try:
                result["notified"] = notify_pending(state, config.notify_every_days)
            except Exception as exc:
                result["errors"] += 1
                result["notification_error"] = type(exc).__name__
        report = Path(config.report_path)
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps({key: value for key, value in result.items() if key != "offers"}))
        return 1 if result["errors"] else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        # Messages des exceptions de bibliothèques susceptibles de contenir des secrets.
        print("Échec de l'exécution : " + type(exc).__name__ + ". Vérifier configuration, accès et journal d'état.")
        raise SystemExit(1)
