from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    BigInteger,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
    inspect as sa_inspect,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base
from app.database.types import UTCDateTime

USD = "USD"
ACCOUNT_STATUSES = "'pending','open','dormant','frozen','closed'"
TRANSACTION_STATUSES = "'pending','posted','declined','voided'"
TRANSFER_STATUSES = "'pending','reconciled','voided'"
ALERT_STATUSES = "'new','acknowledged','in_review','escalated','resolved','closed'"
CASE_STATUSES = "'open','in_review','escalated','resolved','closed'"
PRIORITIES = "'P1','P2','P3','P4'"


class Customer(Base):
    __tablename__ = "customer"
    __table_args__ = (
        CheckConstraint("status IN ('active','suspended','closed')", name="ck_customer_status"),
        CheckConstraint("updated_at >= created_at", name="ck_customer_updated"),
    )

    customer_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)

    kyc_profiles: Mapped[list["KYCProfile"]] = relationship(back_populates="customer", passive_deletes="all")
    account_links: Mapped[list["CustomerAccount"]] = relationship(back_populates="customer", passive_deletes="all")
    device_links: Mapped[list["CustomerDevice"]] = relationship(back_populates="customer", passive_deletes="all")


class Account(Base):
    __tablename__ = "account"
    __table_args__ = (
        CheckConstraint("currency = 'USD'", name="ck_account_currency_usd"),
        CheckConstraint("opening_balance_minor >= 0", name="ck_account_opening_balance"),
        CheckConstraint("overdraft_limit_minor >= 0", name="ck_account_overdraft_limit"),
        CheckConstraint("overdraft_eligible = 1 OR overdraft_limit_minor = 0", name="ck_account_overdraft_policy"),
        CheckConstraint(f"status IN ({ACCOUNT_STATUSES})", name="ck_account_status"),
        CheckConstraint("status != 'closed' OR closed_at IS NOT NULL", name="ck_account_closed_at_required"),
        CheckConstraint("status = 'closed' OR closed_at IS NULL", name="ck_account_closed_at_only_closed"),
        CheckConstraint("closed_at IS NULL OR closed_at >= opened_at", name="ck_account_closed_at"),
        Index("ix_account_status", "status"),
    )

    account_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default=USD)
    opening_balance_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    overdraft_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    overdraft_limit_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    opened_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)

    ownership_links: Mapped[list["CustomerAccount"]] = relationship(back_populates="account", passive_deletes="all")
    transactions: Mapped[list["Transaction"]] = relationship(
        back_populates="account", foreign_keys="Transaction.account_id", passive_deletes="all"
    )
    source_transfers: Mapped[list["TransferLink"]] = relationship(
        back_populates="source_account", foreign_keys="TransferLink.source_account_id", passive_deletes="all"
    )
    destination_transfers: Mapped[list["TransferLink"]] = relationship(
        back_populates="destination_account", foreign_keys="TransferLink.destination_account_id", passive_deletes="all"
    )


class Merchant(Base):
    __tablename__ = "merchant"
    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0", name="ck_merchant_name"),
        CheckConstraint("status IN ('active','inactive','blocked')", name="ck_merchant_status"),
        CheckConstraint("country_code IS NULL OR length(country_code) = 2", name="ck_merchant_country"),
    )

    merchant_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    category_code: Mapped[str] = mapped_column(String(32), nullable=False)
    country_code: Mapped[str | None] = mapped_column(String(2))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)

    transactions: Mapped[list["Transaction"]] = relationship(back_populates="merchant", passive_deletes="all")


class Device(Base):
    __tablename__ = "device"
    __table_args__ = (
        CheckConstraint("device_type IN ('mobile','web','tablet','other')", name="ck_device_type"),
        CheckConstraint("status IN ('active','revoked','unknown')", name="ck_device_status"),
    )

    device_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    device_type: Mapped[str] = mapped_column(String(16), nullable=False)
    fingerprint_hash: Mapped[str | None] = mapped_column(String(128), unique=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    first_seen_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)

    customer_links: Mapped[list["CustomerDevice"]] = relationship(back_populates="device", passive_deletes="all")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="device", passive_deletes="all")


