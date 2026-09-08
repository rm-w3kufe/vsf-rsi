"""
vsm_utils.py — VSM metadata generation utilities.

Copied from vos_kernel.utils.vsm_kernel to avoid hard dependency on vos-kernel.
These are the minimal functions needed for VSM document generation.

For the full VSM kernel, install: pip install vos-kernel
"""

from datetime import datetime, timezone
from typing import Optional

# ============================================================
# VSM Protocol Version (single source of truth)
# ============================================================
VSM_VERSION = "1.2.1"
VSM_VERSION_STR = f"vsm-{VSM_VERSION}"


def get_version() -> str:
    """Get the current VSM protocol version.
    
    Returns:
        Version string like "1.2.1"
    """
    return VSM_VERSION


def get_version_str() -> str:
    """Get the current VSM protocol version with prefix.
    
    Returns:
        Version string like "vsm-1.2.1"
    """
    return VSM_VERSION_STR


def get_timestamp() -> str:
    """Generate a VSM-compliant timestamp.
    
    Returns:
        ISO 8601 UTC timestamp like "2026-09-07T19:00:00Z"
    
    Security: This is the ONLY way to generate timestamps.
    Agents must NEVER hardcode timestamps.
    """
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def vsm_header(name: str, doc_type: str, timestamp: Optional[str] = None) -> str:
    """Generate a VSM-compliant header.
    
    Args:
        name: Document name (e.g., "my_document")
        doc_type: Document type (e.g., "DOCUMENTATION-v1", "PLAN-v1")
        timestamp: Optional timestamp (if None, generates current time)
        
    Returns:
        Header string like "⟦ my_document | DOCUMENTATION-v1 | vsm-1.2.1 | 2026-09-07T19:00:00Z ⟧"
    
    Security: Agents must NEVER build headers manually.
    """
    if timestamp is None:
        timestamp = get_timestamp()
    
    return f"⟦ {name} | {doc_type} | {VSM_VERSION_STR} | {timestamp} ⟧"


def vsm_footer_with_type(name: str, doc_type: str, timestamp: Optional[str] = None) -> str:
    """Generate a VSM-compliant footer with document type (DEPRECATED).
    
    DEPRECATED: Use vsm_footer() instead. This function is kept for backward
    compatibility only. The standard footer format is SHORT: ⟦ /name ⟧
    
    Args:
        name: Document name (must match header name)
        doc_type: Document type (ignored, kept for API compatibility)
        timestamp: Optional timestamp (ignored, kept for API compatibility)
        
    Returns:
        Footer string like "⟦ /my_document ⟧"
    """
    return f"⟦ /{name} ⟧"
