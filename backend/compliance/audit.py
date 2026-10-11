from .models import AuditLog


def client_ip(request):
    if request is None:
        return None
    fwd = request.META.get("HTTP_X_FORWARDED_FOR")
    return (fwd.split(",")[0].strip() if fwd else request.META.get("REMOTE_ADDR")) or None


def audit(actor, action, obj=None, meta=None, request=None, object_type="", object_id=""):
    """audit(actor, action, obj, meta) — actor may be a User, a string, or None (system)."""
    if actor is None:
        actor_s = "system"
    elif isinstance(actor, str):
        actor_s = actor
    else:
        actor_s = getattr(actor, "email", None) or f"{getattr(actor, 'role', 'user')}:{getattr(actor, 'pk', '')}"
    if obj is not None:
        object_type = object_type or obj.__class__.__name__
        object_id = object_id or str(getattr(obj, "pk", ""))
    return AuditLog.objects.create(actor=actor_s, action=action, object_type=object_type, object_id=object_id,
                                   ip=client_ip(request), metadata=meta or {})
