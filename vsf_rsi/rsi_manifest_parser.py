"""rsi_manifest_parser — parse VSM manifest files for RSI.

design: child/docs/vos_package_detailed_plans.vsm
Parses the VSM manifest format used by rsi_generated_trees.vsm,
rsi_generated_predicates.vsm, rsi_forests.vsm, and rsi_component_registry.json.

VSM 1.2 Format:
  ⟦ name | MANIFEST-v1 | vsm-1.2 | YYYY-MM-DDTHH:MM:SSZ ⟧
  @vsm 1.2
  @status active
  // comments
  entries = [
    { key: "value", key: "value" },
    ...
  ]
  ⟦ /name | MANIFEST-v1 | vsm-1.2 ⟧

Usage:
    from rsi_manifest_parser import load_manifest, save_manifest
    manifest = load_manifest(Path("rsi_generated_trees.vsm"))
    # manifest = {"trees": [{"name": "...", "path": "...", ...}, ...]}

VSM 1.2 Compliance:
  - Header: ⟦ name | TYPE-v1 | vsm-1.2 | YYYY-MM-DDTHH:MM:SSZ ⟧
  - Footer: ⟦ /name | TYPE-v1 | vsm-1.2 ⟧
  - Timestamps: ISO 8601 UTC with Z suffix (no microseconds, no +00:00)
  - Deduplication: entries deduplicated by (name, path) before save
"""

import re
from pathlib import Path
from typing import Dict, List, Any, Optional


def _parse_entry(line: str) -> Dict[str, str]:
    """Parse a single VSM dict entry line: { key: "value", key: "value" }"""
    entry = {}
    # Match key: "value" or key: number patterns
    for match in re.finditer(r'(\w+):\s*"([^"]*)"', line):
        entry[match.group(1)] = match.group(2)
    for match in re.finditer(r'(\w+):\s*(\d+)', line):
        entry[match.group(1)] = int(match.group(2))
    return entry


def _extract_list_entries(content: str, list_name: str) -> List[Dict[str, str]]:
    """Extract entries from a VSM list: list_name = [ ... ]"""
    # Find the list block
    pattern = rf'{list_name}\s*=\s*\[(.*?)\]'
    match = re.search(pattern, content, re.DOTALL)
    if not match:
        return []

    block = match.group(1)
    entries = []

    for line in block.split('\n'):
        line = line.strip()
        if line.startswith('{') and '}' in line:
            # Extract the dict portion
            dict_match = re.search(r'\{(.*?)\}', line)
            if dict_match:
                entry = _parse_entry(dict_match.group(1))
                if entry:
                    entries.append(entry)

    return entries


def load_manifest(path: Path) -> Dict[str, List[Dict[str, str]]]:
    """Load a VSM manifest file and return its entries.

    Returns a dict where the key is the list name (e.g., "trees", "predicates",
    "forests") and the value is a list of dicts.
    """
    if not path.exists():
        return {}

    content = path.read_text(encoding='utf-8')

    # Find the list name (the first identifier before = [)
    list_match = re.search(r'(\w+)\s*=\s*\[', content)
    if not list_match:
        return {}

    list_name = list_match.group(1)
    entries = _extract_list_entries(content, list_name)

    return {list_name: entries}


def _format_timestamp(ts: Any) -> str:
    """Format a timestamp to VSM 1.2 standard: YYYY-MM-DDTHH:MM:SSZ.

    Accepts:
      - datetime object
      - ISO string with microseconds (+00:00 format)
      - ISO string with Z suffix
      - Date-only string (YYYY-MM-DD)
    Returns clean UTC timestamp: 2026-08-31T17:47:05Z
    """
    if ts is None:
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # If it's a datetime object
    if hasattr(ts, 'strftime'):
        return ts.strftime("%Y-%m-%dT%H:%M:%SZ")

    ts_str = str(ts).strip()

    # Already in correct format
    if re.match(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$', ts_str):
        return ts_str

    # ISO format with microseconds and +00:00 — strip microseconds and replace +00:00 with Z
    match = re.match(r'^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})\.\d+\+00:00$', ts_str)
    if match:
        return match.group(1) + "Z"

    # ISO format with +00:00 — replace with Z
    match = re.match(r'^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})\+00:00$', ts_str)
    if match:
        return match.group(1) + "Z"

    # Date only — add midnight
    match = re.match(r'^(\d{4}-\d{2}-\d{2})$', ts_str)
    if match:
        return match.group(1) + "T00:00:00Z"

    # Fallback — return as-is (will be validated later)
    return ts_str


def _dedup_key(entry: Dict[str, str]) -> tuple:
    """Generate a deduplication key from an entry.

    Uses (name,) as the uniqueness criterion — paths change across runs
    (different /tmp/ directories), so path-based dedup doesn't work.
    """
    name = entry.get("name", entry.get("predicate", ""))
    return (name,)


def save_manifest(path: Path, list_name: str, entries: List[Dict[str, str]],
                  header_name: str, timestamp: str,
                  expression_type: str = "MANIFEST-v1",
                  vsm_version: str = "1.2.1",
                  status: str = "active",
                  deduplicate: bool = True) -> None:
    """Save entries to a VSM 1.2.1 compliant manifest file.

    Args:
        path: Path to the manifest file
        list_name: Name of the list (e.g., "trees", "predicates", "forests")
        entries: List of dicts to serialize
        header_name: Name for the VSM header/footer
        timestamp: UTC timestamp for the header (will be normalized to Z format)
        expression_type: VSM expression type (default: MANIFEST-v1)
        vsm_version: VSM version (default: 1.2.1, per vsl_language_primer)
        status: Document status (default: active)
        deduplicate: Whether to deduplicate entries (default: True)
    """
    # Normalize timestamp to VSM 1.2.1 format
    header_ts = _format_timestamp(timestamp)

    # Deduplicate entries if requested
    if deduplicate:
        seen = set()
        deduped = []
        for entry in entries:
            key = _dedup_key(entry)
            if key not in seen:
                seen.add(key)
                deduped.append(entry)
        entries = deduped

    # Build content
    content = f"⟦ {header_name} | {expression_type} | vsm-{vsm_version} | {header_ts} ⟧\n\n"
    content += f"@vsm {vsm_version}\n"
    content += f"@status {status}\n\n"
    content += f"// Auto-generated {list_name} manifest\n"
    content += f"// Generated by RSI\n\n"
    content += f"{list_name} = [\n"

    for entry in entries:
        parts = []
        for key, value in entry.items():
            if isinstance(value, int):
                parts.append(f"{key}: {value}")
            else:
                # Normalize timestamps in values
                normalized = _format_timestamp(value)
                parts.append(f'{key}: "{normalized}"')
        content += "  { " + ", ".join(parts) + " },\n"

    content += "]\n\n"
    # Footer: NAME-ONLY per vsl_language_primer.vsm §file_grammar (vsm-1.2.1)
    content += f"⟦ /{header_name} ⟧\n"

    path.write_text(content, encoding='utf-8')