class Transaction(Base):
    __tablename__ = "transaction_record"
    __table_args__ = (
        UniqueConstraint("account_id", "transaction_id", name="uq_transaction_account_id"),
        CheckConstraint("transaction_type IN ('purchase','cash_withdrawal','deposit','transfer','fee','refund','adjustment')", name="ck_transaction_type"),
        CheckConstraint(f"status IN ({TRANSACTION_STATUSES})", name="ck_transaction_status"),
        CheckConstraint("currency = 'USD'", name="ck_transaction_currency_usd"),
        CheckConstraint("debit_minor >= 0 AND credit_minor >= 0", name="ck_transaction_nonnegative_amounts"),
        CheckConstraint(
            "status != 'posted' OR ((debit_minor > 0 AND credit_minor = 0) OR (credit_minor > 0 AND debit_minor = 0))",
            name="ck_transaction_posted_amount_direction",
        ),
        CheckConstraint(
            "status != 'posted' OR (posted_at IS NOT NULL AND opening_balance_minor IS NOT NULL "
            "AND closing_balance_minor IS NOT NULL AND account_status_at_posting IN ('open','dormant'))",
            name="ck_transaction_posted_snapshot",
        ),
        CheckConstraint("posted_at IS NULL OR posted_at >= transaction_at", name="ck_transaction_posted_time"),
        CheckConstraint(
            "status = 'posted' OR (posted_at IS NULL AND opening_balance_minor IS NULL "
            "AND closing_balance_minor IS NULL AND account_status_at_posting IS NULL)",
            name="ck_transaction_unposted_snapshot",
        ),
        CheckConstraint(
            "status != 'posted' OR closing_balance_minor = opening_balance_minor - debit_minor + credit_minor",
            name="ck_transaction_balance_equation",
        ),
        ForeignKeyConstraint(
            ["reversal_of_transaction_id"], ["transaction_record.transaction_id"], ondelete="RESTRICT"
        ),
        Index("ix_transaction_account_time_id", "account_id", "transaction_at", "transaction_id"),
        Index("ix_transaction_time_id", "transaction_at", "transaction_id"),
        Index("ix_transaction_merchant_time", "merchant_id", "transaction_at"),
        Index("ix_transaction_device_time", "device_id", "transaction_at"),
    )

    transaction_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("account.account_id", ondelete="RESTRICT"), nullable=False)
    merchant_id: Mapped[str | None] = mapped_column(ForeignKey("merchant.merchant_id", ondelete="RESTRICT"))
    device_id: Mapped[str | None] = mapped_column(ForeignKey("device.device_id", ondelete="RESTRICT"))
    transaction_type: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    transaction_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    posted_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default=USD)
    debit_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    credit_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    opening_balance_minor: Mapped[int | None] = mapped_column(BigInteger)
    closing_balance_minor: Mapped[int | None] = mapped_column(BigInteger)
    account_status_at_posting: Mapped[str | None] = mapped_column(String(16))
    reversal_of_transaction_id: Mapped[str | None] = mapped_column(String(40), unique=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)

    account: Mapped[Account] = relationship(back_populates="transactions", foreign_keys=[account_id])
    merchant: Mapped[Merchant | None] = relationship(back_populates="transactions")
    device: Mapped[Device | None] = relationship(back_populates="transactions")
    source_transfer: Mapped["TransferLink | None"] = relationship(
        back_populates="source_transaction", foreign_keys="TransferLink.source_transaction_id", uselist=False
    )
    destination_transfer: Mapped["TransferLink | None"] = relationship(
        back_populates="destination_transaction", foreign_keys="TransferLink.destination_transaction_id", uselist=False
    )
    reversal_of: Mapped["Transaction | None"] = relationship(
        remote_side=[transaction_id], foreign_keys=[reversal_of_transaction_id], back_populates="reversal"
    )
    reversal: Mapped["Transaction | None"] = relationship(
        foreign_keys=[reversal_of_transaction_id], back_populates="reversal_of", uselist=False
    )
    alerts: Mapped[list["Alert"]] = relationship(back_populates="triggering_transaction", passive_deletes="all")


