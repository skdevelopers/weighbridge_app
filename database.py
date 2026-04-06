import sqlite3
from typing import List, Any, Optional
import config


class Database:
    """
    Optimized SQLite storage for weighbridge system.

    Fixes:
    - auto-repairs old duplicate OPEN tickets before unique index creation
    - keeps sqlite3.Row compatibility
    - uses first_date/first_time + second_date/second_time consistently
    - allows main.py compatibility via update_ticket()
    """

    def __init__(self, db_name: str = config.DB_NAME) -> None:
        self.conn = sqlite3.connect(db_name)
        self.conn.row_factory = sqlite3.Row

        self.create_tables()
        self.ensure_schema()
        self.normalize_legacy_data()
        self.create_indexes()

    # =========================================================
    # INTERNAL HELPERS
    # =========================================================
    def _column_names(self) -> List[str]:
        cursor = self.conn.execute("PRAGMA table_info(tickets)")
        return [row["name"] for row in cursor.fetchall()]

    def _has_column(self, column_name: str) -> bool:
        return column_name in self._column_names()

    def _safe_text(self, value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip()

    def _safe_int(self, value: Any) -> int:
        try:
            return abs(int(float(str(value).strip())))
        except Exception:
            return 0

    def _safe_float(self, value: Any) -> float:
        try:
            raw = str(value).strip()
            return float(raw) if raw else 0.0
        except Exception:
            return 0.0

    # =========================================================
    # TABLE CREATION
    # =========================================================
    def create_tables(self) -> None:
        self.conn.execute(
            """
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
            """
        )
        self.conn.commit()

    # =========================================================
    # SAFE MIGRATION
    # =========================================================
    def ensure_schema(self) -> None:
        columns = self._column_names()

        def add(col: str, sql: str) -> None:
            if col not in columns:
                self.conn.execute(sql)

        add("first_date", "ALTER TABLE tickets ADD COLUMN first_date TEXT")
        add("first_time", "ALTER TABLE tickets ADD COLUMN first_time TEXT")
        add("second_date", "ALTER TABLE tickets ADD COLUMN second_date TEXT")
        add("second_time", "ALTER TABLE tickets ADD COLUMN second_time TEXT")
        add("first_mode", "ALTER TABLE tickets ADD COLUMN first_mode TEXT")
        add("second_mode", "ALTER TABLE tickets ADD COLUMN second_mode TEXT")
        add("weight_type", "ALTER TABLE tickets ADD COLUMN weight_type TEXT")
        add("payment_status", "ALTER TABLE tickets ADD COLUMN payment_status TEXT")
        add("paid_amount", "ALTER TABLE tickets ADD COLUMN paid_amount REAL DEFAULT 0")
        add("remarks", "ALTER TABLE tickets ADD COLUMN remarks TEXT")
        add("status", "ALTER TABLE tickets ADD COLUMN status TEXT DEFAULT 'OPEN'")
        add("created_at", "ALTER TABLE tickets ADD COLUMN created_at TEXT DEFAULT CURRENT_TIMESTAMP")

        # legacy compatibility
        add("ticket_date", "ALTER TABLE tickets ADD COLUMN ticket_date TEXT")
        add("ticket_time", "ALTER TABLE tickets ADD COLUMN ticket_time TEXT")

        self.conn.commit()

    # =========================================================
    # LEGACY / DUPLICATE NORMALIZATION
    # =========================================================
    def normalize_legacy_data(self) -> None:
        """
        1. Backfill first_date/first_time from old ticket_date/ticket_time.
        2. Remove duplicate OPEN rows per vehicle before unique index creation.
        3. Ensure blank status becomes OPEN.
        """
        if self._has_column("ticket_date"):
            self.conn.execute(
                """
                UPDATE tickets
                SET first_date = COALESCE(NULLIF(first_date, ''), ticket_date)
                WHERE (first_date IS NULL OR first_date = '')
                  AND ticket_date IS NOT NULL
                  AND ticket_date <> ''
                """
            )

        if self._has_column("ticket_time"):
            self.conn.execute(
                """
                UPDATE tickets
                SET first_time = COALESCE(NULLIF(first_time, ''), ticket_time)
                WHERE (first_time IS NULL OR first_time = '')
                  AND ticket_time IS NOT NULL
                  AND ticket_time <> ''
                """
            )

        self.conn.execute(
            """
            UPDATE tickets
            SET status='OPEN'
            WHERE status IS NULL OR TRIM(status) = ''
            """
        )

        duplicates = self.conn.execute(
            """
            SELECT vehicle_no
            FROM tickets
            WHERE status='OPEN'
            GROUP BY vehicle_no
            HAVING COUNT(*) > 1
            """
        ).fetchall()

        for row in duplicates:
            vehicle_no = row["vehicle_no"]
            open_rows = self.conn.execute(
                """
                SELECT id
                FROM tickets
                WHERE vehicle_no=? AND status='OPEN'
                ORDER BY id DESC
                """,
                (vehicle_no,),
            ).fetchall()

            if len(open_rows) <= 1:
                continue

            keep_id = open_rows[0]["id"]
            old_ids = [r["id"] for r in open_rows[1:]]

            for old_id in old_ids:
                self.conn.execute(
                    """
                    UPDATE tickets
                    SET status='CANCELLED_DUPLICATE'
                    WHERE id=? AND id<>?
                    """,
                    (old_id, keep_id),
                )

        self.conn.commit()

    # =========================================================
    # INDEXES
    # =========================================================
    def create_indexes(self) -> None:
        try:
            self.conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_open_vehicle
                ON tickets(vehicle_no)
                WHERE status='OPEN'
                """
            )
        except sqlite3.IntegrityError:
            self.normalize_legacy_data()
            self.conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_open_vehicle
                ON tickets(vehicle_no)
                WHERE status='OPEN'
                """
            )

        try:
            self.conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_sr_no
                ON tickets(sr_no)
                WHERE sr_no IS NOT NULL AND sr_no <> ''
                """
            )
        except sqlite3.IntegrityError:
            pass

        self.conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_tickets_vehicle_no
            ON tickets(vehicle_no)
            """
        )

        self.conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_tickets_status
            ON tickets(status)
            """
        )

        self.conn.commit()

    # =========================================================
    # SERIAL NUMBER
    # =========================================================
    def next_sr_no(self) -> str:
        row = self.conn.execute(
            "SELECT id FROM tickets ORDER BY id DESC LIMIT 1"
        ).fetchone()
        next_id = 1 if row is None else row["id"] + 1
        return f"WB-{next_id:06d}"

    # =========================================================
    # FIRST PASS INSERT / UPSERT
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
        sr_no = self._safe_text(sr_no)
        vehicle_no = self._safe_text(vehicle_no)
        customer_name = self._safe_text(customer_name)
        material_name = self._safe_text(material_name)
        first_weight = self._safe_int(first_weight)
        first_date = self._safe_text(first_date)
        first_time = self._safe_text(first_time)
        first_mode = self._safe_text(first_mode) or "WithOut Driver"
        payment_status = self._safe_text(payment_status) or "Pending"
        paid_amount = self._safe_float(paid_amount)
        remarks = self._safe_text(remarks)

        existing = self.find_open_ticket(vehicle_no)
        if existing is not None:
            self.conn.execute(
                """
                UPDATE tickets
                SET sr_no=?,
                    customer_name=?,
                    material_name=?,
                    first_weight=?,
                    first_date=?,
                    first_time=?,
                    first_mode=?,
                    payment_status=?,
                    paid_amount=?,
                    remarks=?,
                    second_weight=0,
                    net_weight=0,
                    second_date='',
                    second_time='',
                    second_mode='',
                    status='OPEN'
                WHERE id=?
                """,
                (
                    sr_no,
                    customer_name,
                    material_name,
                    first_weight,
                    first_date,
                    first_time,
                    first_mode,
                    payment_status,
                    paid_amount,
                    remarks,
                    existing["id"],
                ),
            )
            self.conn.commit()
            return int(existing["id"])

        cursor = self.conn.execute(
            """
            INSERT INTO tickets (
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
                remarks,
                status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN')
            """,
            (
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
                remarks,
            ),
        )

        self.conn.commit()
        return int(cursor.lastrowid)

    # =========================================================
    # GENERAL UPDATE METHOD
    # =========================================================
    def update_ticket(
        self,
        ticket_id: int,
        vehicle_no: str,
        customer_name: str,
        material_name: str,
        first_weight: int,
        second_weight: int,
        net_weight: int,
        payment_status: str,
        paid_amount: float,
        remarks: str,
        status: str,
        sr_no: Optional[str] = None,
        first_date: Optional[str] = None,
        first_time: Optional[str] = None,
        second_date: Optional[str] = None,
        second_time: Optional[str] = None,
        first_mode: Optional[str] = None,
        second_mode: Optional[str] = None,
        weight_type: Optional[str] = None,
        ticket_date: Optional[str] = None,
        ticket_time: Optional[str] = None,
    ) -> None:
        first_date_final = self._safe_text(first_date or ticket_date)
        first_time_final = self._safe_text(first_time or ticket_time)

        self.conn.execute(
            """
            UPDATE tickets
            SET sr_no = COALESCE(?, sr_no),
                vehicle_no=?,
                customer_name=?,
                material_name=?,
                first_weight=?,
                second_weight=?,
                net_weight=?,
                first_date = COALESCE(NULLIF(?, ''), first_date),
                first_time = COALESCE(NULLIF(?, ''), first_time),
                second_date=?,
                second_time=?,
                first_mode = COALESCE(NULLIF(?, ''), first_mode),
                second_mode=?,
                weight_type = COALESCE(NULLIF(?, ''), weight_type),
                payment_status=?,
                paid_amount=?,
                remarks=?,
                status=?
            WHERE id=?
            """,
            (
                self._safe_text(sr_no) if sr_no is not None else None,
                self._safe_text(vehicle_no),
                self._safe_text(customer_name),
                self._safe_text(material_name),
                self._safe_int(first_weight),
                self._safe_int(second_weight),
                self._safe_int(net_weight),
                first_date_final,
                first_time_final,
                self._safe_text(second_date),
                self._safe_text(second_time),
                self._safe_text(first_mode),
                self._safe_text(second_mode),
                self._safe_text(weight_type),
                self._safe_text(payment_status) or "Pending",
                self._safe_float(paid_amount),
                self._safe_text(remarks),
                self._safe_text(status) or "OPEN",
                int(ticket_id),
            ),
        )
        self.conn.commit()

    # =========================================================
    # SECOND PASS UPDATE
    # =========================================================
    def complete_ticket(
        self,
        ticket_id: int,
        second_weight: int,
        net_weight: int,
        second_date: str,
        second_time: str,
        second_mode: str,
    ) -> None:
        self.conn.execute(
            """
            UPDATE tickets
            SET second_weight=?,
                net_weight=?,
                second_date=?,
                second_time=?,
                second_mode=?,
                status='COMPLETED'
            WHERE id=?
            """,
            (
                self._safe_int(second_weight),
                self._safe_int(net_weight),
                self._safe_text(second_date),
                self._safe_text(second_time),
                self._safe_text(second_mode) or "WithOut Driver",
                int(ticket_id),
            ),
        )
        self.conn.commit()

    # =========================================================
    # FETCH
    # =========================================================
    def fetch_recent_tickets(self, limit: int = 100):
        return self.conn.execute(
            """
            SELECT * FROM tickets
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    def find_ticket_by_sr_no(self, sr_no: str):
        return self.conn.execute(
            """
            SELECT * FROM tickets
            WHERE sr_no=?
            LIMIT 1
            """,
            (sr_no,),
        ).fetchone()

    def find_ticket_by_id(self, ticket_id: int):
        return self.conn.execute(
            """
            SELECT * FROM tickets
            WHERE id=?
            LIMIT 1
            """,
            (ticket_id,),
        ).fetchone()

    def find_open_ticket(self, vehicle_no: str):
        return self.conn.execute(
            """
            SELECT * FROM tickets
            WHERE vehicle_no=? AND status='OPEN'
            ORDER BY id DESC
            LIMIT 1
            """,
            (vehicle_no,),
        ).fetchone()

    def find_by_vehicle_or_sr(self, keyword: str):
        pattern = f"%{keyword}%"
        return self.conn.execute(
            """
            SELECT * FROM tickets
            WHERE vehicle_no LIKE ? OR sr_no LIKE ?
            ORDER BY id DESC
            """,
            (pattern, pattern),
        ).fetchall()

    # =========================================================
    # CLOSE
    # =========================================================
    def close(self) -> None:
        try:
            self.conn.close()
        except Exception:
            pass