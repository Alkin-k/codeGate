"""Rust structural pattern extractor.

Extracts security-relevant and interface-relevant patterns from
Rust (.rs) files, with focus on Tauri IPC commands.

Extraction targets:
  - #[tauri::command] attributes
  - Function signatures (name, parameters, return type)
  - SQL pagination patterns (LIMIT, OFFSET, page, size)

Design boundary: this module produces FACTS, not judgments.
"keyword/limit was replaced by page/size" is a POLICY decision
computed from the diff between baseline and current patterns.
"""

from __future__ import annotations

import re
from typing import List

from codegate.analysis.baseline_diff import PatternMatch


# ---------------------------------------------------------------------------
# Pattern regexes
# ---------------------------------------------------------------------------

# Tauri command attribute
_TAURI_COMMAND_RE = re.compile(
    r"#\[tauri::command(?:\([^)]*\))?\]",
    re.MULTILINE,
)

# Rust function signatures — captures visibility, async, name, params, return type
_RUST_FN_SIG_RE = re.compile(
    r"(?:pub(?:\s*\(crate\))?\s+)?(?:async\s+)?fn\s+"
    r"(\w+)\s*"                          # function name
    r"(?:<[^>]*>\s*)?"                   # optional generic params
    r"\(([^)]*)\)"                       # parameters
    r"(?:\s*->\s*([^{;]+?))?"            # optional return type
    r"\s*[{;]",                          # body start or semicolon
    re.MULTILINE | re.DOTALL,
)

# SQL pagination keywords in string literals
_SQL_PAGINATION_RE = re.compile(
    r"(?:LIMIT|OFFSET|page_size|per_page)\b",
    re.IGNORECASE,
)

# Rust string literals (for SQL detection)
_RUST_STRING_RE = re.compile(
    r'(?:r#?"[^"]*"#?|"(?:[^"\\]|\\.)*")',
    re.DOTALL,
)

# Rust use/import statements
_RUST_USE_RE = re.compile(
    r"^use\s+([\w:]+(?:::\{[^}]*\})?)\s*;",
    re.MULTILINE,
)

# Rust attribute (generic, for detecting other relevant attributes)
_RUST_ATTRIBUTE_RE = re.compile(
    r"#\[(\w+(?:::\w+)*(?:\([^)]*\))?)\]",
    re.MULTILINE,
)


# ---------------------------------------------------------------------------
# Main extractor
# ---------------------------------------------------------------------------

def extract_rust_patterns(filepath: str, content: str) -> List[PatternMatch]:
    """Extract trackable patterns from a Rust source file.

    Returns PatternMatch objects with kinds:
      - "tauri_command": #[tauri::command] attribute
      - "function_signature": fn name(params) -> ReturnType
      - "sql_pagination": LIMIT/OFFSET/page_size in SQL strings
      - "import": use declarations
    """
    lines = content.split("\n")
    patterns: List[PatternMatch] = []

    # --- 1. Tauri command attributes ---
    tauri_command_lines: set[int] = set()
    for m in _TAURI_COMMAND_RE.finditer(content):
        line_num = _line_number(content, m.start())
        tauri_command_lines.add(line_num)
        patterns.append(PatternMatch(
            file=filepath,
            pattern=m.group(0),
            kind="tauri_command",
            line_number=line_num,
            context=_context_line(lines, line_num),
        ))

    # --- 2. Function signatures ---
    for m in _RUST_FN_SIG_RE.finditer(content):
        fn_name = m.group(1)
        params_raw = m.group(2).strip()
        return_type = (m.group(3) or "").strip()
        line_num = _line_number(content, m.start())

        # Parse individual parameters
        params = _parse_params(params_raw)
        params_str = ", ".join(params) if params else ""

        sig = f"fn {fn_name}({params_str})"
        if return_type:
            sig += f" -> {return_type}"

        # Check if this function is a tauri command (attribute on previous line)
        is_tauri = any(
            tl in range(max(1, line_num - 3), line_num + 1)
            for tl in tauri_command_lines
        )

        patterns.append(PatternMatch(
            file=filepath,
            pattern=sig,
            kind="function_signature",
            line_number=line_num,
            context=_context_line(lines, line_num),
        ))

    # --- 3. SQL pagination patterns in string literals ---
    for sm in _RUST_STRING_RE.finditer(content):
        string_content = sm.group(0)
        for pm in _SQL_PAGINATION_RE.finditer(string_content):
            line_num = _line_number(content, sm.start())
            keyword = pm.group(0)
            patterns.append(PatternMatch(
                file=filepath,
                pattern=f"SQL:{keyword}",
                kind="sql_pagination",
                line_number=line_num,
                context=_context_line(lines, line_num),
            ))

    # --- 4. Use (import) statements ---
    for m in _RUST_USE_RE.finditer(content):
        line_num = _line_number(content, m.start())
        use_path = m.group(1).strip()
        patterns.append(PatternMatch(
            file=filepath,
            pattern=f"use {use_path}",
            kind="import",
            line_number=line_num,
            context=_context_line(lines, line_num),
        ))

    return _deduplicate(patterns)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_params(params_raw: str) -> List[str]:
    """Parse Rust function parameters into name: Type pairs.

    Handles multi-line params, skips &self/&mut self.
    """
    if not params_raw.strip():
        return []

    params = []
    for part in params_raw.split(","):
        part = part.strip()
        if not part or part in ("&self", "&mut self", "self"):
            continue
        # Clean up multiline whitespace
        part = re.sub(r"\s+", " ", part)
        params.append(part)

    return params


def _line_number(content: str, char_offset: int) -> int:
    """Convert character offset to 1-based line number."""
    return content[:char_offset].count("\n") + 1


def _context_line(lines: List[str], line_num: int) -> str:
    """Get the line at 1-based line_num, or empty string."""
    if 1 <= line_num <= len(lines):
        return lines[line_num - 1].strip()
    return ""


def _deduplicate(patterns: List[PatternMatch]) -> List[PatternMatch]:
    """Remove duplicate patterns (same pattern text + kind)."""
    seen: set[tuple[str, str]] = set()
    result: List[PatternMatch] = []
    for p in patterns:
        key = (p.pattern.strip(), p.kind)
        if key not in seen:
            seen.add(key)
            result.append(p)
    return result
