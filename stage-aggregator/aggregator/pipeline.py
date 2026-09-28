from .filtering import filter_reason
from .models import Offer, Evaluation
from .state import now


def run_pipeline(offers, config, profile, state, evaluator, tracker=None):
    for offer in offers:
        state.add(offer)
    result = {"collected": len(offers), "filtered": 0, "evaluated": 0, "selected": 0,
              "imported": 0, "reconciled": 0, "errors": 0, "offers": []}
    for row in state.pending():
        offer = Offer.model_validate_json(row["offer"])
        key = offer.fingerprint
        try:
            reason = filter_reason(offer, config)
            if reason:
                state.update(key, status="filtered", last_error=reason)
                result["filtered"] += 1
                continue
            if tracker:
                existing = tracker.find_application(offer.external_id)
                if existing:
                    # État local perdu ou réponse HTTP perdue : ne pas recréer/renotifier.
                    state.update(key, status="imported", application_id=existing["id"], notified_at=None if row["evaluation"] else now(), last_error=None)
                    result["reconciled"] += 1
                    continue
            if row["evaluation"]:
                evaluation = Evaluation.model_validate_json(row["evaluation"])
                evaluator_name = row["evaluator"]
            else:
                if result["evaluated"] >= config.max_evaluations:
                    continue
                result["evaluated"] += 1 # les tentatives échouées comptent dans le budget
                evaluation = evaluator.evaluate(offer, profile)
                evaluator_name = evaluator.name
                state.update(key, evaluation=evaluation.model_dump_json(), evaluator=evaluator_name, last_error=None)
            if evaluation.score < config.min_score:
                state.update(key, status="rejected")
                continue
            state.update(key, status="selected")
            result["selected"] += 1
            result["offers"].append({"title": offer.title, "company": offer.company, "url": str(offer.url),
                                     "source": offer.source, "score": evaluation.score, "reason": evaluation.reason,
                                     "evaluator": evaluator_name})
            if tracker:
                application_id = tracker.import_offer(offer, evaluation, evaluator_name)
                state.update(key, status="imported", application_id=application_id, last_error=None)
                result["imported"] += 1
        except Exception as exc:
            # Ne pas journaliser les réponses HTTP, en-têtes ou secrets.
            state.update(key, last_error=type(exc).__name__)
            result["errors"] += 1
    return result
