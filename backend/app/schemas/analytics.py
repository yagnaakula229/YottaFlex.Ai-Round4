from pydantic import BaseModel


class DashboardSummary(BaseModel):
    total_transactions: int
    total_alerts: int
    alerts_by_priority: dict[str, int]
    open_cases: int
    suspicious_transactions: int
    account_risk_distribution: dict[str, int]
    analyst_dispositions: dict[str, int]


class EvaluationMetrics(BaseModel):
    labeled_transactions: int
    true_positive: int
    false_positive: int
    true_negative: int
    false_negative: int
    precision: float
    recall: float
    f1_score: float
    false_positive_rate: float
    excluded_ambiguous: int
    top_100_precision: float
    top_100_labeled_transactions: int
    top_100_prediction_count: int
