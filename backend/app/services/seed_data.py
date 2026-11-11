import argparse
import hashlib
import json
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session, sessionmaker

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
    CustomerDevice,
    Device,
    ExceptionRecord,
    KYCProfile,
    Merchant,
    RiskRule,
    Transaction,
    TransferLink,
)
from app.services.data_quality import priority_for_score, validate_dataset

SEED = 20261022
DATASET_VERSION = "2026.1"
START_AT = datetime(2026, 1, 1, tzinfo=timezone.utc)
END_AT = datetime(2026, 10, 22, 23, 59, 59, tzinfo=timezone.utc)
DEFAULT_COUNTS = {
    "customers": 50,
    "accounts": 70,
    "merchants": 20,
    "devices": 30,
    "transactions": 500,
    "alerts": 10,
}
RULE_CONFIG = (
    ("velocity_spike", "Transaction velocity spike", 2500, {"window_minutes": 60, "minimum_count": 5}),
    ("high_value", "High-value transaction", 3000, {"threshold_minor": 250000}),
    ("new_device", "New-device activity", 2500, {"lookback_days": 30}),
    ("dormant_reactivation", "Dormant account reactivation", 3500, {"dormant_days": 90}),
    ("circular_transfer", "Circular transfer pattern", 5000, {"minimum_accounts": 3}),
)
PATTERNS = ("velocity", "high_value", "new_device", "dormant_reactivation", "circular_transfer")


@dataclass(frozen=True)
class SeedConfig:
    customers: int = DEFAULT_COUNTS["customers"]
    accounts: int = DEFAULT_COUNTS["accounts"]
    merchants: int = DEFAULT_COUNTS["merchants"]
    devices: int = DEFAULT_COUNTS["devices"]
    transactions: int = DEFAULT_COUNTS["transactions"]
    alerts: int = DEFAULT_COUNTS["alerts"]
    seed: int = SEED

    def validate(self) -> None:
        if min(self.customers, self.accounts, self.merchants, self.devices, self.transactions, self.alerts) < 1:
            raise ValueError("all entity counts must be positive")
        if self.accounts < self.customers:
            raise ValueError("the baseline requires at least one account per customer")
        if self.accounts < 2:
            raise ValueError("at least two accounts are required for transfers")
        if self.transactions < 2:
            raise ValueError("at least two transactions are required for transfer validation")
        if self.transactions > 99_999_999:
            raise ValueError("transaction count exceeds the fixed eight-digit ID sequence")
        if self.alerts > min(1_000, self.transactions * len(RULE_CONFIG)):
            raise ValueError("alert count exceeds the approved baseline or unique rule/transaction pairs")
        if self.accounts > 99_999_999 or self.customers > 999_999:
            raise ValueError("account/customer count exceeds the configured ID sequence")
        if self.merchants > 999_999 or self.devices > 999_999:
            raise ValueError("merchant/device count exceeds the configured ID sequence")


