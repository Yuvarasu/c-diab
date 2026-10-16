from app.models import AuditLog


def audit(db, actor_id, action: str, entity_type: str, entity_id=None, **meta) -> None:
    """Record a privileged or sensitive action. Never put health details in meta. Caller commits."""
    db.add(AuditLog(actor_id=actor_id, action=action, entity_type=entity_type,
                    entity_id=str(entity_id) if entity_id is not None else None, meta=meta))
