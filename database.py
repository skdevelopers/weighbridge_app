import sqlite3
from typing import List, Optional
import config


class Database:
    """
    Optimized SQLite storage for weighbridge system
    """

    def __init__(self, db_name: str = config.DB_NAME) -> None:
        self.conn = sqlite3.connect(db_name)
        self.conn.row_factory = sqlite3.Row

        self.create_tables()
        self.ensure_schema()

    # =========================================================
    # TABLE CREATION
    # =========================================================
    def create_tables(self) -> None:
        self.conn.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            sr_no TEXT,
            vehicle_no TEXT NOT NULL,
            customer_name TEXT,
            material_name TEXT,

            first_weight INTEGER DEFAULT 0,
            second_weight INTEGER DEFAULT 0,
            net_weight INTEGER DEFAULT 0,

            first_date TEXT,
            first_time TEXT,

            second_date TEXT,
            second_time TEXT,

            first_mode TEXT,
            second_mode TEXT,

            weight_type TEXT,
            payment_status TEXT,
            paid_amount REAL DEFAULT 0,

            remarks TEXT,

            status TEXT DEFAULT 'OPEN',

            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """)
        self.conn.commit()

    # =========================================================
    # SAFE MIGRATION (NO DATA LOSS)
    # =========================================================
    def ensure_schema(self) -> None:
        cursor = self.conn.execute("PRAGMA table_info(tickets)")
        columns = [row["name"] for row in cursor.fetchall()]

        def add(col, sql):
            if col not in columns:
                self.conn.execute(sql)

        add("first_date", "ALTER TABLE tickets ADD COLUMN first_date TEXT")
        add("first_time", "ALTER TABLE tickets ADD COLUMN first_time TEXT")
        add("second_date", "ALTER TABLE tickets ADD COLUMN second_date TEXT")
        add("second_time", "ALTER TABLE tickets ADD COLUMN second_time TEXT")
        add("first_mode", "ALTER TABLE tickets ADD COLUMN first_mode TEXT")
        add("second_mode", "ALTER TABLE tickets ADD COLUMN second_mode TEXT")
        add("status", "ALTER TABLE tickets ADD COLUMN status TEXT DEFAULT 'OPEN'")

        self.conn.commit()

    # =========================================================
    # SERIAL NUMBER
    # =========================================================
    def next_sr_no(self) -> str:
        row = self.conn.execute("SELECT id FROM tickets ORDER BY id DESC LIMIT 1").fetchone()
        next_id = 1 if row is None else row["id"] + 1
        return f"WB-{next_id:06d}"

    # =========================================================
    # FIRST PASS INSERT
    # =========================================================
    def insert_ticket(
        self,
        sr_no: str,
        vehicle_no: str,
        customer_name: str,
        material_name: str,
        first_weight: int,
        first_date: str,
        first_time: str,
        first_mode: str,
        payment_status: str,
        paid_amount: float,
        remarks: str,
    ) -> int:

        cursor = self.conn.execute("""
        INSERT INTO tickets (
            sr_no, vehicle_no, customer_name, material_name,
            first_weight,
            first_date, first_time,
            first_mode,
            payment_status, paid_amount, remarks,
            status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN')
        """, (
            sr_no,
            vehicle_no,
            customer_name,
            material_name,
            first_weight,
            first_date,
            first_time,
            first_mode,
            payment_status,
            paid_amount,
            remarks
        ))

        self.conn.commit()
        return cursor.lastrowid

    # =========================================================
    # SECOND PASS UPDATE (CRITICAL FIX)
    # =========================================================
    def complete_ticket(
        self,
        ticket_id: int,
        second_weight: int,
        net_weight: int,
        second_date: str,
        second_time: str,
        second_mode: str
    ) -> None:

        self.conn.execute("""
        UPDATE tickets
        SET second_weight=?,
            net_weight=?,
            second_date=?,
            second_time=?,
            second_mode=?,
            status='COMPLETED'
        WHERE id=?
        """, (
            second_weight,
            net_weight,
            second_date,
            second_time,
            second_mode,
            ticket_id
        ))

        self.conn.commit()

    # =========================================================
    # FETCH
    # =========================================================
    def fetch_recent_tickets(self, limit: int = 100):
        return self.conn.execute("""
            SELECT * FROM tickets
            ORDER BY id DESC
            LIMIT ?
        """, (limit,)).fetchall()

    def find_ticket_by_sr_no(self, sr_no: str):
        return self.conn.execute("""
            SELECT * FROM tickets
            WHERE sr_no=?
        """, (sr_no,)).fetchone()

    def find_ticket_by_id(self, ticket_id: int):
        return self.conn.execute("""
            SELECT * FROM tickets
            WHERE id=?
        """, (ticket_id,)).fetchone()

    def find_open_ticket(self, vehicle_no: str):
        return self.conn.execute("""
            SELECT * FROM tickets
            WHERE vehicle_no=? AND status='OPEN'
            ORDER BY id DESC LIMIT 1
        """, (vehicle_no,)).fetchone()

    def find_by_vehicle_or_sr(self, keyword: str):
        pattern = f"%{keyword}%"
        return self.conn.execute("""
            SELECT * FROM tickets
            WHERE vehicle_no LIKE ? OR sr_no LIKE ?
            ORDER BY id DESC
        """, (pattern, pattern)).fetchall()

    def close(self) -> None:
        try:
            self.conn.close()
        except Exception:
            pass