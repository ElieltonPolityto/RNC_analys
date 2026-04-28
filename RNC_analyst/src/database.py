from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


SCHEMA = """
CREATE TABLE IF NOT EXISTS analyses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    user_name TEXT NOT NULL,
    customer TEXT,
    document TEXT,
    project TEXT,
    revision TEXT,
    provider TEXT,
    model TEXT,
    status TEXT,
    overall_risk TEXT,
    findings_count INTEGER,
    max_severity TEXT,
    pdf_name TEXT,
    upload_path TEXT,
    report_xlsx_path TEXT,
    report_md_path TEXT,
    result_json TEXT NOT NULL,
    pdf_summary_json TEXT NOT NULL
);
"""


def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute(SCHEMA)
        conn.commit()


def save_analysis(db_path: Path, record: dict[str, Any]) -> int:
    columns = [
        "created_at",
        "user_name",
        "customer",
        "document",
        "project",
        "revision",
        "provider",
        "model",
        "status",
        "overall_risk",
        "findings_count",
        "max_severity",
        "pdf_name",
        "upload_path",
        "report_xlsx_path",
        "report_md_path",
        "result_json",
        "pdf_summary_json",
    ]
    payload = []
    for column in columns:
        value = record.get(column)
        if column.endswith("_json") and not isinstance(value, str):
            value = json.dumps(value or {}, ensure_ascii=False)
        payload.append(value)

    placeholders = ", ".join("?" for _ in columns)
    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute(
            f"INSERT INTO analyses ({', '.join(columns)}) VALUES ({placeholders})",
            payload,
        )
        conn.commit()
        return int(cursor.lastrowid)


def list_analyses(db_path: Path, limit: int = 200) -> list[dict[str, Any]]:
    if not db_path.exists():
        return []
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT id, created_at, user_name, customer, document, project, revision,
                   provider, model, status, overall_risk, findings_count,
                   max_severity, pdf_name, report_xlsx_path, report_md_path
            FROM analyses
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]

