import json
import logging
from datetime import UTC, datetime

# Standard LogRecord attributes — excluded from the extra-fields merge
_LOG_RECORD_ATTRS = frozenset(
    {
        "args",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "message",
        "module",
        "msecs",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "thread",
        "threadName",
        "taskName",
    }
)


class JsonFormatter(logging.Formatter):
    """Formats every log record as a single JSON line.

    If the message is itself a JSON object (e.g. pre-encoded by security_log),
    its fields are merged into the outer record so the output stays flat and
    queryable by CloudWatch Insights without nested-field syntax.
    """

    def format(self, record: logging.LogRecord) -> str:
        base: dict = {
            "ts": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
        }

        msg = record.getMessage()
        try:
            parsed = json.loads(msg)
            if isinstance(parsed, dict):
                # Flatten pre-encoded JSON (security_log events) into the record.
                # The inner "ts" wins over ours — it's the event-generation timestamp.
                base.update(parsed)
            else:
                base["message"] = msg
        except (json.JSONDecodeError, ValueError):
            base["message"] = msg

        # Merge caller-supplied extra fields (e.g. method, path, status_code)
        for key, val in record.__dict__.items():
            if key not in _LOG_RECORD_ATTRS and not key.startswith("_") and key not in base:
                base[key] = val

        if record.exc_info:
            base["exc"] = self.formatException(record.exc_info)

        return json.dumps(base, default=str)
