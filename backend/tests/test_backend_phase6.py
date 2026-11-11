import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from alembic import command
from alembic.config import Config
from app.api import analytics as analytics_api
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.core.config import PROJECT_ROOT
from app.database.init_db import upgrade_database
from app.database.session import get_session, make_engine
from app.main import app
from app.models import (
    Account,
    Alert,
    AuditEvent,
    AnalystAction,
    Case,
    CaseAlert,
    Customer,
    CustomerAccount,
    CustomerDevice,
    Device,
    RiskRule,
    Transaction,
    TransferLink,
)
from app.services.case_service import group_related_alerts, record_analyst_action
from app.services.data_quality import validate_dataset
from app.services.evaluation_service import evaluate_ground_truth
from app.services.link_analysis import analyze_account_links
from app.services.risk_engine import (
    EvaluationContext,
    RuleDefinition,
    aggregate_score,
    evaluate_transaction,
    priority_for_score,
)
from app.services.risk_service import evaluate_transactions
from app.services.seed_data import SeedConfig, generate_dataset

UTC = timezone.utc
NOW = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
SEED_CONFIG = SeedConfig(
    customers=10,
    accounts=14,
    merchants=5,
    devices=6,
    transactions=100,
    alerts=10,
)


@pytest.fixture
def backend(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'phase6.db'}")
    upgrade_database(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    truth_path = tmp_path / "truth.jsonl"
    with factory() as session:
        generate_dataset(session, SEED_CONFIG, truth_path)

    def override_session():
        with factory() as session:
            yield session

    previous_override = app.dependency_overrides.get(get_session)
    had_previous_override = get_session in app.dependency_overrides
    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            yield client, engine, factory, truth_path
    finally:
        if had_previous_override:
            app.dependency_overrides[get_session] = previous_override
        else:
            app.dependency_overrides.pop(get_session, None)
        engine.dispose()


def _transaction(**overrides):
    values = {
        "transaction_id": "TXN-2026-90000001",
        "account_id": "ACC--01",
        "device_id": "DEV-000001",
        "status": "posted",
        "transaction_at": NOW,
        "debit_minor": 1000,
        "credit_minor": 0,
        "account_status_at_posting": "open",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _rule(key: str, contribution: int = 2500, parameters=None):
    return RuleDefinition(
        rule_id=f"RUL-{key}-V01",
        rule_key=key,
        version=1,
        parameters=parameters or {},
        contribution_bps=contribution,
    )


def test_each_risk_rule_has_independent_deterministic_evidence():
    cases = (
        (
            _rule("velocity_spike", parameters={"window_minutes": 60, "minimum_count": 5}),
            _transaction(),
            EvaluationContext(
                prior_transactions=[
                    _transaction(transaction_id=f"TXN-2026-{i:08d}", transaction_at=NOW - timedelta(minutes=i))
                    for i in range(1, 5)
                ]
            ),
            "transaction_count",
        ),
        (_rule("new_device"), _transaction(), EvaluationContext(device_is_new=True), "device_id"),
        (
            _rule("circular_transfer"),
            _transaction(transaction_id="TXN-SOURCE"),
            EvaluationContext(
                transfers=[
                    SimpleNamespace(
                        transfer_id="TRF-1",
                        source_transaction_id="TXN-SOURCE",
                        destination_transaction_id="TXN-B",
                        source_account_id="ACC-A",
                        destination_account_id="ACC-B",
                        status="reconciled",
                    ),
                    SimpleNamespace(
                        transfer_id="TRF-2",
                        source_transaction_id="TXN-C",
                        destination_transaction_id="TXN-D",
                        source_account_id="ACC-B",
                        destination_account_id="ACC-C",
                        status="reconciled",
                    ),
                    SimpleNamespace(
                        transfer_id="TRF-3",
                        source_transaction_id="TXN-E",
                        destination_transaction_id="TXN-F",
                        source_account_id="ACC-C",
                        destination_account_id="ACC-A",
                        status="reconciled",
                    ),
                ]
            ),
            "transfer_ids",
        ),
        (
            _rule("dormant_reactivation", parameters={"dormant_days": 90}),
            _transaction(),
            EvaluationContext(prior_activity_at=NOW - timedelta(days=120)),
            "days_since_prior_activity",
        ),
        (
            _rule("high_value", parameters={"threshold_minor": 250_000}),
            _transaction(credit_minor=300_000),
            EvaluationContext(),
            "threshold_minor",
        ),
        (
            _rule("linked_suspicious"),
            _transaction(),
            EvaluationContext(related_alerts=[{"alert_id": "ALT-2026-000001"}]),
            "related_alerts",
        ),
    )
    for rule, transaction, context, evidence_key in cases:
        first = evaluate_transaction(transaction, [rule], context, evaluated_at=NOW)
        second = evaluate_transaction(transaction, [rule], context, evaluated_at=NOW)
        assert len(first) == 1
        assert first == second
        assert first[0].rule_id == rule.rule_id
        assert evidence_key in first[0].evidence
        assert first[0].explanation


def test_risk_engine_no_trigger_multi_rule_cap_and_priority():
    rules = [
        _rule("velocity_spike", parameters={"minimum_count": 5, "window_minutes": 60}),
        _rule("new_device"),
        _rule("high_value", parameters={"threshold_minor": 250_000}),
        _rule("dormant_reactivation"),
        _rule("linked_suspicious"),
    ]
    assert evaluate_transaction(_transaction(device_id=None), rules, EvaluationContext(), NOW) == []
    findings = evaluate_transaction(
        _transaction(credit_minor=300_000),
        [
            _rule("high_value", 3000, {"threshold_minor": 250_000}),
            _rule("new_device", 2500),
            _rule("linked_suspicious", 3000),
        ],
        EvaluationContext(device_is_new=True, related_alerts=[{"alert_id": "ALT-1"}]),
        NOW,
    )
    assert len(findings) == 3
    assert aggregate_score([finding.contribution_bps for finding in findings]) == 8500
    assert aggregate_score([7000, 5000]) == 10_000
    assert [priority_for_score(score) for score in (7500, 5000, 2500, 2499)] == [
        "P1",
        "P2",
        "P3",
        "P4",
    ]


def _add_high_value_transaction(session):
    account = session.scalar(select(Account).where(Account.status == "open").order_by(Account.account_id))
    last_balance = session.scalar(
        select(Transaction.closing_balance_minor)
        .where(Transaction.account_id == account.account_id, Transaction.status == "posted")
        .order_by(Transaction.transaction_at.desc())
        .limit(1)
    )
    last_time = session.scalar(
        select(Transaction.transaction_at)
        .where(Transaction.account_id == account.account_id, Transaction.status == "posted")
        .order_by(Transaction.transaction_at.desc())
        .limit(1)
    )
    at = max(last_time, NOW) + timedelta(seconds=1)
    transaction = Transaction(
        transaction_id="TXN-2026-90000002",
        account_id=account.account_id,
        transaction_type="deposit",
        status="posted",
        transaction_at=at,
        posted_at=at,
        currency=account.currency,
        debit_minor=0,
        credit_minor=300_000,
        opening_balance_minor=last_balance,
        closing_balance_minor=last_balance + 300_000,
        account_status_at_posting="open",
        created_at=at,
    )
    session.add(transaction)
    session.commit()
    return transaction


def test_risk_evaluation_creates_real_alerts_and_is_duplicate_safe(backend):
    _, _, factory, _ = backend
    with factory() as session:
        transaction = _add_high_value_transaction(session)
        first = evaluate_transactions(session, transaction_id=transaction.transaction_id)
        second = evaluate_transactions(session, transaction_id=transaction.transaction_id)
        alerts = session.scalars(
            select(Alert).where(Alert.triggering_transaction_id == transaction.transaction_id)
        ).all()
        assert first["transactions_evaluated"] == 1
        assert first["alerts_created"] >= 1
        assert second["alerts_created"] == 0
        assert len(alerts) == len({alert.rule_id for alert in alerts})
        assert all(alert.evidence_json["source"] == "risk_engine" for alert in alerts)
        assert all("evidence" in alert.evidence_json for alert in alerts)
        assert validate_dataset(session)["transaction_record"] == 101


def test_missing_risk_rule_is_rejected_by_foreign_key(backend):
    _, _, factory, _ = backend
    with factory() as session:
        transaction = session.scalar(select(Transaction).limit(1))
        at = transaction.transaction_at
        session.add(
            Alert(
                alert_id="ALT-TEST-MISSING-RULE",
                rule_id="RUL-NOT-REGISTERED-V01",
                triggering_transaction_id=transaction.transaction_id,
                status="new",
                priority="P4",
                score_contribution_bps=100,
                evidence_json={"source": "risk_engine"},
                detected_at=at,
                created_at=at,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


def test_transaction_alert_case_dashboard_and_openapi_apis(backend, monkeypatch, tmp_path):
    client, _, _, _ = backend
    listed = client.get("/api/transactions", params={"limit": 5, "status": "posted"})
    assert listed.status_code == 200
    assert listed.json()["total"] == 100
    assert len(listed.json()["items"]) == 5
    transaction_id = listed.json()["items"][0]["transaction_id"]
    assert client.get(f"/api/transactions/{transaction_id}").status_code == 200
    assert client.get("/api/transactions/TXN-MISSING").status_code == 404
    assert client.get("/api/accounts/ACC--01/transactions").status_code == 200
    assert client.get("/api/accounts/ACC-MISSING/transactions").status_code == 404

    alerts = client.get("/api/alerts", params={"limit": 3})
    assert alerts.status_code == 200
    alert_id = alerts.json()["items"][0]["alert_id"]
    priority = alerts.json()["items"][0]["priority"]
    filtered_alerts = client.get("/api/alerts", params={"priority": priority})
    assert all(item["priority"] == priority for item in filtered_alerts.json()["items"])
    assert client.get(f"/api/alerts/{alert_id}").status_code == 200
    assert client.get("/api/alerts/ALT-MISSING").status_code == 404

    cases = client.get("/api/cases")
    assert cases.status_code == 200
    case_id = cases.json()["items"][0]["case_id"]
    case_detail = client.get(f"/api/cases/{case_id}")
    assert case_detail.status_code == 200
    assert any(event["event_type"] == "case.created" for event in case_detail.json()["audit_events"])
    assert client.get("/api/cases/CASE-MISSING").status_code == 404
    summary = client.get("/api/dashboard/summary")
    assert summary.status_code == 200
    assert summary.json()["total_transactions"] == 100
    assert summary.json()["total_alerts"] == 10
    truth_path = tmp_path / "api-truth.jsonl"
    truth_record = {
        "truth_record_id": "GT-2026-000001",
        "dataset_version": "2026.1",
        "scenario_id": "SCN-2026-000001",
        "entity_type": "transaction",
        "entity_id": transaction_id,
        "label": "legitimate",
        "pattern_type": "baseline_synthetic",
        "expected_rule_ids": [],
        "rationale": "Temporary fixture label for the API evaluation test.",
        "split": "evaluation",
    }
    truth_path.write_text(json.dumps(truth_record) + "\n", encoding="utf-8")
    monkeypatch.setattr(
        analytics_api,
        "evaluate_ground_truth",
        lambda session: evaluate_ground_truth(session, truth_path),
    )
    evaluation = client.get("/api/analytics/evaluation")
    assert evaluation.status_code == 200
    assert evaluation.json()["labeled_transactions"] == 1
    assert evaluation.json()["excluded_ambiguous"] == 0
    assert {
        "precision",
        "recall",
        "f1_score",
        "false_positive_rate",
        "top_100_precision",
    } <= evaluation.json().keys()
    assert client.get("/api/accounts/ACC--01/links").status_code == 200
    assert client.get("/docs").status_code == 200
    invalid = client.get("/api/transactions", params={"limit": 0})
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "validation_error"
    first_batch = client.post("/api/risk/evaluate", json={"limit": 2})
    assert first_batch.status_code == 200
    assert first_batch.json()["transactions_evaluated"] == 2
    cursor = first_batch.json()["next_cursor"]
    assert cursor is not None
    next_batch = client.post(
        "/api/risk/evaluate",
        json={"limit": 2, **cursor},
    )
    assert next_batch.status_code == 200
    assert next_batch.json()["transactions_evaluated"] == 2
    assert next_batch.json()["next_cursor"]["after_transaction_id"] != cursor["after_transaction_id"]


@pytest.mark.parametrize(
    "params",
    (
        {"start_at": "not-a-timestamp"},
        {"end_at": "not-a-timestamp"},
    ),
)
def test_transaction_list_rejects_malformed_timestamps(backend, params):
    client, _, _, _ = backend

    response = client.get("/api/transactions", params=params)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


@pytest.mark.parametrize(
    "params",
    (
        {"start_at": "2026-01-01T00:00:00"},
        {"end_at": "2026-01-01T00:00:00"},
        {"start_at": "2026-01-01T00:00:00", "end_at": "2026-01-02T00:00:00Z"},
        {"start_at": "2026-01-01T00:00:00Z", "end_at": "2026-01-02T00:00:00"},
    ),
)
def test_transaction_list_rejects_naive_timestamps_before_comparison(backend, params):
    client, _, _, _ = backend

    response = client.get("/api/transactions", params=params)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "http_error"
    assert response.json()["error"]["message"] == "timestamps must include a timezone"


def test_transaction_list_rejects_reversed_aware_range_and_accepts_equal_boundaries(backend):
    client, _, _, _ = backend

    reversed_range = client.get(
        "/api/transactions",
        params={
            "start_at": "2026-10-22T00:00:00Z",
            "end_at": "2026-01-01T00:00:00Z",
        },
    )
    assert reversed_range.status_code == 422
    assert reversed_range.json()["error"]["code"] == "http_error"
    assert reversed_range.json()["error"]["message"] == "end_at must not precede start_at"

    sample = client.get("/api/transactions", params={"limit": 1}).json()["items"][0]
    boundary = sample["transaction_at"]
    equal_range = client.get(
        "/api/transactions",
        params={"start_at": boundary, "end_at": boundary},
    )
    assert equal_range.status_code == 200
    assert equal_range.json()["total"] == 1
    assert equal_range.json()["items"][0]["transaction_id"] == sample["transaction_id"]


@pytest.mark.parametrize(
    ("path", "params"),
    (
        ("/api/transactions", {"transaction_type": "not-a-type"}),
        ("/api/transactions", {"status": "not-a-status"}),
        ("/api/alerts", {"priority": "P0"}),
        ("/api/alerts", {"status": "not-a-status"}),
        ("/api/cases", {"priority": "P0"}),
        ("/api/cases", {"status": "not-a-status"}),
        ("/api/transactions", {"sort_by": "not-a-column"}),
        ("/api/transactions", {"order": "sideways"}),
    ),
)
def test_list_endpoints_reject_invalid_enum_filters_and_sorting(backend, path, params):
    client, _, _, _ = backend

    response = client.get(path, params=params)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


@pytest.mark.parametrize(
    "path",
    (
        "/api/transactions",
        "/api/accounts/ACC--01/transactions",
        "/api/alerts",
        "/api/cases",
    ),
)
@pytest.mark.parametrize("limit", (0, -1, 501))
def test_list_endpoints_enforce_limit_boundaries(backend, path, limit):
    client, _, _, _ = backend

    response = client.get(path, params={"limit": limit})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


@pytest.mark.parametrize(
    "path",
    (
        "/api/transactions",
        "/api/accounts/ACC--01/transactions",
        "/api/alerts",
        "/api/cases",
    ),
)
def test_list_endpoints_accept_maximum_limit_and_return_empty_beyond_records(backend, path):
    client, _, _, _ = backend

    maximum_page = client.get(path, params={"limit": 500})
    assert maximum_page.status_code == 200
    assert maximum_page.json()["limit"] == 500
    assert len(maximum_page.json()["items"]) == maximum_page.json()["total"]

    beyond_records = client.get(path, params={"limit": 1, "offset": 10_000})
    assert beyond_records.status_code == 200
    assert beyond_records.json()["items"] == []
    assert beyond_records.json()["total"] == maximum_page.json()["total"]
    assert beyond_records.json()["offset"] == 10_000


@pytest.mark.parametrize("offset", (-1, -100))
def test_list_endpoints_reject_negative_offsets(backend, offset):
    client, _, _, _ = backend

    for path in (
        "/api/transactions",
        "/api/accounts/ACC--01/transactions",
        "/api/alerts",
        "/api/cases",
    ):
        response = client.get(path, params={"offset": offset})
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"


@pytest.mark.parametrize("limit", (0, -1, 10_001))
def test_risk_evaluation_rejects_out_of_range_limits(backend, limit):
    client, _, _, _ = backend

    response = client.post("/api/risk/evaluate", json={"limit": limit})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_risk_evaluation_accepts_minimum_and_maximum_limits(backend):
    client, _, _, _ = backend

    minimum = client.post("/api/risk/evaluate", json={"limit": 1})
    assert minimum.status_code == 200
    assert minimum.json()["transactions_evaluated"] == 1

    maximum = client.post("/api/risk/evaluate", json={"limit": 10_000})
    assert maximum.status_code == 200
    assert maximum.json()["transactions_evaluated"] == 100
    assert maximum.json()["next_cursor"] is None


def test_transaction_sort_fields_orders_ties_and_pagination_are_deterministic(backend):
    client, _, factory, _ = backend
    sort_fields = (
        "transaction_at",
        "transaction_id",
        "debit_minor",
        "credit_minor",
        "transaction_type",
        "status",
    )
    with factory() as session:
        transactions = session.scalars(
            select(Transaction).order_by(Transaction.transaction_id)
        ).all()

    for sort_by in sort_fields:
        for order in ("asc", "desc"):
            expected = sorted(transactions, key=lambda row: row.transaction_id)
            expected.sort(
                key=lambda row: getattr(row, sort_by),
                reverse=order == "desc",
            )
            response = client.get(
                "/api/transactions",
                params={"sort_by": sort_by, "order": order, "limit": 500},
            )
            assert response.status_code == 200
            transaction_ids = [
                row["transaction_id"] for row in response.json()["items"]
            ]
            assert transaction_ids == [row.transaction_id for row in expected]

            repeated = client.get(
                "/api/transactions",
                params={"sort_by": sort_by, "order": order, "limit": 500},
            )
            assert [
                row["transaction_id"] for row in repeated.json()["items"]
            ] == transaction_ids

    for order in ("asc", "desc"):
        page_ids = []
        for offset in range(0, len(transactions), 9):
            page = client.get(
                "/api/transactions",
                params={
                    "sort_by": "status",
                    "order": order,
                    "limit": 9,
                    "offset": offset,
                },
            )
            assert page.status_code == 200
            page_ids.extend(row["transaction_id"] for row in page.json()["items"])
        expected = sorted(transactions, key=lambda row: row.transaction_id)
        expected.sort(key=lambda row: row.status, reverse=order == "desc")
        assert page_ids == [row.transaction_id for row in expected]
        assert len(page_ids) == len(set(page_ids))


def test_alert_and_case_timestamp_ties_have_stable_paginated_order(backend):
    client, _, factory, _ = backend
    tied_at = datetime(2026, 10, 1, tzinfo=UTC)
    with factory() as session:
        alerts = session.scalars(select(Alert)).all()
        for alert in alerts:
            alert.detected_at = tied_at

        for case in session.scalars(select(Case)).all():
            case.updated_at = tied_at

        cases = [
            Case(
                case_id=f"CASE-STEP73B-{index:02d}",
                title=f"Pagination tie case {index}",
                status="open",
                priority="P4",
                created_at=tied_at,
                updated_at=tied_at,
                created_by_actor_id="system-risktrace",
            )
            for index in range(1, 4)
        ]
        session.add_all(cases)
        session.commit()
        expected_alert_ids = sorted(alert.alert_id for alert in alerts)

    alert_ids = []
    for offset in range(0, len(expected_alert_ids), 3):
        page = client.get(
            "/api/alerts",
            params={"limit": 3, "offset": offset},
        )
        assert page.status_code == 200
        alert_ids.extend(row["alert_id"] for row in page.json()["items"])
    assert alert_ids == expected_alert_ids
    assert len(alert_ids) == len(set(alert_ids))

    case_ids = []
    for offset in range(0, len(cases) + 1, 2):
        page = client.get("/api/cases", params={"limit": 2, "offset": offset})
        assert page.status_code == 200
        case_ids.extend(row["case_id"] for row in page.json()["items"])
    assert case_ids == sorted(
        [f"CASE-STEP73B-{index:02d}" for index in range(1, 4)]
        + ["CASE-2026-000001"]
    )
    assert len(case_ids) == len(set(case_ids))


def test_missing_api_references_return_standard_http_error_envelope(backend):
    client, _, _, _ = backend
    missing_requests = (
        ("GET", "/api/transactions/TXN-MISSING", None, "Transaction not found."),
        (
            "GET",
            "/api/accounts/ACC-MISSING/transactions",
            None,
            "Account not found.",
        ),
        (
            "GET",
            "/api/accounts/ACC-MISSING/links",
            None,
            "Account ACC-MISSING was not found.",
        ),
        ("GET", "/api/alerts/ALT-MISSING", None, "Alert not found."),
        ("GET", "/api/cases/CASE-MISSING", None, "Case not found."),
        (
            "POST",
            "/api/risk/evaluate",
            {"transaction_id": "TXN-MISSING"},
            "Transaction not found.",
        ),
        (
            "POST",
            "/api/cases/CASE-MISSING/actions",
            {"action_type": "note_added"},
            "Case CASE-MISSING was not found.",
        ),
    )
    for method, path, payload, message in missing_requests:
        response = (
            client.get(path)
            if method == "GET"
            else client.post(path, json=payload)
        )
        assert response.status_code == 404
        assert response.json() == {
            "error": {"code": "http_error", "message": message}
        }


def test_risk_evaluation_rejects_non_posted_transaction_with_standard_error(backend):
    client, _, factory, _ = backend
    with factory() as session:
        alerted_transaction_ids = select(Alert.triggering_transaction_id)
        transaction = session.scalar(
            select(Transaction)
            .where(Transaction.transaction_id.not_in(alerted_transaction_ids))
            .order_by(Transaction.transaction_id)
            .limit(1)
        )
        assert transaction is not None
        transaction.status = "declined"
        transaction.posted_at = None
        transaction.opening_balance_minor = None
        transaction.closing_balance_minor = None
        transaction.account_status_at_posting = None
        transaction_id = transaction.transaction_id
        session.commit()

    response = client.post(
        "/api/risk/evaluate",
        json={"transaction_id": transaction_id},
    )
    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "http_error",
            "message": "Only posted transactions can be evaluated.",
        }
    }


def test_unknown_list_filter_ids_return_empty_pages_not_not_found(backend):
    client, _, _, _ = backend
    requests = (
        ("/api/transactions", {"account_id": "ACC-MISSING"}),
        ("/api/alerts", {"rule_id": "RUL-MISSING"}),
        ("/api/alerts", {"transaction_id": "TXN-MISSING"}),
    )
    for path, params in requests:
        response = client.get(path, params=params)
        assert response.status_code == 200
        assert response.json()["items"] == []
        assert response.json()["total"] == 0


def test_link_analysis_requires_evidence_and_reports_shared_customer_device_transfer(backend):
    _, _, factory, _ = backend
    at = datetime(2026, 10, 1, tzinfo=UTC)
    with factory() as session:
        customer_result = analyze_account_links(session, "ACC--01", as_of=at)
        assert any(
            row["account_id"] == "ACC--11"
            and any(reason["type"] == "shared_customer" for reason in row["reasons"])
            for row in customer_result["linked_accounts"]
        )

        owners = {
            account_id: session.scalar(
                select(CustomerAccount.customer_id).where(CustomerAccount.account_id == account_id)
            )
            for account_id in ("ACC--01", "ACC--02")
        }
        device = Device(
            device_id="DEV-SHARED-TEST",
            device_type="web",
            status="active",
            first_seen_at=datetime(2026, 1, 1, tzinfo=UTC),
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        session.add(device)
        for index, owner_id in enumerate(owners.values(), start=1):
            session.add(
                CustomerDevice(
                    customer_device_id=f"CDV-SHARED-{index}",
                    customer_id=owner_id,
                    device_id=device.device_id,
                    status="active",
                    first_seen_at=datetime(2026, 1, 1, tzinfo=UTC),
                    last_seen_at=datetime(2026, 12, 1, tzinfo=UTC),
                    created_at=datetime(2026, 1, 1, tzinfo=UTC),
                )
            )
        session.commit()
        device_result = analyze_account_links(session, "ACC--01", as_of=at)
        shared_device = next(row for row in device_result["linked_accounts"] if row["account_id"] == "ACC--02")
        assert any(reason["type"] == "shared_device" for reason in shared_device["reasons"])

        transfer = session.scalar(select(TransferLink).limit(1))
        transfer_result = analyze_account_links(
            session,
            transfer.source_account_id,
            as_of=transfer.initiated_at,
            lookback_days=365,
        )
        destination = next(
            row for row in transfer_result["linked_accounts"]
            if row["account_id"] == transfer.destination_account_id
        )
        assert any(reason["type"] == "transfer" for reason in destination["reasons"])

        isolated = Account(
            account_id="ACC-ISOLATED-TEST",
            currency="USD",
            opening_balance_minor=1000,
            overdraft_eligible=False,
            overdraft_limit_minor=0,
            status="open",
            opened_at=datetime(2026, 1, 1, tzinfo=UTC),
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        session.add(isolated)
        session.commit()
        assert analyze_account_links(session, isolated.account_id, as_of=at)["linked_accounts"] == []


def _create_groupable_alerts(session):
    account = session.scalar(select(Account).where(Account.status == "open").order_by(Account.account_id))
    already_alerted = select(Alert.triggering_transaction_id)
    transactions = session.scalars(
        select(Transaction)
        .where(
            Transaction.account_id == account.account_id,
            Transaction.status == "posted",
            Transaction.transaction_id.not_in(already_alerted),
        )
        .order_by(Transaction.transaction_at)
        .limit(2)
    ).all()
    rules = session.scalars(select(RiskRule).where(RiskRule.status == "active").order_by(RiskRule.rule_key).limit(2)).all()
    detected_at = datetime.now(UTC) - timedelta(minutes=5)
    for transaction, rule in zip(transactions, rules):
        session.add(
            Alert(
                alert_id=f"ALT-TEST-{transaction.transaction_id[-8:]}",
                rule_id=rule.rule_id,
                triggering_transaction_id=transaction.transaction_id,
                status="new",
                priority="P2",
                score_contribution_bps=rule.default_score_contribution_bps,
                evidence_json={
                    "schema_version": 1,
                    "source": "risk_engine",
                    "explanation": "Test correlation finding.",
                    "evidence": {"test": True},
                    "evaluated_at": detected_at.isoformat(),
                },
                detected_at=detected_at,
                created_at=detected_at,
            )
        )
    session.commit()
    return [transaction.transaction_id for transaction in transactions]


def _insert_grouping_alert(
    session,
    transaction: Transaction,
    *,
    alert_id: str,
    rule_key: str,
    priority: str = "P2",
    detected_at: datetime = NOW,
) -> Alert:
    rule = session.scalar(
        select(RiskRule).where(
            RiskRule.rule_key == rule_key,
            RiskRule.status == "active",
        )
    )
    assert rule is not None
    alert = Alert(
        alert_id=alert_id,
        rule_id=rule.rule_id,
        triggering_transaction_id=transaction.transaction_id,
        status="new",
        priority=priority,
        score_contribution_bps=rule.default_score_contribution_bps,
        evidence_json={
            "schema_version": 1,
            "source": "risk_engine",
            "explanation": "Test case grouping alert.",
            "evidence": {"test": True},
            "evaluated_at": detected_at.isoformat(),
        },
        detected_at=detected_at,
        created_at=detected_at,
    )
    session.add(alert)
    session.flush()
    return alert


def _active_case_member(session):
    row = session.execute(
        select(Case, Alert, Transaction)
        .join(CaseAlert, CaseAlert.case_id == Case.case_id)
        .join(Alert, Alert.alert_id == CaseAlert.alert_id)
        .join(Transaction, Transaction.transaction_id == Alert.triggering_transaction_id)
        .where(Case.status.in_(("open", "in_review", "escalated")), CaseAlert.status == "linked")
        .order_by(Case.created_at, Case.case_id, Alert.alert_id)
        .limit(1)
    ).one()
    return row


def test_single_related_alert_attaches_to_active_case_and_recalculates_priority(backend):
    _, _, factory, _ = backend
    with factory() as session:
        case, _, transaction = _active_case_member(session)
        linked_count_before = session.scalar(
            select(func.count(CaseAlert.case_alert_id)).where(
                CaseAlert.case_id == case.case_id,
                CaseAlert.status == "linked",
            )
        )
        alert = _insert_grouping_alert(
            session,
            transaction,
            alert_id="ALT-ATTACH-SAME-ACCOUNT",
            rule_key="new_device",
            priority="P1",
        )
        session.commit()
        original_updated_at = case.updated_at

        result = group_related_alerts(session, limit=1000)
        assert result == {
            "cases_created": 0,
            "case_ids": [],
            "attached_case_ids": [case.case_id],
            "alert_count": 1,
        }
        links = session.scalars(
            select(CaseAlert).where(
                CaseAlert.case_id == case.case_id,
                CaseAlert.alert_id == alert.alert_id,
                CaseAlert.status == "linked",
            )
        ).all()
        assert len(links) == 1
        assert links[0].link_reason == "rule_correlation"
        linked_count_after = session.scalar(
            select(func.count(CaseAlert.case_alert_id)).where(
                CaseAlert.case_id == case.case_id,
                CaseAlert.status == "linked",
            )
        )
        assert linked_count_after == linked_count_before + 1
        session.refresh(case)
        assert case.priority == "P1"
        assert case.updated_at >= original_updated_at
        audit_count = session.scalar(
            select(func.count(AuditEvent.audit_event_id)).where(
                AuditEvent.event_type == "case.alert_attached",
                AuditEvent.entity_id == case.case_id,
            )
        )
        assert audit_count == 1
        audit = session.scalar(
            select(AuditEvent).where(
                AuditEvent.event_type == "case.alert_attached",
                AuditEvent.entity_id == case.case_id,
            )
        )
        assert audit is not None
        assert audit.payload_json["case_id"] == case.case_id
        assert audit.payload_json["alert_id"] == alert.alert_id
        assert audit.payload_json["relationship_reason"] == "same_account"

        repeated = group_related_alerts(session, limit=1000)
        assert repeated == {
            "cases_created": 0,
            "case_ids": [],
            "attached_case_ids": [],
            "alert_count": 0,
        }
        assert session.scalar(
            select(func.count(CaseAlert.case_alert_id)).where(
                CaseAlert.case_id == case.case_id,
                CaseAlert.alert_id == alert.alert_id,
            )
        ) == 1
        assert session.scalar(
            select(func.count(AuditEvent.audit_event_id)).where(
                AuditEvent.event_type == "case.alert_attached",
                AuditEvent.entity_id == case.case_id,
            )
        ) == audit_count


def test_single_alert_with_shared_customer_attaches_to_related_active_case(backend):
    _, _, factory, _ = backend
    with factory() as session:
        case, _, linked_transaction = _active_case_member(session)
        linked_owner = session.scalar(
            select(CustomerAccount).where(
                CustomerAccount.account_id == linked_transaction.account_id,
                CustomerAccount.status == "active",
            )
        )
        assert linked_owner is not None
        linked_account_ids = select(Transaction.account_id).join(
            Alert, Alert.triggering_transaction_id == Transaction.transaction_id
        ).join(CaseAlert, CaseAlert.alert_id == Alert.alert_id).where(
            CaseAlert.status == "linked"
        )
        transaction = session.scalar(
            select(Transaction)
            .where(
                Transaction.status == "posted",
                Transaction.account_id != linked_transaction.account_id,
                Transaction.account_id.not_in(linked_account_ids),
            )
            .order_by(Transaction.transaction_id)
            .limit(1)
        )
        assert transaction is not None
        owner_exists = session.scalar(
            select(CustomerAccount.customer_account_id).where(
                CustomerAccount.customer_id == linked_owner.customer_id,
                CustomerAccount.account_id == transaction.account_id,
            )
        )
        if owner_exists is None:
            session.add(
                CustomerAccount(
                    customer_account_id="OWN-SHARED-TEST",
                    customer_id=linked_owner.customer_id,
                    account_id=transaction.account_id,
                    relationship_type="joint_owner",
                    status="active",
                    valid_from=datetime(2026, 1, 1, tzinfo=UTC),
                    created_at=datetime(2026, 1, 1, tzinfo=UTC),
                )
            )
        alert = _insert_grouping_alert(
            session,
            transaction,
            alert_id="ALT-ATTACH-SHARED-CUSTOMER",
            rule_key="new_device",
        )
        session.commit()

        result = group_related_alerts(session, at=NOW)

        assert result["cases_created"] == 0
        assert result["case_ids"] == []
        assert result["attached_case_ids"] == [case.case_id]
        audit = session.scalar(
            select(AuditEvent).where(
                AuditEvent.event_type == "case.alert_attached",
                AuditEvent.entity_id == case.case_id,
            )
        )
        assert audit is not None
        assert audit.payload_json["alert_id"] == alert.alert_id
        assert audit.payload_json["relationship_reason"] == "shared_customer"


def test_unrelated_singleton_alert_does_not_create_or_attach_case(backend):
    _, _, factory, _ = backend
    with factory() as session:
        account = Account(
            account_id="ACC-CASE-UNRELATED",
            currency="USD",
            opening_balance_minor=100_000,
            overdraft_eligible=False,
            overdraft_limit_minor=0,
            status="open",
            opened_at=NOW - timedelta(days=1),
            created_at=NOW - timedelta(days=1),
        )
        transaction = Transaction(
            transaction_id="TXN-2026-99000001",
            account=account,
            transaction_type="purchase",
            status="posted",
            transaction_at=NOW,
            posted_at=NOW,
            currency="USD",
            debit_minor=1_000,
            credit_minor=0,
            opening_balance_minor=100_000,
            closing_balance_minor=99_000,
            account_status_at_posting="open",
            created_at=NOW,
        )
        session.add(transaction)
        session.flush()
        _insert_grouping_alert(
            session,
            transaction,
            alert_id="ALT-ATTACH-UNRELATED",
            rule_key="new_device",
        )
        session.commit()

        result = group_related_alerts(session, at=NOW)

        assert result == {
            "cases_created": 0,
            "case_ids": [],
            "attached_case_ids": [],
            "alert_count": 1,
        }
        assert session.scalar(
            select(func.count(CaseAlert.case_alert_id)).where(
                CaseAlert.alert_id == "ALT-ATTACH-UNRELATED"
            )
        ) == 0


def test_singleton_matching_multiple_cases_chooses_oldest_then_case_id(backend):
    _, _, factory, _ = backend
    with factory() as session:
        _, _, transaction = _active_case_member(session)
        tied_created_at = datetime(2025, 12, 1, tzinfo=UTC)
        cases = [
            Case(
                case_id=case_id,
                title="Tie-break test",
                status="open",
                priority="P3",
                created_at=tied_created_at,
                updated_at=tied_created_at,
            )
            for case_id in ("CASE-2026-900002", "CASE-2026-900001")
        ]
        session.add_all(cases)
        for case, rule_key, alert_id in zip(
            cases,
            ("high_value", "dormant_reactivation"),
            ("ALT-ATTACH-TIE-B", "ALT-ATTACH-TIE-A"),
        ):
            member_alert = _insert_grouping_alert(
                session,
                transaction,
                alert_id=alert_id,
                rule_key=rule_key,
            )
            session.add(
                CaseAlert(
                    case_alert_id=f"CAL-{alert_id}",
                    case_id=case.case_id,
                    alert_id=member_alert.alert_id,
                    linked_at=tied_created_at,
                    linked_by_actor_id="system-risktrace",
                    link_reason="rule_correlation",
                    status="linked",
                )
            )
        candidate = _insert_grouping_alert(
            session,
            transaction,
            alert_id="ALT-ATTACH-TIE-CANDIDATE",
            rule_key="new_device",
        )
        session.commit()

        result = group_related_alerts(session, at=NOW)

        assert result["attached_case_ids"] == ["CASE-2026-900001"]
        assert result["cases_created"] == 0
        assert session.scalar(
            select(func.count(CaseAlert.case_alert_id)).where(
                CaseAlert.alert_id == candidate.alert_id,
                CaseAlert.status == "linked",
            )
        ) == 1


def test_case_grouping_and_append_only_analyst_disposition(backend):
    client, _, factory, _ = backend
    with factory() as session:
        transaction_ids = _create_groupable_alerts(session)
        grouped = group_related_alerts(session)
        assert grouped["cases_created"] >= 1
        assert grouped["attached_case_ids"] == []
        assert grouped["alert_count"] == 2
        matching_case = None
        links = []
        for case_id in grouped["case_ids"]:
            case_links = session.scalars(
                select(CaseAlert).where(CaseAlert.case_id == case_id, CaseAlert.status == "linked")
            ).all()
            if {link.alert.triggering_transaction_id for link in case_links} == set(transaction_ids):
                matching_case = session.get(Case, case_id)
                links = case_links
                break
        assert matching_case is not None
        case = matching_case
        assert group_related_alerts(session)["cases_created"] == 0

        action_response = client.post(
            f"/api/cases/{case.case_id}/actions",
            json={
                "action_type": "review_started",
                "alert_id": links[0].alert_id,
                "note": "Beginning review.",
            },
        )
        assert action_response.status_code == 201
        assert action_response.json()["actor_id"] == "analyst-demo-001"
        session.refresh(case)
        assert session.get(Case, case.case_id).status == "in_review"
        disposition_response = client.post(
            f"/api/cases/{case.case_id}/actions",
            json={
                "action_type": "disposition_recorded",
                "alert_id": links[0].alert_id,
                "disposition": "LEGITIMATE",
                "note": "Reviewed supporting evidence.",
            },
        )
        assert disposition_response.status_code == 201
        assert disposition_response.json()["disposition"] == "false_positive"
        session.refresh(case)
        assert session.get(Case, case.case_id).status == "resolved"
        assert session.scalar(
            select(func.count(AnalystAction.action_id)).where(AnalystAction.case_id == case.case_id)
        ) == 2
        disposition = session.get(AnalystAction, disposition_response.json()["action_id"])
        disposition.note = "overwrite attempt"
        with pytest.raises(ValueError, match="append-only"):
            session.commit()


def test_invalid_case_disposition_and_future_alert_chronology_are_rejected(backend):
    _, _, factory, _ = backend
    with factory() as session:
        _create_groupable_alerts(session)
        group = group_related_alerts(session)
        case_id = group["case_ids"][0]
        with pytest.raises(ValueError, match="must be in_review"):
            record_analyst_action(
                session,
                case_id,
                {"action_type": "disposition_recorded", "disposition": "suspicious"},
            )
        assert session.scalar(
            select(func.count(AuditEvent.audit_event_id)).where(
                AuditEvent.event_type == "analyst.action_rejected"
            )
        ) == 1
        link = session.scalar(select(CaseAlert).where(CaseAlert.case_id == case_id))
        alert = session.get(Alert, link.alert_id)
        alert.detected_at = datetime.now(UTC) + timedelta(days=1)
        session.commit()
        with pytest.raises(ValueError, match="cannot precede"):
            record_analyst_action(
                session,
                case_id,
                {"action_type": "note_added", "alert_id": alert.alert_id, "note": "too early"},
            )


def test_ground_truth_is_evaluated_separately_and_not_used_by_risk_detection(backend):
    _, _, factory, truth_path = backend
    with factory() as session:
        metrics = evaluate_ground_truth(session, truth_path)
        assert metrics["labeled_transactions"] + metrics["excluded_ambiguous"] == 100
        assert set(metrics) >= {"precision", "recall", "f1_score", "false_positive_rate"}
        transaction = _add_high_value_transaction(session)
        result = evaluate_transactions(session, transaction_id=transaction.transaction_id)
        assert result["transactions_evaluated"] == 1
        assert session.scalar(
            select(func.count(Alert.alert_id)).where(
                Alert.triggering_transaction_id == transaction.transaction_id
            )
        ) >= 1


def test_evaluator_metrics_exclude_seed_alerts_and_ambiguous_labels(backend, tmp_path):
    _, _, factory, _ = backend
    truth_path = tmp_path / "metric-truth.jsonl"
    with factory() as session:
        seed_alerted = select(Alert.triggering_transaction_id)
        transactions = session.scalars(
            select(Transaction)
            .where(Transaction.transaction_id.not_in(seed_alerted))
            .order_by(Transaction.transaction_id)
            .limit(3)
        ).all()
        rules = session.scalars(
            select(RiskRule).where(RiskRule.status == "active").order_by(RiskRule.rule_key).limit(3)
        ).all()
        labels = ("suspicious", "legitimate", "ambiguous")
        for index, (transaction, rule, label) in enumerate(zip(transactions, rules, labels)):
            if label == "ambiguous":
                contribution = 7500
            else:
                contribution = 5000 if label == "suspicious" else 2500
            session.add(
                Alert(
                    alert_id=f"ALT-METRIC-{index}",
                    rule_id=rule.rule_id,
                    triggering_transaction_id=transaction.transaction_id,
                    status="new",
                    priority="P2",
                    score_contribution_bps=contribution,
                    evidence_json={"source": "risk_engine", "evidence": {}},
                    detected_at=transaction.transaction_at,
                    created_at=transaction.transaction_at,
                )
            )
        session.commit()
        truth_path.write_text(
            "\n".join(
                (
                    '{"entity_type":"transaction","entity_id":"%s","label":"%s"}'
                    % (transaction.transaction_id, label)
                )
                for transaction, label in zip(transactions, labels)
            ),
            encoding="utf-8",
        )
        metrics = evaluate_ground_truth(session, truth_path)
        assert metrics["true_positive"] == 1
        assert metrics["false_positive"] == 1
        assert metrics["true_negative"] == 0
        assert metrics["false_negative"] == 0
        assert metrics["precision"] == 0.5
        assert metrics["recall"] == 1.0
        assert metrics["false_positive_rate"] == 1.0
        assert metrics["excluded_ambiguous"] == 1
        assert metrics["top_100_prediction_count"] == 3
        assert metrics["top_100_labeled_transactions"] == 2
        assert metrics["top_100_precision"] == 0.5


def test_schema_upgrade_preserves_phase5_seed_records(tmp_path):
    backend_dir = PROJECT_ROOT / "backend"
    database_path = tmp_path / "upgrade-preserves-data.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    config = Config(str(backend_dir / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "0055723a91d0")
    engine = make_engine(database_url)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    truth_path = tmp_path / "upgrade-truth.jsonl"
    with factory() as session:
        generate_dataset(session, SEED_CONFIG, truth_path)
        old_count = session.scalar(select(func.count(Transaction.transaction_id)))
    upgrade_database(engine)
    with factory() as session:
        assert session.scalar(select(func.count(Transaction.transaction_id))) == old_count
        assert session.scalar(
            select(func.count(RiskRule.rule_id)).where(RiskRule.rule_key == "linked_suspicious")
        ) == 1
    engine.dispose()
