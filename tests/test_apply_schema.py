from pathlib import Path

from db.apply_schema import split_statements


def test_splits_at_line_end_semicolons_only():
    sql = (
        "-- header comment;\n"
        "CREATE TABLE t (\n  a int  -- note\n);\n"
        "DO $$ BEGIN CREATE ROLE r; EXCEPTION WHEN duplicate_object THEN NULL; END $$;\n"
        "CREATE INDEX i ON t (a);  -- trailing comment\n"
    )
    assert split_statements(sql) == [
        "CREATE TABLE t (\n  a int  -- note\n)",
        "DO $$ BEGIN CREATE ROLE r; EXCEPTION WHEN duplicate_object THEN NULL; END $$",
        "CREATE INDEX i ON t (a)",
    ]


def test_schema_file_splits_into_complete_statements():
    statements = split_statements(Path("db/schema.sql").read_text())
    assert statements[0] == "CREATE EXTENSION IF NOT EXISTS vector"
    assert all(not s.startswith("--") for s in statements)
    assert sum(s.startswith("CREATE TABLE") for s in statements) == 3
