"""Rust structural extractor tests.

Validates that the Rust extractor correctly identifies:
  - #[tauri::command] attributes
  - Function signatures (name, parameters, return type)
  - Parameter additions (T3: offset added)
  - Parameter replacements (T4: keyword/limit → page/size)
  - SQL pagination patterns (LIMIT, OFFSET)
  - Use declarations
"""

from __future__ import annotations

import pytest

from codegate.analysis.structural_extractors.rust import extract_rust_patterns


# ---------------------------------------------------------------------------
# Fixtures: realistic Rust code snippets
# ---------------------------------------------------------------------------

RUST_T3_BASELINE = '''
use tauri::command;
use rusqlite::Connection;

#[tauri::command]
pub async fn local_db_search(keyword: String, limit: i32) -> Result<Vec<Record>, String> {
    let conn = Connection::open("app.db").map_err(|e| e.to_string())?;
    let mut stmt = conn.prepare(
        "SELECT * FROM records WHERE title LIKE ?1 LIMIT ?2"
    ).map_err(|e| e.to_string())?;

    let results = stmt.query_map(
        rusqlite::params![format!("%{}%", keyword), limit],
        |row| Ok(Record::from_row(row)),
    ).map_err(|e| e.to_string())?;

    results.collect::<Result<Vec<_>, _>>().map_err(|e| e.to_string())
}

#[tauri::command]
pub fn get_config() -> AppConfig {
    AppConfig::default()
}
'''

RUST_T3_OFFSET_ADDED = '''
use tauri::command;
use rusqlite::Connection;

#[tauri::command]
pub async fn local_db_search(keyword: String, limit: i32, offset: i32) -> Result<Vec<Record>, String> {
    let conn = Connection::open("app.db").map_err(|e| e.to_string())?;
    let mut stmt = conn.prepare(
        "SELECT * FROM records WHERE title LIKE ?1 LIMIT ?2 OFFSET ?3"
    ).map_err(|e| e.to_string())?;

    let results = stmt.query_map(
        rusqlite::params![format!("%{}%", keyword), limit, offset],
        |row| Ok(Record::from_row(row)),
    ).map_err(|e| e.to_string())?;

    results.collect::<Result<Vec<_>, _>>().map_err(|e| e.to_string())
}

#[tauri::command]
pub fn get_config() -> AppConfig {
    AppConfig::default()
}
'''

RUST_T4_PAGE_SIZE = '''
use tauri::command;
use rusqlite::Connection;

#[tauri::command]
pub async fn local_db_search(page: i32, size: i32) -> Result<Vec<Record>, String> {
    let conn = Connection::open("app.db").map_err(|e| e.to_string())?;
    let offset = (page - 1) * size;
    let mut stmt = conn.prepare(
        "SELECT * FROM records LIMIT ?1 OFFSET ?2"
    ).map_err(|e| e.to_string())?;

    let results = stmt.query_map(
        rusqlite::params![size, offset],
        |row| Ok(Record::from_row(row)),
    ).map_err(|e| e.to_string())?;

    results.collect::<Result<Vec<_>, _>>().map_err(|e| e.to_string())
}

#[tauri::command]
pub fn get_config() -> AppConfig {
    AppConfig::default()
}
'''


# ---------------------------------------------------------------------------
# Tests: Pattern extraction
# ---------------------------------------------------------------------------


class TestTauriCommandExtraction:
    """Test #[tauri::command] attribute detection."""

    def test_extracts_tauri_commands(self) -> None:
        patterns = extract_rust_patterns("src-tauri/src/commands.rs", RUST_T3_BASELINE)
        tauri = [p for p in patterns if p.kind == "tauri_command"]
        # Deduplication merges identical #[tauri::command] patterns
        assert len(tauri) >= 1

    def test_tauri_command_pattern_text(self) -> None:
        patterns = extract_rust_patterns("src-tauri/src/commands.rs", RUST_T3_BASELINE)
        tauri = [p for p in patterns if p.kind == "tauri_command"]
        assert all("#[tauri::command]" in p.pattern for p in tauri)


class TestFunctionSignatureExtraction:
    """Test function signature detection."""

    def test_extracts_function_signatures(self) -> None:
        patterns = extract_rust_patterns("src-tauri/src/commands.rs", RUST_T3_BASELINE)
        sigs = [p for p in patterns if p.kind == "function_signature"]
        assert len(sigs) >= 2

    def test_baseline_signature_params(self) -> None:
        patterns = extract_rust_patterns("src-tauri/src/commands.rs", RUST_T3_BASELINE)
        sigs = [p for p in patterns if p.kind == "function_signature"]
        search_sig = next((s for s in sigs if "local_db_search" in s.pattern), None)
        assert search_sig is not None
        assert "keyword" in search_sig.pattern
        assert "limit" in search_sig.pattern

    def test_t3_offset_added(self) -> None:
        """T3 scenario: offset parameter is added to local_db_search."""
        patterns = extract_rust_patterns("src-tauri/src/commands.rs", RUST_T3_OFFSET_ADDED)
        sigs = [p for p in patterns if p.kind == "function_signature"]
        search_sig = next((s for s in sigs if "local_db_search" in s.pattern), None)
        assert search_sig is not None
        assert "offset" in search_sig.pattern
        assert "keyword" in search_sig.pattern
        assert "limit" in search_sig.pattern

    def test_t4_page_size_replacement(self) -> None:
        """T4 scenario: keyword/limit replaced by page/size."""
        patterns = extract_rust_patterns("src-tauri/src/commands.rs", RUST_T4_PAGE_SIZE)
        sigs = [p for p in patterns if p.kind == "function_signature"]
        search_sig = next((s for s in sigs if "local_db_search" in s.pattern), None)
        assert search_sig is not None
        assert "page" in search_sig.pattern
        assert "size" in search_sig.pattern
        assert "keyword" not in search_sig.pattern
        assert "limit" not in search_sig.pattern

    def test_return_type_captured(self) -> None:
        patterns = extract_rust_patterns("src-tauri/src/commands.rs", RUST_T3_BASELINE)
        sigs = [p for p in patterns if p.kind == "function_signature"]
        search_sig = next((s for s in sigs if "local_db_search" in s.pattern), None)
        assert search_sig is not None
        assert "Result" in search_sig.pattern