def _when(index: int, total: int) -> datetime:
    if total <= 1:
        return START_AT
    span = int((END_AT - START_AT).total_seconds())
    return START_AT + timedelta(seconds=span * index // (total - 1))


def _write_truth(path: Path, records: list[dict[str, Any]]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "".join(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n" for record in records)
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8", newline="\n")
    temporary.replace(path)
    return digest


def _insert_in_batches(session: Session, rows: list[Any], batch_size: int = 2_000) -> None:
    for offset in range(0, len(rows), batch_size):
        session.add_all(rows[offset : offset + batch_size])
        session.flush()
        session.expunge_all()


def generate_dataset(
    session: Session,
    config: SeedConfig = SeedConfig(),
    truth_path: Path | None = None,
) -> dict[str, Any]:
    config.validate()
    rng = random.Random(config.seed)
    created = START_AT
    with session.begin():
        if any(session.scalar(select(model).limit(1)) is not None for model in (Customer, Account, Transaction)):
            raise RuntimeError("seed target is not empty; use a new database or an explicit approved reset")

        customers = [
            Customer(
                customer_id=f"CUS-{i:06d}",
                status="active",
                created_at=created,
                updated_at=created,
            )
            for i in range(1, config.customers + 1)
        ]
        accounts = [
            Account(
                account_id=f"ACC--{i:02d}",
                currency="USD",
                opening_balance_minor=5_000_000,
                overdraft_eligible=False,
                overdraft_limit_minor=0,
                status="open",
                opened_at=START_AT,
                created_at=created,
            )
            for i in range(1, config.accounts + 1)
        ]
        merchants = [
            Merchant(
                merchant_id=f"MER-{i:06d}",
                name=f"Demo Merchant {i:04d}",
                category_code=("retail", "grocery", "travel", "digital", "services")[(i - 1) % 5],
                country_code="US",
                status="active",
                created_at=created,
            )
            for i in range(1, config.merchants + 1)
        ]
        devices = [
            Device(
                device_id=f"DEV-{i:06d}",
                device_type=("mobile", "web", "tablet", "other")[(i - 1) % 4],
                fingerprint_hash=hashlib.sha256(f"{config.seed}:device:{i}".encode()).hexdigest(),
                status="active",
                first_seen_at=START_AT,
                created_at=created,
            )
            for i in range(1, config.devices + 1)
        ]
        session.add_all(customers + accounts + merchants + devices)
        session.flush()

        ownerships: list[CustomerAccount] = []
        for i in range(1, config.accounts + 1):
            owner_index = (i - 1) % config.customers
            ownerships.append(
                CustomerAccount(
                    customer_account_id=f"OWN-{i:06d}",
                    customer_id=f"CUS-{owner_index + 1:06d}",
                    account_id=f"ACC--{i:02d}",
                    relationship_type="primary_owner",
                    ownership_share_bps=None,
                    status="active",
                    valid_from=START_AT,
                    created_at=created,
                )
            )
            if config.customers > 1 and rng.random() < 0.1:
                joint_index = (owner_index + rng.randint(1, config.customers - 1)) % config.customers
                ownerships.append(
                    CustomerAccount(
                        customer_account_id=f"OWN-{config.accounts + len(ownerships):06d}",
                        customer_id=f"CUS-{joint_index + 1:06d}",
                        account_id=f"ACC--{i:02d}",
                        relationship_type="joint_owner",
                        ownership_share_bps=None,
                        status="active",
                        valid_from=START_AT,
                        created_at=created,
                    )
                )
        customer_devices: list[CustomerDevice] = []
        for i in range(1, config.devices + 1):
            customer_index = rng.randrange(config.customers)
            customer_devices.append(
                CustomerDevice(
                    customer_device_id=f"CDV-{i:06d}",
                    customer_id=f"CUS-{customer_index + 1:06d}",
                    device_id=f"DEV-{i:06d}",
                    status="active",
                    first_seen_at=START_AT,
                    last_seen_at=END_AT,
                    created_at=created,
                )
            )
        kycs = [
            KYCProfile(
                kyc_profile_id=f"KYC-{i:06d}",
                customer_id=f"CUS-{i:06d}",
                version=1,
                status="verified",
                risk_rating="low" if i % 7 else "medium",
                effective_at=START_AT,
                attributes_json={"synthetic": True},
                created_at=created,
            )
            for i in range(1, config.customers + 1)
        ]
        session.add_all(ownerships + customer_devices + kycs)
        session.flush()

        rule_rows = [
            RiskRule(
                rule_id=f"RUL-{rule_key}-V01",
                rule_key=rule_key,
                version=1,
                name=name,
                description=f"Versioned deterministic demo rule configuration for {name.lower()}.",
                status="active",
                parameters_json=parameters,
                default_score_contribution_bps=score,
                effective_at=START_AT,
                created_at=created,
            )
            for rule_key, name, score, parameters in RULE_CONFIG
        ]
        session.add_all(rule_rows)
        session.flush()

        transfer_pair_count = config.transactions // 20
        events: list[dict[str, Any]] = []
        transfer_specs: list[dict[str, Any]] = []
        for pair in range(transfer_pair_count):
            source_index = rng.randrange(config.accounts)
            destination_index = (source_index + rng.randrange(1, config.accounts)) % config.accounts
            amount = rng.randint(1_000, 50_000)
            transfer_id = f"TRF-2026-{pair + 1:06d}"
            events.append({
                "account_index": source_index,
                "type": "transfer",
                "debit": amount,
                "credit": 0,
                "transfer_id": transfer_id,
                "leg": "source",
            })
            events.append({
                "account_index": destination_index,
                "type": "transfer",
                "debit": 0,
                "credit": amount,
                "transfer_id": transfer_id,
                "leg": "destination",
            })
            transfer_specs.append({
                "transfer_id": transfer_id,
                "source_account_id": f"ACC--{source_index + 1:02d}",
                "destination_account_id": f"ACC--{destination_index + 1:02d}",
                "source_amount_minor": amount,
                "destination_amount_minor": amount,
                "pair": pair,
            })

        remaining = config.transactions - len(events)
        for _ in range(remaining):
            transaction_type = rng.choices(
                ("purchase", "cash_withdrawal", "deposit", "fee", "refund"),
                weights=(68, 10, 12, 4, 6),
                k=1,
            )[0]
            amount = rng.randint(100, 25_000)
            is_credit = transaction_type in ("deposit", "refund")
            events.append({
                "account_index": rng.randrange(config.accounts),
                "type": transaction_type,
                "debit": 0 if is_credit else amount,
                "credit": amount if is_credit else 0,
                "transfer_id": None,
                "leg": None,
            })

        rng.shuffle(events)
        transaction_rows: list[Transaction] = []
        transfer_leg_ids: dict[tuple[str, str], str] = {}
        truth_records: list[dict[str, Any]] = []
        balances = {f"ACC--{i:02d}": account.opening_balance_minor for i, account in enumerate(accounts, 1)}
        for index, event_data in enumerate(events, start=1):
            transaction_id = f"TXN-2026-{index:08d}"
            at = _when(index - 1, len(events))
            account_id = f"ACC--{event_data['account_index'] + 1:02d}"
            opening = balances[account_id]
            closing = opening - event_data["debit"] + event_data["credit"]
            if closing < 0:
                event_data["type"] = "deposit"
                event_data["credit"] = event_data["debit"] + 1_000
                event_data["debit"] = 0
                closing = opening + event_data["credit"]
            balances[account_id] = closing
            merchant_id = (
                f"MER-{rng.randrange(1, config.merchants + 1):06d}"
                if event_data["type"] in ("purchase", "refund")
                else None
            )
            device_id = f"DEV-{rng.randrange(1, config.devices + 1):06d}" if rng.random() < 0.8 else None
            transaction_rows.append(
                Transaction(
                    transaction_id=transaction_id,
                    account_id=account_id,
                    merchant_id=merchant_id,
                    device_id=device_id,
                    transaction_type=event_data["type"],
                    status="posted",
                    transaction_at=at,
                    posted_at=at,
                    currency="USD",
                    debit_minor=event_data["debit"],
                    credit_minor=event_data["credit"],
                    opening_balance_minor=opening,
                    closing_balance_minor=closing,
                    account_status_at_posting="open",
                    created_at=at,
                )
            )
            if event_data["transfer_id"]:
                transfer_leg_ids[(event_data["transfer_id"], event_data["leg"])] = transaction_id

            if index % 101 == 0:
                label, pattern = "ambiguous", "ambiguous_demo"
            elif index % 37 == 0:
                label, pattern = "suspicious", PATTERNS[(index // 37) % len(PATTERNS)]
            else:
                label, pattern = "legitimate", "baseline_synthetic"
            truth_records.append(
                {
                    "truth_record_id": f"GT-2026-{index:06d}",
                    "dataset_version": DATASET_VERSION,
                    "scenario_id": f"SCN-2026-{index:06d}",
                    "entity_type": "transaction",
                    "entity_id": transaction_id,
                    "label": label,
                    "pattern_type": pattern,
                    "expected_rule_ids": [],
                    "rationale": "Synthetic evaluation label; not available to the operational generator consumer.",
                    "split": "evaluation",
                }
            )

        _insert_in_batches(session, transaction_rows)

        transfer_rows = [
            TransferLink(
                transfer_id=spec["transfer_id"],
                source_account_id=spec["source_account_id"],
                destination_account_id=spec["destination_account_id"],
                source_transaction_id=transfer_leg_ids[(spec["transfer_id"], "source")],
                destination_transaction_id=transfer_leg_ids[(spec["transfer_id"], "destination")],
                currency="USD",
                source_amount_minor=spec["source_amount_minor"],
                destination_amount_minor=spec["destination_amount_minor"],
                status="reconciled",
                initiated_at=_when(spec["pair"] * 2, len(events)),
                reconciled_at=_when(spec["pair"] * 2 + 1, len(events)),
                created_at=_when(spec["pair"] * 2, len(events)),
            )
            for spec in transfer_specs
        ]
        session.add_all(transfer_rows)
        session.flush()

        alert_rows: list[Alert] = []
        trigger_alerts: dict[str, list[Alert]] = {}
        for alert_number in range(config.alerts):
            transaction_index = alert_number % len(transaction_rows)
            transaction = transaction_rows[transaction_index]
            rule = rule_rows[(alert_number // len(transaction_rows)) % len(rule_rows)]
            alert = Alert(
                alert_id=f"ALT-2026-{alert_number + 1:06d}",
                rule_id=rule.rule_id,
                triggering_transaction_id=transaction.transaction_id,
                status="new",
                priority="P4",
                score_contribution_bps=rule.default_score_contribution_bps,
                evidence_json={
                    "schema_version": 1,
                    "source": "deterministic_seed_sample",
                    "summary": "Representative seed alert; no detection engine was run.",
                    "transaction_id": transaction.transaction_id,
                    "rule_id": rule.rule_id,
                },
                detected_at=transaction.transaction_at,
                created_at=transaction.transaction_at,
            )
            alert_rows.append(alert)
            trigger_alerts.setdefault(transaction.transaction_id, []).append(alert)

        for transaction_alerts in trigger_alerts.values():
            priority = priority_for_score(
                min(sum(alert.score_contribution_bps for alert in transaction_alerts), 10_000)
            )
            for alert in transaction_alerts:
                alert.priority = priority
        session.add_all(alert_rows)
        session.flush()

        if alert_rows:
            highest_priority = min(
                (alert.priority for alert in alert_rows),
                key={"P1": 0, "P2": 1, "P3": 2, "P4": 3}.__getitem__,
            )
            first_detected = min(alert.detected_at for alert in alert_rows)
            case = Case(
                case_id="CASE-2026-000001",
                title="Synthetic transaction review sample",
                status="open",
                priority=highest_priority,
                created_at=first_detected,
                updated_at=first_detected,
                created_by_actor_id="system",
            )
            session.add(case)
            session.flush()
            case_links = [
                CaseAlert(
                    case_alert_id=f"CAL-{index:06d}",
                    case_id=case.case_id,
                    alert_id=alert.alert_id,
                    linked_at=alert.detected_at,
                    linked_by_actor_id="system",
                    link_reason="rule_correlation",
                    status="linked",
                )
                for index, alert in enumerate(alert_rows, start=1)
            ]
            review_at = max(alert.detected_at for alert in alert_rows)
            action = AnalystAction(
                action_id="ACT-2026-000001",
                case_id=case.case_id,
                action_type="review_started",
                actor_id="analyst-demo-001",
                action_at=review_at,
                note="Synthetic demo review started.",
                details_json={"source": "seed"},
            )
            session.add_all(case_links + [action])
            session.add_all(
                [
                    AuditEvent(
                        audit_event_id="AUD-2026-000001",
                        event_type="case.created",
                        entity_type="case",
                        entity_id=case.case_id,
                        actor_type="system",
                        event_at=case.created_at,
                        payload_json={"source": "seed"},
                    ),
                    AuditEvent(
                        audit_event_id="AUD-2026-000002",
                        event_type="action.recorded",
                        entity_type="analyst_action",
                        entity_id=action.action_id,
                        actor_type="analyst",
                        actor_id="analyst-demo-001",
                        event_at=action.action_at,
                        payload_json={"source": "seed"},
                    ),
                ]
            )

        sample_transaction = transaction_rows[0]
        sample_account_id = sample_transaction.account_id
        sample_transfer = transfer_rows[0] if transfer_rows else None
        detected_at = alert_rows[0].detected_at if alert_rows else END_AT
        exception_records = [
            ExceptionRecord(
                exception_id="EXC-2026-000001",
                scenario_code="transaction_closed_account",
                subject_type="transaction",
                subject_id="TXN-INVALID-CLOSED",
                status="quarantined",
                validation_code="ACCOUNT_CLOSED",
                reason="Candidate transaction references an account captured as closed; candidate was not posted.",
                payload_json={"candidate_transaction_id": "TXN-INVALID-CLOSED", "account_id": sample_account_id, "account_status": "closed"},
                detected_at=END_AT,
            ),
            ExceptionRecord(
                exception_id="EXC-2026-000002",
                scenario_code="unauthorized_negative_balance",
                subject_type="transaction",
                subject_id="TXN-INVALID-OVERDRAW",
                status="quarantined",
                validation_code="OVERDRAFT_NOT_ALLOWED",
                reason="Candidate debit would exceed the balance of a non-overdraft account; candidate was not posted.",
                payload_json={"account_id": sample_account_id, "opening_candidate_balance_minor": 1, "debit_minor": 2, "overdraft_eligible": False},
                detected_at=END_AT,
            ),
            ExceptionRecord(
                exception_id="EXC-2026-000003",
                scenario_code="transfer_mismatch",
                subject_type="transfer_link",
                subject_id="TRF-INVALID-MISMATCH",
                status="quarantined",
                validation_code="TRANSFER_LEGS_DIFFER",
                reason="Candidate transfer legs have unequal amounts; no operational TransferLink was created.",
                payload_json={
                    "source_transaction_id": sample_transfer.source_transaction_id if sample_transfer else None,
                    "destination_transaction_id": sample_transfer.destination_transaction_id if sample_transfer else None,
                    "source_amount_minor": 1000,
                    "destination_amount_minor": 999,
                },
                detected_at=END_AT,
            ),
            ExceptionRecord(
                exception_id="EXC-2026-000004",
                scenario_code="orphan_alert",
                subject_type="alert",
                subject_id="ALT-INVALID-ORPHAN",
                status="quarantined",
                validation_code="TRIGGER_TRANSACTION_MISSING",
                reason="Candidate alert has no valid triggering transaction and was not inserted into Alert.",
                payload_json={"candidate_alert_id": "ALT-INVALID-ORPHAN", "triggering_transaction_id": None},
                detected_at=END_AT,
            ),
            ExceptionRecord(
                exception_id="EXC-2026-000005",
                scenario_code="disposition_before_alert",
                subject_type="analyst_action",
                subject_id="ACT-INVALID-CHRONOLOGY",
                status="quarantined",
                validation_code="ACTION_PRECEDES_ALERT",
                reason="Candidate disposition time precedes alert detection and was not inserted as an accepted AnalystAction.",
                payload_json={
                    "candidate_case_id": "CASE-2026-000001" if alert_rows else None,
                    "candidate_alert_id": alert_rows[0].alert_id if alert_rows else None,
                    "candidate_action_at": (detected_at - timedelta(seconds=1)).isoformat(),
                    "alert_detected_at": detected_at.isoformat(),
                    "action_type": "disposition_recorded",
                },
                detected_at=END_AT,
            ),
        ]
        session.add_all(exception_records)
        session.flush()

        counts = validate_dataset(session)
        counts["ground_truth_records"] = len(truth_records)
        counts["exception_scenarios"] = len(exception_records)
        counts["transfer_links"] = len(transfer_rows)
        counts["alerts"] = len(alert_rows)

    if truth_path is not None:
        counts["ground_truth_sha256"] = _write_truth(truth_path, truth_records)
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Create deterministic RiskTrace AI demo records.")
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--ground-truth", type=Path, default=None)
    parser.add_argument(
        "--reset",
        action="store_true",
        help="remove the exact SQLite database file only if it contains no analyst/audit history",
    )
    parser.add_argument("--seed", type=int, default=SEED)
    for key, default in DEFAULT_COUNTS.items():
        parser.add_argument(f"--{key}", type=int, default=default)
    args = parser.parse_args()
    config = SeedConfig(
        customers=args.customers,
        accounts=args.accounts,
        merchants=args.merchants,
        devices=args.devices,
        transactions=args.transactions,
        alerts=args.alerts,
        seed=args.seed,
    )
    repository_root = Path(__file__).resolve().parents[3]
    ground_truth = args.ground_truth or repository_root / "ground_truth" / "generated" / "truth_2026.jsonl"
    engine = make_engine(args.database_url)
    if args.reset:
        if engine.dialect.name != "sqlite" or engine.url.database in (None, "", ":memory:"):
            raise ValueError("--reset requires a file-backed SQLite database URL")
        existing_tables = set(inspect(engine).get_table_names())
        if {"analyst_action", "audit_event"} <= existing_tables:
            with engine.connect() as connection:
                history_count = connection.execute(
                    text(
                        "SELECT (SELECT count(*) FROM analyst_action) + "
                        "(SELECT count(*) FROM audit_event)"
                    )
                ).scalar_one()
            if history_count:
                raise RuntimeError("reset refused because analyst/audit history must be retained")
        database_file = Path(engine.url.database).resolve()
        engine.dispose()
        if database_file.exists():
            if not database_file.is_file():
                raise ValueError("SQLite database path does not resolve to a file")
            database_file.unlink()
        engine = make_engine(args.database_url)
    upgrade_database(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        result = generate_dataset(session, config, ground_truth)
    engine.dispose()
    print(json.dumps({"counts": result, "ground_truth_path": str(ground_truth)}, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
