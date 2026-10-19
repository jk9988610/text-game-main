"""组织、成员和组织内标签管理。"""
import secrets
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any


ORG_LABELS = frozenset({"applicant", "handler", "approver", "admin"})


class OrganizationManager:
    def __init__(self, db_path: str = "game_data/auth.db"):
        self.db_path = db_path
        self._lock = threading.Lock()
        conn = self._connect()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS organizations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    join_code TEXT NOT NULL UNIQUE,
                    owner_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS organization_members (
                    organization_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    label TEXT NOT NULL,
                    joined_at TEXT NOT NULL,
                    PRIMARY KEY (organization_id, user_id, label)
                );
            """)
            conn.commit()
        finally:
            conn.close()

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def create(self, name: str, owner_id: int) -> dict[str, Any]:
        name = name.strip()
        if not name or len(name) > 80:
            raise ValueError("组织名称无效")
        now = datetime.now(timezone.utc).isoformat()
        for _ in range(5):
            code = secrets.token_urlsafe(8)
            try:
                with self._lock:
                    conn = self._connect()
                    try:
                        cur = conn.execute(
                            "INSERT INTO organizations (name, join_code, owner_id, created_at) VALUES (?, ?, ?, ?)",
                            (name, code, owner_id, now),
                        )
                        org_id = cur.lastrowid
                        conn.execute(
                            "INSERT INTO organization_members (organization_id, user_id, label, joined_at) VALUES (?, ?, ?, ?)",
                            (org_id, owner_id, "admin", now),
                        )
                        conn.commit()
                    finally:
                        conn.close()
                return self.get(org_id, owner_id)
            except sqlite3.IntegrityError:
                continue
        raise RuntimeError("无法生成组织邀请码")

    def get(self, organization_id: int, user_id: int | None = None):
        conn = self._connect()
        try:
            org = conn.execute("SELECT * FROM organizations WHERE id=?", (organization_id,)).fetchone()
            if not org:
                return None
            member = None
            if user_id is not None:
                member = conn.execute(
                    "SELECT label FROM organization_members WHERE organization_id=? AND user_id=?",
                    (organization_id, user_id),
                ).fetchall()
        finally:
            conn.close()
        result = dict(org)
        result["labels"] = [row["label"] for row in (member or [])]
        return result

    def join(self, join_code: str, user_id: int):
        conn = self._connect()
        try:
            org = conn.execute("SELECT * FROM organizations WHERE join_code=?", (join_code.strip(),)).fetchone()
        finally:
            conn.close()
        if not org:
            raise KeyError("组织邀请码不存在")
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO organization_members (organization_id, user_id, label, joined_at) VALUES (?, ?, ?, ?)",
                    (org["id"], user_id, "applicant", now),
                )
                conn.commit()
            finally:
                conn.close()
        return self.get(org["id"], user_id)

    def list_for_user(self, user_id: int):
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT o.*, GROUP_CONCAT(m.label) AS labels FROM organizations o "
                "JOIN organization_members m ON m.organization_id=o.id "
                "WHERE m.user_id=? GROUP BY o.id ORDER BY o.created_at DESC", (user_id,)
            ).fetchall()
        finally:
            conn.close()
        return [{**dict(row), "labels": row["labels"].split(",") if row["labels"] else []} for row in rows]

    def members(self, organization_id: int):
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT user_id, GROUP_CONCAT(label) AS labels, MIN(joined_at) AS joined_at "
                "FROM organization_members WHERE organization_id=? GROUP BY user_id",
                (organization_id,),
            ).fetchall()
        finally:
            conn.close()
        return [{**dict(row), "labels": row["labels"].split(",") if row["labels"] else []} for row in rows]

    def set_labels(self, organization_id: int, user_id: int, labels: list[str]) -> None:
        labels = list(dict.fromkeys(labels))
        if not labels or any(label not in ORG_LABELS for label in labels):
            raise ValueError("组织标签无效")
        with self._lock:
            conn = self._connect()
            try:
                exists = conn.execute(
                    "SELECT 1 FROM organization_members WHERE organization_id=? AND user_id=?",
                    (organization_id, user_id),
                ).fetchone()
                if not exists:
                    raise KeyError("用户不是组织成员")
                conn.execute(
                    "DELETE FROM organization_members WHERE organization_id=? AND user_id=?",
                    (organization_id, user_id),
                )
                now = datetime.now(timezone.utc).isoformat()
                conn.executemany(
                    "INSERT INTO organization_members (organization_id, user_id, label, joined_at) VALUES (?, ?, ?, ?)",
                    [(organization_id, user_id, label, now) for label in labels],
                )
                conn.commit()
            finally:
                conn.close()
