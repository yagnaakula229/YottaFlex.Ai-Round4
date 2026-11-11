from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TransactionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    transaction_id: str
    account_id: str
    merchant_id: str | None
    device_id: str | None
    transaction_type: str
    status: str
    transaction_at: datetime
    posted_at: datetime | None
    currency: str
    debit_minor: int
    credit_minor: int
    opening_balance_minor: int | None
    closing_balance_minor: int | None