class TransferLink(Base):
    __tablename__ = "transfer_link"
    __table_args__ = (
        ForeignKeyConstraint(
            ["source_account_id", "source_transaction_id"],
            ["transaction_record.account_id", "transaction_record.transaction_id"],
            ondelete="RESTRICT",
            name="fk_transfer_source_account_transaction",
        ),
        ForeignKeyConstraint(
            ["destination_account_id", "destination_transaction_id"],
            ["transaction_record.account_id", "transaction_record.transaction_id"],
            ondelete="RESTRICT",
            name="fk_transfer_destination_account_transaction",
        ),
        CheckConstraint("source_account_id != destination_account_id", name="ck_transfer_distinct_accounts"),
        CheckConstraint("currency = 'USD'", name="ck_transfer_currency_usd"),
        CheckConstraint("source_amount_minor > 0 AND destination_amount_minor > 0", name="ck_transfer_positive_amounts"),
        CheckConstraint("source_amount_minor = destination_amount_minor", name="ck_transfer_equal_amounts"),
        CheckConstraint(f"status IN ({TRANSFER_STATUSES})", name="ck_transfer_status"),
        CheckConstraint("status != 'reconciled' OR reconciled_at IS NOT NULL", name="ck_transfer_reconciled_at"),
        CheckConstraint("source_transaction_id != destination_transaction_id", name="ck_transfer_distinct_legs"),
        UniqueConstraint("source_transaction_id", name="uq_transfer_source_transaction"),
        UniqueConstraint("destination_transaction_id", name="uq_transfer_destination_transaction"),
        Index("ix_transfer_source_account_time", "source_account_id", "initiated_at"),
        Index("ix_transfer_destination_account_time", "destination_account_id", "initiated_at"),
    )

    transfer_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    source_account_id: Mapped[str] = mapped_column(ForeignKey("account.account_id", ondelete="RESTRICT"), nullable=False)
    destination_account_id: Mapped[str] = mapped_column(ForeignKey("account.account_id", ondelete="RESTRICT"), nullable=False)
    source_transaction_id: Mapped[str] = mapped_column(ForeignKey("transaction_record.transaction_id", ondelete="RESTRICT"), nullable=False)
    destination_transaction_id: Mapped[str] = mapped_column(ForeignKey("transaction_record.transaction_id", ondelete="RESTRICT"), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default=USD)
    source_amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    destination_amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    initiated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    reconciled_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)

    source_account: Mapped[Account] = relationship(back_populates="source_transfers", foreign_keys=[source_account_id])
    destination_account: Mapped[Account] = relationship(back_populates="destination_transfers", foreign_keys=[destination_account_id])
    source_transaction: Mapped[Transaction] = relationship(back_populates="source_transfer", foreign_keys=[source_transaction_id])
    destination_transaction: Mapped[Transaction] = relationship(back_populates="destination_transfer", foreign_keys=[destination_transaction_id])


class RiskRule(Base):
    __tablename__ = "risk_rule"
    __table_args__ = (
        UniqueConstraint("rule_key", "version", name="uq_risk_rule_key_version"),
        CheckConstraint("rule_key IN ('velocity_spike','high_value','new_device','dormant_reactivation','circular_transfer','linked_suspicious')", name="ck_risk_rule_key"),
        CheckConstraint("version >= 1", name="ck_risk_rule_version"),
        CheckConstraint("status IN ('draft','active','retired')", name="ck_risk_rule_status"),
        CheckConstraint("default_score_contribution_bps BETWEEN 0 AND 10000", name="ck_risk_rule_score"),
        CheckConstraint("status != 'active' OR effective_at IS NOT NULL", name="ck_risk_rule_effective"),
        CheckConstraint("retired_at IS NULL OR effective_at IS NULL OR retired_at >= effective_at", name="ck_risk_rule_retired_at"),
    )

    rule_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    rule_key: Mapped[str] = mapped_column(String(48), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    parameters_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    default_score_contribution_bps: Mapped[int] = mapped_column(Integer, nullable=False)
    effective_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    retired_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)

    alerts: Mapped[list["Alert"]] = relationship(back_populates="rule", passive_deletes="all")


