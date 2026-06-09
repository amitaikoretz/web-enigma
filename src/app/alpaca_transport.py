from __future__ import annotations

import errno
import socket
import ssl
from urllib.error import URLError

_TRANSIENT_ERRNOS = {
    errno.ECONNABORTED,
    errno.ECONNREFUSED,
    errno.ECONNRESET,
    errno.EHOSTDOWN,
    errno.EHOSTUNREACH,
    errno.ENETDOWN,
    errno.ENETRESET,
    errno.ENETUNREACH,
    errno.EPIPE,
    errno.ETIMEDOUT,
}


def alpaca_transport_failure_label(exc: URLError) -> str:
    reason = getattr(exc, "reason", None)
    if isinstance(reason, socket.gaierror):
        return "temporary DNS failure" if reason.errno == -3 else "DNS failure"
    if isinstance(reason, ssl.SSLEOFError):
        return "transient TLS/network handshake failure"
    if isinstance(reason, ssl.SSLError):
        message = str(reason).lower()
        if "wrong version number" in message:
            return "TLS protocol mismatch"
        if "unexpected eof while reading" in message or "handshake" in message or "tlsv1 alert" in message:
            return "transient TLS/network handshake failure"
        return "TLS failure"

    errno_value = getattr(reason, "errno", None)
    if errno_value in _TRANSIENT_ERRNOS:
        return "transient network failure"
    return "network failure"


def is_temporary_alpaca_transport_failure(exc: URLError) -> bool:
    reason = getattr(exc, "reason", None)
    if isinstance(reason, socket.gaierror):
        return reason.errno == -3
    if isinstance(reason, ssl.SSLEOFError):
        return True
    if isinstance(reason, ssl.SSLError):
        message = str(reason).lower()
        if "wrong version number" in message:
            return False
        if "unexpected eof while reading" in message or "handshake" in message or "tlsv1 alert" in message:
            return True
        return False

    errno_value = getattr(reason, "errno", None)
    return errno_value in _TRANSIENT_ERRNOS


def format_alpaca_transport_failure_message(*, service: str, exc: URLError) -> str:
    reason = getattr(exc, "reason", None)
    return f"Failed to reach Alpaca {service} ({alpaca_transport_failure_label(exc)}): {reason}"
