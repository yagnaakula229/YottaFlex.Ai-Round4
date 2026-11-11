from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import GROUND_TRUTH_PATH
from app.models import Alert
from app.services.risk_engine import MAX_RISK_SCORE_BPS


def evaluate_ground_truth(session: Session, truth_path: Path = GROUND_TRUTH_PATH) -> dict:
    if not truth_path.is_file():
        raise FileNotFoundError(f"Ground-truth dataset was not found: {truth_path}")
    labels: dict[str, str] = {}
    with truth_path.open("r", encoding="utf-8") as truth_file:
        for line_number, line in enumerate(truth_file, start=1):
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid ground-truth JSON on line {line_number}.") from exc
            if record.get("entity_type") != "transaction":
                continue
            entity_id = record.get("entity_id")
            label = record.get("label")
            if not isinstance(entity_id, str) or label not in {"suspicious", "legitimate", "ambiguous"}:
                raise ValueError(f"Invalid transaction label record on line {line_number}.")
            if entity_id in labels:
                raise ValueError(f"Duplicate ground-truth transaction {entity_id} on line {line_number}.")
            labels[entity_id] = label

    contributions_by_transaction: dict[str, int] = {}
    for alert in session.scalars(select(Alert)):
        if alert.evidence_json.get("source") == "risk_engine":
            contributions_by_transaction[alert.triggering_transaction_id] = min(
                MAX_RISK_SCORE_BPS,
                contributions_by_transaction.get(alert.triggering_transaction_id, 0)
                + alert.score_contribution_bps,
            )
    ranked_predictions = sorted(
        contributions_by_transaction,
        key=lambda transaction_id: (-contributions_by_transaction[transaction_id], transaction_id),
    )[:100]
    top_labeled = [transaction_id for transaction_id in ranked_predictions if transaction_id in labels and labels[transaction_id] != "ambiguous"]
    top_100_precision = (
        sum(labels[transaction_id] == "suspicious" for transaction_id in top_labeled) / len(top_labeled)
        if top_labeled
        else 0.0
    )
    predicted_ids = set(contributions_by_transaction)

    eligible = {key: value for key, value in labels.items() if value in {"suspicious", "legitimate"}}
    tp = sum(label == "suspicious" and key in predicted_ids for key, label in eligible.items())
    fp = sum(label == "legitimate" and key in predicted_ids for key, label in eligible.items())
    tn = sum(label == "legitimate" and key not in predicted_ids for key, label in eligible.items())
    fn = sum(label == "suspicious" and key not in predicted_ids for key, label in eligible.items())
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    false_positive_rate = fp / (fp + tn) if fp + tn else 0.0
    return {
        "labeled_transactions": len(eligible),
        "true_positive": tp,
        "false_positive": fp,
        "true_negative": tn,
        "false_negative": fn,
        "precision": precision,
        "recall": recall,
        "f1_score": f1,
        "false_positive_rate": false_positive_rate,
        "excluded_ambiguous": sum(label == "ambiguous" for label in labels.values()),
        "top_100_precision": top_100_precision,
        "top_100_labeled_transactions": len(top_labeled),
        "top_100_prediction_count": len(ranked_predictions),
    }
