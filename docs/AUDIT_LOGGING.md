# Audit Logging

All security-relevant events are logged to Firestore collection `audit_logs` for compliance, forensics, and incident investigation.

## Event Types

**Camera Management**
- `camera_registered` — Camera added to system
- `camera_deleted` — Camera removed from system
- `camera_reboot` — Reboot command sent
- `camera_ota_check` — OTA check requested
- `camera_diag_requested` — Diagnostics requested

**Person/Face Management**
- `person_created` — New person enrolled
- `person_deleted` — Person removed
- `person_updated` — Person metadata changed
- `face_enrolled` — Face image added to person record

**Firmware**
- `firmware_uploaded` — New firmware binary uploaded
- `firmware_downloaded` — Camera downloaded firmware

**System Control**
- `system_armed` — Surveillance enabled
- `system_disarmed` — Surveillance disabled

**Webhooks**
- `webhook_created` — Detection callback registered
- `webhook_deleted` — Callback removed
- `webhook_delivery_failed` — Callback delivery error

**Security**
- `auth_failed` — Invalid API key or authentication error
- `rate_limit_exceeded` — Rate limit violation

## Audit Log Entry Format

```json
{
  "timestamp": "2026-06-23T12:34:56.789Z",
  "event_type": "camera_registered",
  "actor": "api",
  "resource": "s3eye-01",
  "resource_type": "camera",
  "success": true,
  "error_reason": null,
  "details": {
    "type": "s3eye",
    "ip": "192.168.1.50"
  }
}
```

## Using Audit Logging

### Import and Use in API Routes

```python
from audit import log_camera_registered, log_person_deleted

# In an async endpoint:
await log_camera_registered(
    actor="api",
    camera_id="s3eye-01",
    camera_type="s3eye",
    ip="192.168.1.50"
)
```

### Error Logging

```python
from audit import log_audit_event, AuditEventType

try:
    # Do something
    pass
except Exception as exc:
    await log_audit_event(
        AuditEventType.CAMERA_REBOOT,
        actor="api",
        resource="s3eye-01",
        resource_type="camera",
        success=False,
        error_reason=str(exc),
    )
```

## Querying Audit Logs

### Firestore Console

Navigate to Firestore → Collection `audit_logs` → Browse documents.

### Python

```python
from db.firestore import get_db
from datetime import datetime, timedelta, timezone

db = get_db()
collection = db.collection("audit_logs")

# Events in the last 24 hours
yesterday = datetime.now(timezone.utc) - timedelta(days=1)
docs = collection.where("timestamp", ">", yesterday).stream()
for doc in docs:
    print(doc.to_dict())

# Events for a specific resource
camera_events = collection.where("resource", "==", "s3eye-01").stream()

# Failed events only
failures = collection.where("success", "==", False).stream()
```

### Firestore Query Examples

**All admin actions in the last 7 days:**
```
collection("audit_logs")
  .where("timestamp", ">", now - 7 days)
  .orderBy("timestamp", "desc")
```

**Failed firmware uploads:**
```
collection("audit_logs")
  .where("event_type", "==", "firmware_uploaded")
  .where("success", "==", false)
```

**All actions on a specific camera:**
```
collection("audit_logs")
  .where("resource", "==", "xiao-01")
  .orderBy("timestamp", "desc")
```

## Retention and Archival

**Current Policy**: No automatic deletion (append-only log)

**Recommended**:
- Retain all audit logs indefinitely (storage is cheap)
- Archive to Cloud Storage monthly for backup
- Set up alerting on failed authentication events

## Compliance and Forensics

Audit logs support investigations like:

- **"When was camera X registered?"** → Query by resource & event_type
- **"Who last modified person Y?"** → Query by resource & timestamp
- **"What actions failed today?"** → Query by success=false & timestamp
- **"What firmware was uploaded at time Z?"** → Query by event_type & timestamp

## Integration Checklist

Audit logging is currently integrated into:
- ✅ Camera registration (`cameras.py:register`)
- ✅ Camera deletion (`cameras.py:delete_camera`)

Still needs integration:
- ⏳ `persons.py`: create_person, delete_person, add_face_image
- ⏳ `firmware.py`: upload_firmware
- ⏳ `system.py`: arm, disarm
- ⏳ `webhooks.py`: create_webhook, delete_webhook
- ⏳ `main.py`: auth failures (FastAPI exception handler)

## Security Considerations

- **Immutable**: Audit logs cannot be deleted (Firestore allows document write but changing event_type or timestamp is application-level audit failure)
- **Protected**: Firestore IAM should restrict write to app service account only
- **Privacy**: Audit logs may contain sensitive data (IPs, camera IDs); treat as confidential
- **Not Real-Time**: Logs are written asynchronously; expect 1–5 second delay

## Future Enhancements

- [ ] Export audit logs to external SIEM (Splunk, ELK)
- [ ] Real-time alerts on suspicious patterns
- [ ] Dashboard for audit log visualization
- [ ] Immutable cloud storage archive (GCS Retention Lock)
- [ ] Performance optimization (logging may slow writes at scale)