class TestSqlPaginationExtraction:
    """Test SQL pagination pattern detection."""

    def test_detects_limit_in_sql(self) -> None:
        patterns = extract_rust_patterns("src-tauri/src/commands.rs", RUST_T3_BASELINE)
        sql = [p for p in patterns if p.kind == "sql_pagination"]
        assert any("LIMIT" in p.pattern.upper() for p in sql)

    def test_detects_offset_added_in_t3(self) -> None:
        patterns = extract_rust_patterns("src-tauri/src/commands.rs", RUST_T3_OFFSET_ADDED)
        sql = [p for p in patterns if p.kind == "sql_pagination"]
        sql_texts = [p.pattern.upper() for p in sql]
        assert any("OFFSET" in t for t in sql_texts), \
            f"Expected OFFSET in SQL patterns, got: {sql_texts}"


class TestUseDeclarationExtraction:
    """Test Rust use (import) declaration detection."""

    def test_extracts_use_statements(self) -> None:
        patterns = extract_rust_patterns("src-tauri/src/commands.rs", RUST_T3_BASELINE)
        imports = [p for p in patterns if p.kind == "import"]
        assert len(imports) >= 2
        use_texts = [p.pattern for p in imports]
        assert any("tauri" in t for t in use_texts)
        assert any("rusqlite" in t for t in use_texts)


# ---------------------------------------------------------------------------
# Tests: Diff-level integration
# ---------------------------------------------------------------------------


class TestBaselineDiffIntegration:
    """Test baseline diff correctly identifies Rust structural changes."""

    def test_t3_offset_addition_detected(self) -> None:
        """T3: offset parameter added — diff should show new signature."""
        from codegate.analysis.baseline_diff import compute_baseline_diff

        baseline = {"src-tauri/src/commands.rs": RUST_T3_BASELINE}
        current = {"src-tauri/src/commands.rs": RUST_T3_OFFSET_ADDED}

        diff = compute_baseline_diff(baseline, current)

        # The old signature (without offset) should be removed
        removed_sigs = [
            p for p in diff.removed_from_baseline
            if p.kind == "function_signature" and "local_db_search" in p.pattern
        ]
        # The new signature (with offset) should be added
        added_sigs = [
            p for p in diff.added_not_in_baseline
            if p.kind == "function_signature" and "local_db_search" in p.pattern
        ]

        assert len(removed_sigs) >= 1, "Old signature should be in removed"
        assert len(added_sigs) >= 1, "New signature should be in added"
        assert "offset" not in removed_sigs[0].pattern
        assert "offset" in added_sigs[0].pattern

    def test_t4_page_size_replacement_detected(self) -> None:
        """T4: keyword/limit → page/size — diff should show signature change."""
        from codegate.analysis.baseline_diff import compute_baseline_diff

        baseline = {"src-tauri/src/commands.rs": RUST_T3_BASELINE}
        current = {"src-tauri/src/commands.rs": RUST_T4_PAGE_SIZE}

        diff = compute_baseline_diff(baseline, current)

        removed_sigs = [
            p for p in diff.removed_from_baseline
            if p.kind == "function_signature" and "local_db_search" in p.pattern
        ]
        added_sigs = [
            p for p in diff.added_not_in_baseline
            if p.kind == "function_signature" and "local_db_search" in p.pattern
        ]

        assert len(removed_sigs) >= 1
        assert len(added_sigs) >= 1

        # Old: keyword, limit
        assert "keyword" in removed_sigs[0].pattern
        assert "limit" in removed_sigs[0].pattern

        # New: page, size
        assert "page" in added_sigs[0].pattern
        assert "size" in added_sigs[0].pattern

    def test_t3_sql_offset_added(self) -> None:
        """T3: SQL OFFSET added — diff should detect new pagination pattern."""
        from codegate.analysis.baseline_diff import compute_baseline_diff

        baseline = {"src-tauri/src/commands.rs": RUST_T3_BASELINE}
        current = {"src-tauri/src/commands.rs": RUST_T3_OFFSET_ADDED}

        diff = compute_baseline_diff(baseline, current)

        added_sql = [
            p for p in diff.added_not_in_baseline
            if p.kind == "sql_pagination"
        ]
        assert any("OFFSET" in p.pattern.upper() for p in added_sql), \
            f"Expected OFFSET added, got: {[p.pattern for p in added_sql]}"

    def test_unchanged_get_config_preserved(self) -> None:
        """get_config() is unchanged between T3 baseline and offset variant."""
        from codegate.analysis.baseline_diff import compute_baseline_diff

        baseline = {"src-tauri/src/commands.rs": RUST_T3_BASELINE}
        current = {"src-tauri/src/commands.rs": RUST_T3_OFFSET_ADDED}

        diff = compute_baseline_diff(baseline, current)

        preserved_sigs = [
            p for p in diff.unchanged_baseline
            if p.kind == "function_signature" and "get_config" in p.pattern
        ]
        assert len(preserved_sigs) >= 1, "get_config should be preserved"
