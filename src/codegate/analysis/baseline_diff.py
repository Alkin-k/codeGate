"""Deterministic Baseline Diff — structural pre-check for drift detection.

Design principle: facts are decided by CODE, not by LLM.

This module compares baseline_content (git HEAD) against files_content (current)
to produce a structured diff of what was REMOVED, ADDED, or MODIFIED.

The reviewer LLM receives this structured diff as ground truth input,
rather than being asked to independently diff two code blocks.

Post-filter: any reviewer finding claiming "X was removed" is automatically
suppressed if X does not appear in `removed_from_baseline`.
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class PatternMatch:
    """A single code pattern identified in a source file."""
    file: str
    pattern: str
    kind: str  # "annotation", "exception_handler", "method_signature", "import"
    line_number: int = 0
    context: str = ""  # surrounding line for human readability

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class BaselineDiffResult:
    """The output of deterministic baseline comparison.

    This is injected into the reviewer prompt as GROUND TRUTH.
    The reviewer may add interpretive findings, but cannot contradict
    the facts recorded here.
    """
    removed_from_baseline: List[PatternMatch] = field(default_factory=list)
    added_not_in_baseline: List[PatternMatch] = field(default_factory=list)
    unchanged_baseline: List[PatternMatch] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "removed_from_baseline": [p.to_dict() for p in self.removed_from_baseline],
            "added_not_in_baseline": [p.to_dict() for p in self.added_not_in_baseline],
            "unchanged_baseline": [p.to_dict() for p in self.unchanged_baseline],
        }

    def summary_text(self) -> str:
        """Human-readable summary for injection into reviewer prompt."""
        lines = []

        if self.removed_from_baseline:
            lines.append("🔴 REMOVED FROM BASELINE (these were in the original code and are now gone):")
            for p in self.removed_from_baseline:
                lines.append(f"  - [{p.kind}] {p.pattern} in {p.file}:{p.line_number}")
                if p.context:
                    lines.append(f"    Context: {p.context.strip()}")
        else:
            lines.append("🔴 REMOVED FROM BASELINE: (none)")

        if self.added_not_in_baseline:
            lines.append("\n🟢 ADDED (not in baseline — new code from executor):")
            for p in self.added_not_in_baseline:
                lines.append(f"  - [{p.kind}] {p.pattern} in {p.file}:{p.line_number}")
        else:
            lines.append("\n🟢 ADDED: (none)")

        if self.unchanged_baseline:
            lines.append("\n⚪ PRESERVED FROM BASELINE (still present, no change):")
            for p in self.unchanged_baseline:
                lines.append(f"  - [{p.kind}] {p.pattern} in {p.file}:{p.line_number}")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Pattern extractors (language-aware, regex-based)
# ---------------------------------------------------------------------------

# Java annotation patterns: @Name or @Name(args)
_JAVA_ANNOTATION_RE = re.compile(
    r"@(Min|Max|NotNull|NotBlank|NotEmpty|Valid|Validated|Size|Pattern|Email|"
    r"Positive|PositiveOrZero|Negative|NegativeOrZero|DecimalMin|DecimalMax|"
    r"Digits|Past|Future|AssertTrue|AssertFalse|RequestParam|PathVariable|"
    r"RequestBody|RequestHeader)"
    r"(\([^)]*\))?",
    re.MULTILINE,
)

# Java @ExceptionHandler(SomeException.class)
_JAVA_EXCEPTION_HANDLER_RE = re.compile(
    r"@ExceptionHandler\s*\(\s*([A-Za-z0-9_.]+)\.class\s*\)",
    re.MULTILINE,
)

# Java method signatures (simplified, catches most public/protected/private methods)
_JAVA_METHOD_SIG_RE = re.compile(
    r"^\s*(public|protected|private)\s+"           # visibility
    r"(?:static\s+)?(?:final\s+)?"                 # optional modifiers
    r"([\w<>\[\],\s?]+?)\s+"                       # return type
    r"(\w+)\s*\(",                                 # method name
    re.MULTILINE,
)

# Python decorator patterns
_PYTHON_DECORATOR_RE = re.compile(
    r"^(\s*@[\w.]+(?:\([^)]*\))?)",
    re.MULTILINE,
)


def _extract_patterns(filepath: str, content: str) -> List[PatternMatch]:
    """Extract trackable patterns from a single source file.

    Returns patterns for: annotations, exception handlers, method signatures.
    """
    patterns: List[PatternMatch] = []
    lines = content.split("\n")

    # Detect language by extension
    ext = filepath.rsplit(".", 1)[-1].lower() if "." in filepath else ""

    if ext == "java":
        patterns.extend(_extract_java_patterns(filepath, content, lines))
    elif ext == "py":
        patterns.extend(_extract_python_patterns(filepath, content, lines))
    else:
        # Generic: try both
        patterns.extend(_extract_java_patterns(filepath, content, lines))
        patterns.extend(_extract_python_patterns(filepath, content, lines))

    return patterns


def _extract_java_patterns(
    filepath: str, content: str, lines: List[str]
) -> List[PatternMatch]:
    """Extract Java-specific patterns."""
    patterns: List[PatternMatch] = []

    # 1. Validation annotations
    for m in _JAVA_ANNOTATION_RE.finditer(content):
        line_num = content[:m.start()].count("\n") + 1
        full_match = m.group(0)
        context_line = lines[line_num - 1] if line_num <= len(lines) else ""
        patterns.append(PatternMatch(
            file=filepath,
            pattern=full_match,
            kind="annotation",
            line_number=line_num,
            context=context_line,
        ))

    # 2. Exception handlers
    for m in _JAVA_EXCEPTION_HANDLER_RE.finditer(content):
        line_num = content[:m.start()].count("\n") + 1
        exception_class = m.group(1)
        context_line = lines[line_num - 1] if line_num <= len(lines) else ""
        patterns.append(PatternMatch(
            file=filepath,
            pattern=f"@ExceptionHandler({exception_class}.class)",
            kind="exception_handler",
            line_number=line_num,
            context=context_line,
        ))

    # 3. Method signatures (only public/protected API)
    for m in _JAVA_METHOD_SIG_RE.finditer(content):
        line_num = content[:m.start()].count("\n") + 1
        visibility = m.group(1)
        return_type = m.group(2).strip()
        method_name = m.group(3)
        sig = f"{visibility} {return_type} {method_name}(...)"
        context_line = lines[line_num - 1] if line_num <= len(lines) else ""
        patterns.append(PatternMatch(
            file=filepath,
            pattern=sig,
            kind="method_signature",
            line_number=line_num,
            context=context_line,
        ))

    return patterns


def _extract_python_patterns(
    filepath: str, content: str, lines: List[str]
) -> List[PatternMatch]:
    """Extract Python-specific patterns."""
    patterns: List[PatternMatch] = []

    for m in _PYTHON_DECORATOR_RE.finditer(content):
        line_num = content[:m.start()].count("\n") + 1
        decorator = m.group(1).strip()
        patterns.append(PatternMatch(
            file=filepath,
            pattern=decorator,
            kind="decorator",
            line_number=line_num,
            context=decorator,
        ))

    return patterns


# ---------------------------------------------------------------------------
# Core diff computation
# ---------------------------------------------------------------------------


def compute_baseline_diff(
    baseline_content: Dict[str, str],
    files_content: Dict[str, str],
) -> BaselineDiffResult:
    """Compare baseline (git HEAD) against current implementation.

    For each file that appears in both baseline_content and files_content:
    1. Extract patterns from both versions
    2. Compute which patterns were REMOVED, ADDED, or PRESERVED

    The comparison key is (pattern, kind) — line numbers are expected to change.
    """
    result = BaselineDiffResult()

    # Only compare files that exist in BOTH baseline and current
    common_files = set(baseline_content.keys()) & set(files_content.keys())

    for filepath in sorted(common_files):
        baseline_patterns = _extract_patterns(filepath, baseline_content[filepath])
        current_patterns = _extract_patterns(filepath, files_content[filepath])

        # Build sets keyed by (pattern, kind) for comparison
        baseline_set = {(p.pattern, p.kind) for p in baseline_patterns}
        current_set = {(p.pattern, p.kind) for p in current_patterns}

        # REMOVED: in baseline but not in current
        removed_keys = baseline_set - current_set
        for p in baseline_patterns:
            if (p.pattern, p.kind) in removed_keys:
                result.removed_from_baseline.append(p)

        # ADDED: in current but not in baseline
        added_keys = current_set - baseline_set
        for p in current_patterns:
            if (p.pattern, p.kind) in added_keys:
                result.added_not_in_baseline.append(p)

        # PRESERVED: in both
        preserved_keys = baseline_set & current_set
        for p in baseline_patterns:
            if (p.pattern, p.kind) in preserved_keys:
                result.unchanged_baseline.append(p)

    logger.info(
        f"Baseline diff: {len(result.removed_from_baseline)} removed, "
        f"{len(result.added_not_in_baseline)} added, "
        f"{len(result.unchanged_baseline)} preserved"
    )

    return result


# ---------------------------------------------------------------------------
# Post-filter: suppress false positive findings
# ---------------------------------------------------------------------------


def post_filter_findings(
    findings: list,
    diff_result: BaselineDiffResult,
    baseline_content: Optional[Dict[str, str]] = None,
) -> tuple[list, list]:
    """Filter reviewer findings using deterministic baseline diff.

    Three-layer verification for drift findings claiming "X was removed":

    Layer 1: Does X appear in `removed_from_baseline`? → KEEP (true positive)
    Layer 2: Does X appear in `added_not_in_baseline`? → SUPPRESS (executor-added)
    Layer 3: Does X appear ANYWHERE in raw baseline_content? → KEEP if yes,
             SUPPRESS if no (ghost pattern from intermediate iteration)

    Returns:
        (kept_findings, suppressed_findings) — suppressed findings are logged
        but not passed to the gatekeeper.
    """
    # Build lookup structures
    actually_removed = {p.pattern.lower() for p in diff_result.removed_from_baseline}
    only_added = {p.pattern.lower() for p in diff_result.added_not_in_baseline}

    # Build raw baseline text for Layer 3 verification
    baseline_text_lower = ""
    if baseline_content:
        baseline_text_lower = "\n".join(baseline_content.values()).lower()

    kept = []
    suppressed = []

    for finding in findings:
        message = getattr(finding, "message", "") or ""
        message_lower = message.lower()

        # Only apply filter to "drift" findings about removal
        if getattr(finding, "category", "") != "drift":
            kept.append(finding)
            continue

        # Check if the finding is about removing something
        removal_keywords = ["removed", "deleted", "dropped", "no longer", "missing"]
        is_removal_claim = any(kw in message_lower for kw in removal_keywords)

        if not is_removal_claim:
            kept.append(finding)
            continue

        # --- Layer 1: Does it reference a pattern actually removed from baseline? ---
        references_baseline_pattern = False
        for removed_pattern in actually_removed:
            if removed_pattern in message_lower:
                references_baseline_pattern = True
                break

        if references_baseline_pattern:
            # Finding correctly identifies something that was actually in baseline
            kept.append(finding)
            continue

        # --- Layer 2: Does it reference a pattern only added by executor? ---
        references_executor_added = False
        for added_pattern in only_added:
            # Match the class/annotation name in the finding message
            # E.g., "HandlerMethodValidationException" from "@ExceptionHandler(HandlerMethodValidationException.class)"
            core_name = added_pattern
            if "(" in core_name:
                inner = core_name.split("(", 1)[1].rstrip(")")
                inner = inner.replace(".class", "").strip()
                if inner.lower() in message_lower:
                    references_executor_added = True
                    break
            if core_name in message_lower:
                references_executor_added = True
                break

        if references_executor_added:
            logger.info(
                f"[POST-FILTER] Suppressed (executor-added pattern): "
                f"'{message[:80]}...'"
            )
            suppressed.append(finding)
            continue

        # --- Layer 3: Raw baseline text search (catches ghost patterns) ---
        # Extract the PRIMARY subject of the "removed X" claim.
        # The subject is the specific thing being claimed as removed,
        # NOT incidental identifiers like file names.
        primary_subject = _extract_removal_subject(message)

        if primary_subject and baseline_text_lower:
            subject_in_baseline = primary_subject.lower() in baseline_text_lower

            if not subject_in_baseline:
                # Ghost pattern: the claimed subject never existed in baseline
                logger.info(
                    f"[POST-FILTER] Suppressed (ghost pattern — not in baseline): "
                    f"'{message[:80]}...' "
                    f"Subject '{primary_subject}' not found in any baseline file"
                )
                suppressed.append(finding)
                continue

        # Can't determine — keep it (conservative)
        kept.append(finding)

    if suppressed:
        logger.info(
            f"[POST-FILTER] {len(suppressed)} findings suppressed, "
            f"{len(kept)} kept"
        )

    return kept, suppressed


def _extract_removal_subject(message: str) -> Optional[str]:
    """Extract the PRIMARY subject of a "removed X" claim.

    Looks for the main identifier immediately following removal keywords.
    Returns the most likely subject — a class name, annotation, or type name.

    Examples:
        "Removed HandlerMethodValidationException handler from GlobalExceptionHandler"
        → "HandlerMethodValidationException"

        "Removed @Min(72) annotation from dpi parameter"
        → "@Min(72)"  (but this would match in Layer 1 already)

        "Deleted the cache invalidation logic"
        → "cache" (less precise, but conservative)
    """
    # Pattern 1: "Removed/Deleted/Dropped <CamelCase> ..."
    # Captures the first CamelCase word after a removal keyword
    m = re.search(
        r"(?:removed|deleted|dropped|missing)\s+"
        r"(@?\w+(?:\([^)]*\))?)",  # capture the subject (with optional @annotation)
        message,
        re.IGNORECASE,
    )
    if m:
        subject = m.group(1)
        # If subject is a common word, skip
        common = {"the", "a", "an", "existing", "all", "some", "this", "these", "original"}
        if subject.lower() in common:
            # Try the next word
            rest = message[m.end():].strip()
            m2 = re.match(r"(@?\w+(?:\([^)]*\))?)", rest)
            if m2:
                subject = m2.group(1)
        return subject

    return None


def _extract_identifiers_from_message(message: str) -> List[str]:
    """Extract likely class/annotation/method names from a finding message.

    Heuristic: look for CamelCase words, @Annotations, and qualified names
    that are likely to be the subject of a "removed X" claim.

    Used as fallback when _extract_removal_subject returns None.
    """
    identifiers = []

    # CamelCase identifiers (e.g., HandlerMethodValidationException)
    camel_case = re.findall(r"\b([A-Z][a-zA-Z]+(?:[A-Z][a-zA-Z]+)+)\b", message)
    identifiers.extend(camel_case)

    # @Annotation patterns (e.g., @Min, @ExceptionHandler)
    annotations = re.findall(r"@(\w+)(?:\([^)]*\))?", message)
    identifiers.extend(annotations)

    # Qualified names (e.g., com.example.SomeClass)
    qualified = re.findall(r"\b(\w+(?:\.\w+){2,})\b", message)
    identifiers.extend(qualified)

    # Deduplicate while preserving order, filter out common words
    seen = set()
    result = []
    common_words = {"the", "from", "was", "not", "and", "for", "this", "that",
                    "with", "has", "are", "been", "were", "which", "existing",
                    "removed", "handler", "annotation", "parameter", "method"}
    for ident in identifiers:
        lower = ident.lower()
        if lower not in seen and lower not in common_words and len(ident) > 3:
            seen.add(lower)
            result.append(ident)

    return result


