import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.audit import AuditLog


class AuditLogRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def record(
        self,
        event_type: str,
        actor_id: uuid.UUID | None = None,
        target_id: uuid.UUID | None = None,
        target_type: str | None = None,
        ip_address: str | None = None,
        metadata: dict | None = None,
    ) -> AuditLog:
        entry = AuditLog(
            id=uuid.uuid4(),
            event_type=event_type,
            actor_id=actor_id,
            target_id=target_id,
            target_type=target_type,
            ip_address=ip_address,
            metadata=metadata,
        )
        self._db.add(entry)
        await self._db.flush()
        return entry
