"""多人协作流程实例仓库。"""
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict


class ProcessInstanceManager:
    """保存应用流程实例及其参与人。"""

    def __init__(self, db_path: str = "game_data/process_instances.db"):
        self.db_path = db_path
        self._lock = threading.Lock()
        parent = os.path.dirname(db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        conn = self._connect()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS process_instances (
                    instance_id TEXT PRIMARY KEY,
                    app_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    applicant_id INTEGER,
                    handler_id INTEGER,
                    approver_id INTEGER,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.commit()
        finally:
            conn.close()

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def create(self, app_id: str, applicant_id: int | None = None,
               instance_id: str | None = None) -> Dict[str, Any]:
        instance_id = instance_id or uuid.uuid4().hex
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    "INSERT INTO process_instances "
                    "(instance_id, app_id, status, applicant_id, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (instance_id, app_id, "draft", applicant_id, now, now),
                )
                conn.commit()
            finally:
                conn.close()
        return self.get(instance_id)

    def get(self, instance_id: str) -> Dict[str, Any] | None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM process_instances WHERE instance_id=?", (instance_id,)
            ).fetchone()
        finally:
            conn.close()
        return dict(row) if row else None

    def for_app(self, app_id: str, limit: int = 50) -> list[Dict[str, Any]]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM process_instances WHERE app_id=? "
                "ORDER BY updated_at DESC LIMIT ?", (app_id, limit)
            ).fetchall()
        finally:
            conn.close()
        return [dict(row) for row in rows]

    def assign(self, instance_id: str, **participants: int | None) -> Dict[str, Any]:
        allowed = {"applicant_id", "handler_id", "approver_id"}
        updates = {key: value for key, value in participants.items() if key in allowed}
        if not updates:
            raise ValueError("没有可更新的参与人字段")
        now = datetime.now(timezone.utc).isoformat()
        clause = ", ".join(f"{key}=?" for key in updates)
        values = list(updates.values()) + [now, instance_id]
        with self._lock:
            conn = self._connect()
            try:
                cursor = conn.execute(
                    f"UPDATE process_instances SET {clause}, updated_at=? WHERE instance_id=?",
                    values,
                )
                conn.commit()
            finally:
                conn.close()
        if cursor.rowcount == 0:
            raise KeyError("流程实例不存在")
        return self.get(instance_id)

    def set_status(self, instance_id: str, status: str) -> Dict[str, Any]:
        if not status.strip():
            raise ValueError("流程状态不能为空")
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            conn = self._connect()
            try:
                cursor = conn.execute(
                    "UPDATE process_instances SET status=?, updated_at=? WHERE instance_id=?",
                    (status, now, instance_id),
                )
                conn.commit()
            finally:
                conn.close()
        if cursor.rowcount == 0:
            raise KeyError("流程实例不存在")
        return self.get(instance_id)

    def query(self, *, user_id: int | None = None, role: str | None = None,
              status: str | None = None, app_id: str | None = None,
              limit: int = 100) -> list[Dict[str, Any]]:
        fields = {"applicant": "applicant_id", "handler": "handler_id", "approver": "approver_id"}
        conditions = []
        values: list[Any] = []
        if user_id is not None and role in fields:
            conditions.append(f"{fields[role]}=?")
            values.append(user_id)
        if status:
            conditions.append("status=?")
            values.append(status)
        if app_id:
            conditions.append("app_id=?")
            values.append(app_id)
        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        conn = self._connect()
        try:
            rows = conn.execute(
                f"SELECT * FROM process_instances{where} ORDER BY updated_at DESC LIMIT ?",
                (*values, limit),
            ).fetchall()
        finally:
            conn.close()
        return [dict(row) for row in rows]
