"""
RSI Bridge — Integration with state-canon-mcp

Provides functions to:
- Query canonical state for RSI-relevant data
- Feed RSI metrics back into the state canon
- Query rules that constrain RSI behavior

DEPENDS ON: state-canon-mcp (running as MCP server)

MCP Integration:
- Uses state-canon-mcp tools when available (via opencode)
- Falls back to local state when MCP is not available
"""

from typing import Any, Dict, Optional
from pathlib import Path
import json
import logging

logger = logging.getLogger("vsf_rsi.bridge")

# Local state directory for fallback
LOCAL_STATE_DIR = Path(__file__).parent.parent / "state"
LOCAL_STATE_DIR.mkdir(parents=True, exist_ok=True)


def query_canon(domain: str, filter: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Query canonical state through state-canon-mcp.
    
    Args:
        domain: Data domain (e.g., 'services', 'tasks', 'rules')
        filter: Optional filter criteria
    
    Returns:
        Query results from state canon
    """
    try:
        # Try to use MCP tools if available
        # In opencode environment, these are available as MCP tools
        # In standalone mode, fall back to local state
        from state_canon_mcp import state_query
        result = state_query(domain=domain, filter=filter or {})
        logger.info(f"MCP query successful: domain={domain}")
        return result
    except ImportError:
        # MCP not available, use local state
        logger.debug("MCP not available, using local state")
        return _query_local(domain, filter)
    except Exception as e:
        logger.warning(f"MCP query failed: {e}, using local state")
        return _query_local(domain, filter)


def _query_local(domain: str, filter: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Fallback: query local state files."""
    state_file = LOCAL_STATE_DIR / f"{domain}.json"
    if state_file.exists():
        try:
            with open(state_file) as f:
                data = json.load(f)
            if filter:
                # Simple filter: check if filter keys match
                data = [r for r in (data if isinstance(data, list) else [data])
                        if all(r.get(k) == v for k, v in filter.items())]
            return {"domain": domain, "data": data, "source": "local"}
        except Exception as e:
            logger.error(f"Local query failed: {e}")
    return {"domain": domain, "data": [], "source": "local", "status": "not_found"}


def get_rsi_rules() -> Dict[str, Any]:
    """
    Get rules that constrain RSI behavior from state canon.
    
    Returns:
        Dictionary of active rules affecting RSI
    """
    try:
        result = query_canon("rules", {"domain": "rsi"})
        if result.get("data"):
            return result["data"]
    except Exception as e:
        logger.debug(f"Could not query rules from canon: {e}")
    
    # Fallback: hardcoded rules from VSM spec
    return {
        "A0": "Purpose inalienable — RSI must serve system purpose",
        "A5": "Autonomy ceiling — RSI cannot exceed L2 without approval",
        "D4-L2": "parameter_drift: autonomous, capability_extension: audited",
        "D4-L3": "axiom changes: always human",
        "R17": "Destructive actions require explicit consent",
        "R16": "Implementation with design",
    }


def get_rsi_focus() -> Dict[str, Any]:
    """
    Get current RSI focus state from state canon.
    
    Returns:
        Current focus entries related to RSI
    """
    try:
        from state_canon_mcp import state_journal_history
        history = state_journal_history(limit=10)
        return {"entries": history, "source": "state-canon-mcp"}
    except ImportError:
        logger.debug("MCP not available, using local focus")
    except Exception as e:
        logger.debug(f"MCP focus query failed: {e}")
    
    # Fallback: local focus file
    focus_file = LOCAL_STATE_DIR / "rsi_focus.json"
    if focus_file.exists():
        try:
            with open(focus_file) as f:
                return json.load(f)
        except Exception:
            pass
    return {"entries": [], "source": "local"}


def feed_metrics_to_canon(metrics: Dict[str, Any]) -> Dict[str, Any]:
    """
    Feed RSI metrics back into state canon for tracking.
    
    Args:
        metrics: RSI metrics to record
    
    Returns:
        Confirmation of recording
    """
    logger.info(f"Feeding metrics to canon: {list(metrics.keys())}")
    
    # Save locally
    metrics_file = LOCAL_STATE_DIR / "rsi_metrics_history.json"
    history = []
    if metrics_file.exists():
        try:
            with open(metrics_file) as f:
                history = json.load(f)
        except Exception:
            pass
    
    history.append(metrics)
    
    # Keep last 100 entries
    if len(history) > 100:
        history = history[-100:]
    
    try:
        with open(metrics_file, "w") as f:
            json.dump(history, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save metrics locally: {e}")
    
    # Try to feed to MCP
    try:
        from state_canon_mcp import state_focus_mark
        state_focus_mark(
            ref=f"rsi_metrics_{len(history)}",
            status="active",
            note=f"RSI metrics update: {list(metrics.keys())}"
        )
        logger.info("Metrics fed to MCP successfully")
        return {"status": "recorded", "source": "state-canon-mcp", "entry_count": len(history)}
    except ImportError:
        logger.debug("MCP not available, metrics saved locally only")
    except Exception as e:
        logger.warning(f"MCP feed failed: {e}, metrics saved locally")
    
    return {"status": "recorded", "source": "local", "entry_count": len(history)}


def get_metrics_history(limit: int = 10) -> list:
    """
    Get recent metrics history.
    
    Args:
        limit: Maximum entries to return
    
    Returns:
        List of metric entries
    """
    metrics_file = LOCAL_STATE_DIR / "rsi_metrics_history.json"
    if metrics_file.exists():
        try:
            with open(metrics_file) as f:
                history = json.load(f)
            return history[-limit:]
        except Exception:
            pass
    return []