class Alert(Base):
    __tablename__ = "alert"
    __table_args__ = (
        UniqueConstraint("rule_id", "triggering_transaction_id", name="uq_alert_rule_transaction"),
        CheckConstraint(f"status IN ({ALERT_STATUSES})", name="ck_alert_status"),
        CheckConstraint(f"priority IN ({PRIORITIES})", name="ck_alert_priority"),
        CheckConstraint("score_contribution_bps BETWEEN 0 AND 10000", name="ck_alert_score"),
        Index("ix_alert_queue", "status", "priority", "detected_at", "alert_id"),
        Index("ix_alert_priority_time", "priority", "detected_at"),
        Index("ix_alert_rule", "rule_id", "detected_at"),
        Index("ix_alert_trigger_tx", "triggering_transaction_id"),
    )

    alert_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    rule_id: Mapped[str] = mapped_column(ForeignKey("risk_rule.rule_id", ondelete="RESTRICT"), nullable=False)
    triggering_transaction_id: Mapped[str] = mapped_column(ForeignKey("transaction_record.transaction_id", ondelete="RESTRICT"), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="new")
    priority: Mapped[str] = mapped_column(String(2), nullable=False)
    score_contribution_bps: Mapped[int] = mapped_column(Integer, nullable=False)
    evidence_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    detected_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)

    rule: Mapped[RiskRule] = relationship(back_populates="alerts")
    triggering_transaction: Mapped[Transaction] = relationship(back_populates="alerts")
    case_links: Mapped[list["CaseAlert"]] = relationship(back_populates="alert", passive_deletes="all")
    actions: Mapped[list["AnalystAction"]] = relationship(back_populates="alert", passive_deletes="all")


class Case(Base):
    __tablename__ = "case_record"
    __table_args__ = (
        CheckConstraint("length(trim(title)) > 0", name="ck_case_title"),
        CheckConstraint(f"status IN ({CASE_STATUSES})", name="ck_case_status"),
        CheckConstraint(f"priority IN ({PRIORITIES})", name="ck_case_priority"),
        CheckConstraint("updated_at >= created_at", name="ck_case_updated"),
        CheckConstraint("resolved_at IS NULL OR resolved_at >= created_at", name="ck_case_resolved_at"),
        CheckConstraint("closed_at IS NULL OR closed_at >= created_at", name="ck_case_closed_at"),
        Index("ix_case_status_priority_updated", "status", "priority", "updated_at", "case_id"),
    )

    case_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    priority: Mapped[str] = mapped_column(String(2), nullable=False, default="P4")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    closed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    created_by_actor_id: Mapped[str | None] = mapped_column(String(64))

    alert_links: Mapped[list["CaseAlert"]] = relationship(back_populates="case", passive_deletes="all")
    actions: Mapped[list["AnalystAction"]] = relationship(back_populates="case", passive_deletes="all")


class AnalystAction(Base):
    __tablename__ = "analyst_action"
    __table_args__ = (
        CheckConstraint("action_type IN ('review_started','note_added','disposition_recorded','status_changed','escalated','alert_linked','alert_unlinked','case_closed','case_reopened')", name="ck_action_type"),
        CheckConstraint("disposition IS NULL OR disposition IN ('suspicious','false_positive','inconclusive','referred')", name="ck_action_disposition"),
        CheckConstraint("action_type != 'disposition_recorded' OR disposition IS NOT NULL", name="ck_action_disposition_required"),
        CheckConstraint("note IS NULL OR length(note) <= 500", name="ck_action_note_length"),
        Index("ix_analyst_action_case_time", "case_id", "action_at", "action_id"),
        Index("ix_analyst_action_alert_time", "alert_id", "action_at"),
    )

    action_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("case_record.case_id", ondelete="RESTRICT"), nullable=False)
    alert_id: Mapped[str | None] = mapped_column(ForeignKey("alert.alert_id", ondelete="RESTRICT"))
    action_type: Mapped[str] = mapped_column(String(32), nullable=False)
    disposition: Mapped[str | None] = mapped_column(String(24))
    actor_id: Mapped[str] = mapped_column(String(64), nullable=False)
    action_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    note: Mapped[str | None] = mapped_column(String(500))
    details_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), unique=True)

    case: Mapped[Case] = relationship(back_populates="actions")
    alert: Mapped[Alert | None] = relationship(back_populates="actions")


