import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import sessionmaker

from app.database.init_db import upgrade_database
from app.database.session import make_engine
from app.models import (
    Account,
    Alert,
    AnalystAction,
    AuditEvent,
    Case,
    CaseAlert,
    Customer,
    CustomerAccount,
    ExceptionRecord,
    RiskRule,
    Transaction,
    TransferLink,
)
from app.services.data_quality import validate_dataset
from app.services.seed_data import SeedConfig, generate_dataset

UTC_NOW = datetime(2026, 5, 1, tzinfo=timezone.utc)


@pytest.fixture
def db(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    upgrade_database(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    try:
        yield engine, factory
    finally:
        engine.dispose()


def test_initial_migration_creates_all_entities_and_enforces_sqlite_fks(db):
    engine, factory = db
    expected_tables = {
        "customer", "account", "merchant", "device", "transaction_record",
        "transfer_link", "risk_rule", "alert", "case_record", "analyst_action",
        "kyc_profile", "customer_account", "customer_device", "case_alert",
        "exception_record", "audit_event",
    }
    assert expected_tables <= set(inspect(engine).get_table_names())
    transaction_indexes = {index["name"] for index in inspect(engine).get_indexes("transaction_record")}
    assert "ix_transaction_account_time_id" in transaction_indexes
    with engine.connect() as connection:
        assert connection.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
        assert connection.execute(text("PRAGMA integrity_check")).scalar_one() == "ok"
    upgrade_database(engine)
    with factory() as session:
        assert len(validate_dataset(session)) == 16


def test_orm_relationships_and_effective_dated_ownership(db):
    _, factory = db
    with factory() as session:
        customer = Customer(customer_id="CUS-000001", status="active", created_at=UTC_NOW, updated_at=UTC_NOW)
        account = Account(
            account_id="ACC--01",
            currency="USD",
            opening_balance_minor=5000,
            overdraft_eligible=False,
            overdraft_limit_minor=0,
            status="open",
            opened_at=UTC_NOW,
            created_at=UTC_NOW,
        )
        link = CustomerAccount(
            customer_account_id="OWN-000001",
            customer=customer,
            account=account,
            relationship_type="primary_owner",
            status="active",
            valid_from=UTC_NOW,
            created_at=UTC_NOW,
        )
        session.add(link)
        session.commit()
        assert link in customer.account_links
        assert link in account.ownership_links


def test_utc_datetime_round_trip_and_naive_input_rejection(db):
    _, factory = db
    with factory() as session:
        account = Account(
            account_id="ACC--01",
            currency="USD",
            opening_balance_minor=5000,
            overdraft_eligible=False,
            overdraft_limit_minor=0,
            status="open",
            opened_at=UTC_NOW,
            created_at=UTC_NOW,
        )
        session.add(account)
        session.commit()
        session.expire(account, ["opened_at"])
        assert account.opened_at == UTC_NOW
        assert account.opened_at.tzinfo == timezone.utc

        session.add(
            Account(
                account_id="ACC--02",
                currency="USD",
                opening_balance_minor=5000,
                overdraft_eligible=False,
                overdraft_limit_minor=0,
                status="open",
                opened_at=datetime(2026, 5, 1),
                created_at=UTC_NOW,
            )
        )
        with pytest.raises(StatementError, match="timezone-aware"):
            session.commit()


def test_check_constraints_reject_invalid_money_and_transfer(db):
    _, factory = db
    with factory() as session:
        session.add(
            Account(
                account_id="ACC--01",
                currency="USD",
                opening_balance_minor=5000,
                overdraft_eligible=False,
                overdraft_limit_minor=0,
                status="open",
                opened_at=UTC_NOW,
                created_at=UTC_NOW,
            )
        )
        session.commit()
        session.add(
            Transaction(
                transaction_id="TXN-2026-00000001",
                account_id="ACC--01",
                transaction_type="purchase",
                status="posted",
                transaction_at=UTC_NOW,
                posted_at=UTC_NOW,
                currency="USD",
                debit_minor=-1,
                credit_minor=0,
                opening_balance_minor=5000,
                closing_balance_minor=5001,
                account_status_at_posting="open",
                created_at=UTC_NOW,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


def test_transfer_mismatch_and_orphan_alert_are_rejected(db):
    engine, factory = db
    with factory() as session:
        accounts = [
            Account(
                account_id=f"ACC--{index:02d}",
                currency="USD",
                opening_balance_minor=5000,
                overdraft_eligible=False,
                overdraft_limit_minor=0,
                status="open",
                opened_at=UTC_NOW,
                created_at=UTC_NOW,
            )
            for index in (1, 2)
        ]
        rule = RiskRule(
            rule_id="RUL-high_value-V01",
            rule_key="high_value",
            version=1,
            name="High value",
            description="Test rule",
            status="active",
            parameters_json={},
            default_score_contribution_bps=3000,
            effective_at=UTC_NOW,
            created_at=UTC_NOW,
        )
        session.add_all(accounts + [rule])
        session.flush()
        source = Transaction(
            transaction_id="TXN-2026-00000001",
            account_id="ACC--01",
            transaction_type="transfer",
            status="posted",
            transaction_at=UTC_NOW,
            posted_at=UTC_NOW,
            currency="USD",
            debit_minor=1000,
            credit_minor=0,
            opening_balance_minor=5000,
            closing_balance_minor=4000,
            account_status_at_posting="open",
            created_at=UTC_NOW,
        )
        destination = Transaction(
            transaction_id="TXN-2026-00000002",
            account_id="ACC--02",
            transaction_type="transfer",
            status="posted",
            transaction_at=UTC_NOW,
            posted_at=UTC_NOW,
            currency="USD",
            debit_minor=0,
            credit_minor=1000,
            opening_balance_minor=5000,
            closing_balance_minor=6000,
            account_status_at_posting="open",
            created_at=UTC_NOW,
        )
        session.add_all([source, destination])
        session.commit()

        session.add(
            TransferLink(
                transfer_id="TRF-2026-000001",
                source_account_id="ACC--01",
                destination_account_id="ACC--02",
                source_transaction_id=source.transaction_id,
                destination_transaction_id=destination.transaction_id,
                currency="USD",
                source_amount_minor=1000,
                destination_amount_minor=999,
                status="reconciled",
                initiated_at=UTC_NOW,
                reconciled_at=UTC_NOW,
                created_at=UTC_NOW,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        session.add(
            Alert(
                alert_id="ALT-2026-000001",
                rule_id=rule.rule_id,
                triggering_transaction_id="TXN-2026-99999999",
                status="new",
                priority="P3",
                score_contribution_bps=3000,
                evidence_json={"schema_version": 1},
                detected_at=UTC_NOW,
                created_at=UTC_NOW,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_seed_data_integrity_transfer_and_exception_isolation(db, tmp_path):
    _, factory = db
    truth_path = tmp_path / "truth.jsonl"
    with factory() as session:
        counts = generate_dataset(
            session,
            SeedConfig(customers=10, accounts=14, merchants=5, devices=6, transactions=100, alerts=10),
            truth_path,
        )
        assert counts["customer"] == 10
        assert counts["account"] == 14
        assert counts["transaction_record"] == 100
        assert counts["transfer_links"] == 5
        assert counts["exception_scenarios"] == 5
        assert counts["ground_truth_records"] == 100
        assert len(session.scalars(select(TransferLink)).all()) == 5
        assert len(session.scalars(select(ExceptionRecord)).all()) == 5
        assert session.scalar(select(Transaction).where(Transaction.transaction_id == "TXN-INVALID-CLOSED")) is None
        assert session.scalar(select(Alert).where(Alert.alert_id == "ALT-INVALID-ORPHAN")) is None
        assert session.scalar(select(TransferLink).where(TransferLink.transfer_id == "TRF-INVALID-MISMATCH")) is None
        assert validate_dataset(session)["transaction_record"] == 100

    truth_rows = [json.loads(line) for line in truth_path.read_text(encoding="utf-8").splitlines()]
    assert len(truth_rows) == 100
    assert {row["entity_type"] for row in truth_rows} == {"transaction"}
    assert all("expected_rule_ids" in row for row in truth_rows)


def test_seed_output_is_reproducible_across_fresh_databases(tmp_path):
    config = SeedConfig(customers=10, accounts=14, merchants=5, devices=6, transactions=100, alerts=10)
    hashes = []
    snapshots = []
    for number in (1, 2):
        engine = make_engine(f"sqlite:///{tmp_path / f'repro{number}.db'}")
        upgrade_database(engine)
        factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
        truth_path = tmp_path / f"truth{number}.jsonl"
        with factory() as session:
            result = generate_dataset(session, config, truth_path)
            rows = session.execute(
                select(Transaction.transaction_id, Transaction.account_id, Transaction.transaction_at,
                       Transaction.debit_minor, Transaction.credit_minor, Transaction.opening_balance_minor,
                       Transaction.closing_balance_minor).order_by(Transaction.transaction_id)
            ).all()
            snapshots.append(rows)
            hashes.append(result["ground_truth_sha256"])
        engine.dispose()
    assert hashes[0] == hashes[1]
    assert snapshots[0] == snapshots[1]


def test_analyst_and_audit_rows_are_append_only(db):
    engine, factory = db
    with factory() as session:
        generate_dataset(
            session,
            SeedConfig(customers=10, accounts=14, merchants=5, devices=6, transactions=100, alerts=10),
        )
        action = session.scalar(select(AnalystAction))
        action.note = "mutated"
        with pytest.raises(ValueError, match="append-only"):
            session.commit()
        session.rollback()
        audit = session.scalar(select(AuditEvent))
        session.delete(audit)
        with pytest.raises(ValueError, match="append-only"):
            session.commit()
        session.rollback()
        customer = session.get(Customer, "CUS-000001")
        customer.customer_id = "CUS-999999"
        with pytest.raises(ValueError, match="identifiers are immutable"):
            session.commit()
        session.rollback()
        rule = session.scalar(select(RiskRule).where(RiskRule.status == "active"))
        rule.name = "Rewritten rule"
        with pytest.raises(ValueError, match="rule versions are immutable"):
            session.commit()
        session.rollback()
    with engine.begin() as connection:
        with pytest.raises(IntegrityError):
            connection.execute(text("UPDATE audit_event SET event_type = 'rewritten'"))
        with pytest.raises(IntegrityError):
            connection.execute(
                text("UPDATE customer SET customer_id = 'CUS-999999' WHERE customer_id = 'CUS-000001'")
            )
        with pytest.raises(IntegrityError):
            connection.execute(
                text("UPDATE risk_rule SET name = 'Rewritten rule' WHERE status = 'active'")
            )
