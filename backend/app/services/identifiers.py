from sqlalchemy import select
from sqlalchemy.orm import Session


def next_yearly_identifier(session: Session, model, field_name: str, prefix: str, year: int) -> str:
    field = getattr(model, field_name)
    stem = f"{prefix}-{year}-"
    latest = session.scalar(
        select(field)
        .where(field.like(f"{stem}%"))
        .order_by(field.desc())
        .limit(1)
    )
    latest_sequence = int(latest.rsplit("-", 1)[1]) if latest else 0
    pending_sequences = [
        int(value.rsplit("-", 1)[1])
        for item in session.new
        if isinstance(item, model)
        for value in [getattr(item, field_name)]
        if value and value.startswith(stem) and value.rsplit("-", 1)[1].isdigit()
    ]
    sequence = max([latest_sequence, *pending_sequences]) + 1
    return f"{stem}{sequence:06d}"