class KYCProfile(Base):
    __tablename__ = "kyc_profile"
    __table_args__ = (
        UniqueConstraint("customer_id", "version", name="uq_kyc_customer_version"),
        CheckConstraint("version >= 1", name="ck_kyc_version"),
        CheckConstraint("status IN ('pending','verified','rejected','expired')", name="ck_kyc_status"),
        CheckConstraint("risk_rating IN ('unknown','low','medium','high')", name="ck_kyc_risk"),
        CheckConstraint("expires_at IS NULL OR expires_at > effective_at", name="ck_kyc_expiry"),
        Index("ix_kyc_customer_effective", "customer_id", "effective_at"),
    )

    kyc_profile_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customer.customer_id", ondelete="RESTRICT"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    risk_rating: Mapped[str] = mapped_column(String(16), nullable=False, default="unknown")
    effective_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    attributes_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)

    customer: Mapped[Customer] = relationship(back_populates="kyc_profiles")


class CustomerAccount(Base):
    __tablename__ = "customer_account"
    __table_args__ = (
        UniqueConstraint("customer_id", "account_id", "valid_from", name="uq_customer_account_valid_from"),
        CheckConstraint("relationship_type IN ('primary_owner','joint_owner','beneficial_owner','authorized_user')", name="ck_owner_relationship"),
        CheckConstraint("ownership_share_bps IS NULL OR ownership_share_bps BETWEEN 0 AND 10000", name="ck_owner_share"),
        CheckConstraint("status IN ('active','ended')", name="ck_owner_status"),
        CheckConstraint("valid_to IS NULL OR valid_to > valid_from", name="ck_owner_valid_to"),
        CheckConstraint("status != 'ended' OR valid_to IS NOT NULL", name="ck_owner_ended_at"),
        Index("ix_customer_account_customer", "customer_id", "status", "account_id"),
        Index("ix_customer_account_account", "account_id", "status", "customer_id"),
    )

    customer_account_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customer.customer_id", ondelete="RESTRICT"), nullable=False)
    account_id: Mapped[str] = mapped_column(ForeignKey("account.account_id", ondelete="RESTRICT"), nullable=False)
    relationship_type: Mapped[str] = mapped_column(String(24), nullable=False)
    ownership_share_bps: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    valid_from: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    valid_to: Mapped[datetime | None] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)

    customer: Mapped[Customer] = relationship(back_populates="account_links")
    account: Mapped[Account] = relationship(back_populates="ownership_links")


class CustomerDevice(Base):
    __tablename__ = "customer_device"
    __table_args__ = (
        UniqueConstraint("customer_id", "device_id", name="uq_customer_device"),
        CheckConstraint("status IN ('active','revoked')", name="ck_customer_device_status"),
        CheckConstraint("last_seen_at IS NULL OR last_seen_at >= first_seen_at", name="ck_customer_device_last_seen"),
        Index("ix_customer_device_customer", "customer_id", "status", "device_id"),
        Index("ix_customer_device_device", "device_id", "status", "customer_id"),
    )

    customer_device_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customer.customer_id", ondelete="RESTRICT"), nullable=False)
    device_id: Mapped[str] = mapped_column(ForeignKey("device.device_id", ondelete="RESTRICT"), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    first_seen_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)

    customer: Mapped[Customer] = relationship(back_populates="device_links")
    device: Mapped[Device] = relationship(back_populates="customer_links")


