"""应用角色仓库与权限策略。"""
import os
import sqlite3
import threading
from typing import Iterable


VALID_ROLES = frozenset({"applicant", "handler", "approver", "admin"})


class RoleManager:
    def __init__(self, db_path: str = "game_data/auth.db"):
        self.db_path = db_path
        self._lock = threading.Lock()
        parent = os.path.dirname(db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        conn = self._connect()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_roles (
                    user_id INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    PRIMARY KEY (user_id, role)
                )
            """)
            conn.commit()
        finally:
            conn.close()

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def roles_for(self, user_id: int) -> tuple[str, ...]:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT role FROM user_roles WHERE user_id=? ORDER BY role",
                    (user_id,),
                ).fetchall()
                return tuple(row["role"] for row in rows)
            finally:
                conn.close()

    def assign(self, user_id: int, role: str) -> None:
        if role not in VALID_ROLES:
            raise ValueError("无效角色")
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO user_roles (user_id, role) VALUES (?, ?)",
                    (user_id, role),
                )
                conn.commit()
            finally:
                conn.close()

    def revoke(self, user_id: int, role: str) -> bool:
        with self._lock:
            conn = self._connect()
            try:
                cursor = conn.execute(
                    "DELETE FROM user_roles WHERE user_id=? AND role=?",
                    (user_id, role),
                )
                conn.commit()
                return cursor.rowcount > 0
            finally:
                conn.close()

    @staticmethod
    def allowed(roles: Iterable[str], capability: str) -> bool:
        roles = set(roles)
        if "admin" in roles:
            return True
        grants = {
            "submit_form": {"applicant"},
            "take_task": {"handler"},
            "approve": {"approver"},
            "edit_template": {"admin"},
        }
        return bool(roles & grants.get(capability, set()))