class CaseAlert(Base):
    __tablename__ = "case_alert"
    __table_args__ = (
        UniqueConstraint("case_id", "alert_id", name="uq_case_alert"),
        CheckConstraint("status IN ('linked','unlinked')", name="ck_case_alert_status"),
        CheckConstraint("link_reason IN ('rule_correlation','manual','reopened')", name="ck_case_alert_reason"),
        CheckConstraint("unlinked_at IS NULL OR unlinked_at >= linked_at", name="ck_case_alert_unlinked_at"),
        CheckConstraint("status != 'unlinked' OR unlinked_at IS NOT NULL", name="ck_case_alert_unlinked_required"),
        Index("ix_case_alert_alert", "alert_id", "case_id"),
    )

    case_alert_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("case_record.case_id", ondelete="RESTRICT"), nullable=False)
    alert_id: Mapped[str] = mapped_column(ForeignKey("alert.alert_id", ondelete="RESTRICT"), nullable=False)
    linked_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    linked_by_actor_id: Mapped[str] = mapped_column(String(64), nullable=False)
    link_reason: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="linked")
    unlinked_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    case: Mapped[Case] = relationship(back_populates="alert_links")
    alert: Mapped[Alert] = relationship(back_populates="case_links")


class ExceptionRecord(Base):
    __tablename__ = "exception_record"
    __table_args__ = (
        CheckConstraint("scenario_code IN ('transaction_closed_account','unauthorized_negative_balance','transfer_mismatch','orphan_alert','disposition_before_alert')", name="ck_exception_scenario"),
        CheckConstraint("status IN ('detected','quarantined','rejected','resolved')", name="ck_exception_status"),
        CheckConstraint("length(trim(reason)) > 0", name="ck_exception_reason"),
        CheckConstraint("resolved_at IS NULL OR resolved_at >= detected_at", name="ck_exception_resolved_at"),
        Index("ix_exception_status_time", "status", "detected_at"),
    )

    exception_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    scenario_code: Mapped[str] = mapped_column(String(48), nullable=False)
    subject_type: Mapped[str] = mapped_column(String(48), nullable=False)
    subject_id: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="detected")
    validation_code: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    detected_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class AuditEvent(Base):
    __tablename__ = "audit_event"
    __table_args__ = (
        CheckConstraint("actor_type IN ('system','analyst','operator')", name="ck_audit_actor_type"),
        Index("ix_audit_subject_time", "entity_type", "entity_id", "event_at"),
    )

    audit_event_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(48), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(64))
    event_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(64))
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


@event.listens_for(AnalystAction, "before_update")
def prevent_analyst_action_update(mapper, connection, target):
    raise ValueError("AnalystAction rows are append-only")


@event.listens_for(AnalystAction, "before_delete")
def prevent_analyst_action_delete(mapper, connection, target):
    raise ValueError("AnalystAction rows are append-only")


@event.listens_for(AuditEvent, "before_update")
def prevent_audit_event_update(mapper, connection, target):
    raise ValueError("AuditEvent rows are append-only")


@event.listens_for(AuditEvent, "before_delete")
def prevent_audit_event_delete(mapper, connection, target):
    raise ValueError("AuditEvent rows are append-only")


def prevent_primary_key_update(mapper, connection, target):
    state = sa_inspect(target)
    if any(state.attrs[column.key].history.has_changes() for column in mapper.primary_key):
        raise ValueError(f"{mapper.class_.__name__} identifiers are immutable")


def prevent_active_rule_update(mapper, connection, target):
    state = sa_inspect(target)
    previous_status = state.attrs.status.history.deleted
    was_active = bool(previous_status and previous_status[0] == "active") or target.status == "active"
    alert_table = Alert.__table__
    referenced = connection.execute(
        alert_table.select()
        .with_only_columns(alert_table.c.alert_id)
        .where(alert_table.c.rule_id == target.rule_id)
        .limit(1)
    ).first()
    protected_fields = (
        "rule_key",
        "version",
        "name",
        "description",
        "parameters_json",
        "default_score_contribution_bps",
        "effective_at",
        "created_at",
    )
    if (was_active or referenced) and any(state.attrs[name].history.has_changes() for name in protected_fields):
        raise ValueError("active or referenced risk-rule versions are immutable")


for entity_model in (
    Customer,
    Account,
    Merchant,
    Device,
    Transaction,
    TransferLink,
    RiskRule,
    Alert,
    Case,
    AnalystAction,
    KYCProfile,
    CustomerAccount,
    CustomerDevice,
    CaseAlert,
    ExceptionRecord,
    AuditEvent,
):
    event.listen(entity_model, "before_update", prevent_primary_key_update)
event.listen(RiskRule, "before_update", prevent_active_rule_update)
