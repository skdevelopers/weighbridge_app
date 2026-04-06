import ast
import inspect
import operator as op
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
from typing import Optional, Dict, Any, Callable

import config
from database import Database
from printer import PrinterService
from serial_service import SerialService


_ALLOWED_OPERATORS = {
    ast.Add: op.add,
    ast.Sub: op.sub,
    ast.Mult: op.mul,
    ast.Div: op.truediv,
    ast.FloorDiv: op.floordiv,
    ast.Mod: op.mod,
    ast.Pow: op.pow,
    ast.USub: op.neg,
    ast.UAdd: op.pos,
}


def safe_eval(expression: str) -> float:
    def _eval(node):
        if isinstance(node, ast.Num):
            return node.n
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_OPERATORS:
            return _ALLOWED_OPERATORS[type(node.op)](_eval(node.left), _eval(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_OPERATORS:
            return _ALLOWED_OPERATORS[type(node.op)](_eval(node.operand))
        raise ValueError("Unsupported expression")

    parsed = ast.parse(expression, mode="eval")
    return _eval(parsed.body)


class WeighbridgeApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(config.APP_TITLE)
        self.root.geometry(config.APP_GEOMETRY)
        self.root.configure(bg="#d9d9d9")

        self.db = Database()
        self.printer = PrinterService()
        self.serial_service = SerialService(
            port=config.SERIAL_PORT,
            baud_rate=config.BAUD_RATE,
            timeout=config.SERIAL_TIMEOUT,
            demo_mode=config.DEMO_MODE,
        )

        self.current_live_weight = 0
        self.current_workflow = "FIRST"

        self.current_loaded_ticket_id: Optional[int] = None
        self.current_loaded_ticket_sr_no: Optional[str] = None
        self.current_loaded_ticket_status: Optional[str] = None

        self.first_pass_date: str = ""
        self.first_pass_time: str = ""
        self.second_pass_date: str = ""
        self.second_pass_time: str = ""

        self.last_print_payload: Optional[Dict[str, Any]] = None
        self.auto_capture_done = False
        self.entries: Dict[str, tk.Entry] = {}

        self._build_variables()
        self._build_layout()
        self._bind_shortcuts()
        self._connect_serial()
        self._load_recent_tickets()
        self._reset_form()
        self._refresh_weight_loop()

    # =========================================================
    # SAFE ROW HELPERS
    # =========================================================
    def _row_value(self, row: Any, key: str, default: Any = None) -> Any:
        if row is None:
            return default

        try:
            if isinstance(row, dict):
                return row.get(key, default)
        except Exception:
            pass

        try:
            keys = row.keys()
            if key in keys:
                value = row[key]
                return default if value is None else value
        except Exception:
            pass

        try:
            value = row[key]
            return default if value is None else value
        except Exception:
            pass

        try:
            value = getattr(row, key)
            return default if value is None else value
        except Exception:
            pass

        return default

    def _row_to_dict(self, row: Any) -> Dict[str, Any]:
        if row is None:
            return {}

        if isinstance(row, dict):
            return dict(row)

        try:
            return {key: row[key] for key in row.keys()}
        except Exception:
            pass

        try:
            return dict(row)
        except Exception:
            pass

        return {}

    # =========================================================
    # VARIABLES
    # =========================================================
    def _build_variables(self) -> None:
        self.sr_no_var = tk.StringVar()
        self.vehicle_no_var = tk.StringVar()
        self.customer_name_var = tk.StringVar()
        self.material_name_var = tk.StringVar()

        self.first_weight_var = tk.StringVar(value="0")
        self.second_weight_var = tk.StringVar(value="0")
        self.net_weight_var = tk.StringVar(value="0")

        self.paid_amount_var = tk.StringVar(value="0")
        self.payment_status_var = tk.StringVar(value="Pending")
        self.remarks_var = tk.StringVar()

        self.workflow_var = tk.StringVar(value="FIRST PASS")
        self.live_weight_var = tk.StringVar(value="0 KG")
        self.stability_var = tk.StringVar(value="UNSTABLE")
        self.status_var = tk.StringVar(value="Ready")

        self.demo_mode_var = tk.BooleanVar(value=config.DEMO_MODE)
        self.auto_capture_var = tk.BooleanVar(value=config.AUTO_CAPTURE_ENABLED)
        self.port_var = tk.StringVar(value=config.SERIAL_PORT)

        self.info_first_dt_var = tk.StringVar(value="-")
        self.info_second_dt_var = tk.StringVar(value="-")
        self.info_loaded_sr_var = tk.StringVar(value="-")
        self.info_loaded_status_var = tk.StringVar(value="-")
        self.info_vehicle_var = tk.StringVar(value="-")

    # =========================================================
    # UI
    # =========================================================
    def _build_layout(self) -> None:
        header = tk.Frame(self.root, bg="#1f2937", height=58)
        header.pack(fill="x")

        tk.Label(
            header,
            text=config.COMPANY_NAME,
            bg="#1f2937",
            fg="white",
            font=("Arial", 18, "bold"),
        ).pack(side="left", padx=12, pady=10)

        tk.Label(
            header,
            text=config.COMPANY_PHONE,
            bg="#1f2937",
            fg="white",
            font=("Arial", 11, "bold"),
        ).pack(side="right", padx=12)

        body = tk.Frame(self.root, bg="#d9d9d9")
        body.pack(fill="both", expand=True, padx=8, pady=8)

        left = tk.Frame(body, bg="#d9d9d9")
        left.pack(side="left", fill="both", expand=True, padx=(0, 6))

        right = tk.Frame(body, bg="#d9d9d9", width=330)
        right.pack(side="right", fill="y")

        self._build_form(left)
        self._build_table(left)
        self._build_live_panel(right)
        self._build_status_bar()

    def _add_entry(
        self,
        parent: tk.Widget,
        label: str,
        var: tk.StringVar,
        row: int,
        readonly: bool = False,
        width: int = 32,
    ) -> tk.Entry:
        tk.Label(
            parent,
            text=label,
            bg="#efefef",
            font=("Arial", 10, "bold"),
        ).grid(row=row, column=0, sticky="w", pady=4)

        entry = tk.Entry(parent, textvariable=var, width=width)
        if readonly:
            entry.configure(state="readonly", readonlybackground="white")
        entry.grid(row=row, column=1, sticky="w", pady=4)
        self.entries[label] = entry
        return entry

    def _build_form(self, parent: tk.Frame) -> None:
        form = tk.LabelFrame(parent, text="Ticket Entry", bg="#efefef", padx=10, pady=10)
        form.pack(fill="x", pady=(0, 8))

        row = 0
        self._add_entry(form, "SR No", self.sr_no_var, row, readonly=True)
        row += 1

        self._add_entry(form, "Vehicle No", self.vehicle_no_var, row)
        row += 1

        self._add_entry(form, "Customer Name", self.customer_name_var, row)
        row += 1

        self._add_entry(form, "Material", self.material_name_var, row)
        row += 1

        tk.Label(form, text="Current Mode", bg="#efefef", font=("Arial", 10, "bold")).grid(
            row=row, column=0, sticky="w", pady=4
        )
        tk.Entry(
            form,
            textvariable=self.workflow_var,
            width=32,
            state="readonly",
            readonlybackground="white",
        ).grid(row=row, column=1, sticky="w", pady=4)
        row += 1

        self.first_weight_entry = self._add_entry(form, "1st Weight", self.first_weight_var, row)
        tk.Button(
            form,
            text="Get Scale",
            width=12,
            command=self.fetch_scale_to_active_field,
            bg="#0ea5e9",
            fg="white",
        ).grid(row=row, column=2, padx=6)
        row += 1

        self.second_weight_entry = self._add_entry(form, "2nd Weight", self.second_weight_var, row)
        tk.Button(
            form,
            text="Get Scale",
            width=12,
            command=self.fetch_scale_to_active_field,
            bg="#0ea5e9",
            fg="white",
        ).grid(row=row, column=2, padx=6)
        row += 1

        self._add_entry(form, "Net Weight", self.net_weight_var, row, readonly=True)
        tk.Button(
            form,
            text="Recalculate",
            width=12,
            command=self.calculate_net,
            bg="#6b7280",
            fg="white",
        ).grid(row=row, column=2, padx=6)
        row += 1

        paid_entry = self._add_entry(form, "Paid Amount", self.paid_amount_var, row)
        paid_entry.bind("<FocusIn>", self._on_paid_amount_focus_in)
        paid_entry.bind("<FocusOut>", self._on_paid_amount_focus_out)
        paid_entry.bind("<KeyRelease>", self._on_paid_amount_changed)
        row += 1

        self._add_entry(form, "Payment Status", self.payment_status_var, row, readonly=True)
        row += 1

        self._add_entry(form, "Remarks", self.remarks_var, row)
        row += 1

        info_frame = tk.LabelFrame(form, text="Pass Information", bg="#efefef", padx=10, pady=10)
        info_frame.grid(row=0, column=3, rowspan=row, sticky="nsew", padx=(18, 0))

        form.grid_columnconfigure(3, weight=1)

        info_items = [
            ("Loaded SR", self.info_loaded_sr_var),
            ("Vehicle", self.info_vehicle_var),
            ("Status", self.info_loaded_status_var),
            ("1st Date-Time", self.info_first_dt_var),
            ("2nd Date-Time", self.info_second_dt_var),
        ]

        info_row = 0
        for label, var in info_items:
            tk.Label(
                info_frame,
                text=label,
                bg="#efefef",
                fg="#111827",
                font=("Arial", 10, "bold"),
                anchor="w",
            ).grid(row=info_row, column=0, sticky="w", pady=(0, 4))
            tk.Label(
                info_frame,
                textvariable=var,
                bg="white",
                fg="#111827",
                font=("Arial", 10),
                anchor="w",
                relief="solid",
                bd=1,
                width=34,
                padx=8,
                pady=6,
            ).grid(row=info_row + 1, column=0, sticky="ew", pady=(0, 10))
            info_row += 2

        btns = tk.Frame(form, bg="#efefef")
        btns.grid(row=row, column=0, columnspan=4, pady=(10, 0), sticky="w")

        tk.Button(btns, text="New", width=10, bg="#2563eb", fg="white", command=self._reset_form).pack(side="left", padx=4)
        tk.Button(btns, text="1st Pass", width=10, bg="#0891b2", fg="white", command=self.select_first_pass).pack(side="left", padx=4)
        tk.Button(btns, text="2nd Pass", width=10, bg="#7c3aed", fg="white", command=self.select_second_pass).pack(side="left", padx=4)
        tk.Button(btns, text="Preview", width=10, bg="#4b5563", fg="white", command=self.preview_current_ticket).pack(side="left", padx=4)
        tk.Button(btns, text="Save", width=10, bg="#16a34a", fg="white", command=self.save_current).pack(side="left", padx=4)
        tk.Button(btns, text="Save+Print", width=12, bg="#15803d", fg="white", command=self.save_and_print).pack(side="left", padx=4)

        search_frame = tk.Frame(form, bg="#efefef")
        search_frame.grid(row=row + 1, column=0, columnspan=4, sticky="w", pady=(10, 0))

        self.search_var = tk.StringVar()
        tk.Label(search_frame, text="Find by SR/Vehicle", bg="#efefef", font=("Arial", 10, "bold")).pack(side="left", padx=(0, 6))
        tk.Entry(search_frame, textvariable=self.search_var, width=30).pack(side="left")
        tk.Button(search_frame, text="Go", width=8, bg="#7c3aed", fg="white", command=self.search_tickets).pack(side="left", padx=6)
        tk.Button(search_frame, text="Reload", width=8, bg="#6b7280", fg="white", command=self._load_recent_tickets).pack(side="left", padx=6)

    def _build_table(self, parent: tk.Frame) -> None:
        card = tk.LabelFrame(parent, text="Recent Transactions", bg="#efefef", padx=8, pady=8)
        card.pack(fill="both", expand=True)

        columns = (
            "id",
            "sr_no",
            "vehicle_no",
            "customer_name",
            "first_weight",
            "second_weight",
            "net_weight",
            "status",
            "paid_amount",
            "first_date",
        )
        self.tree = ttk.Treeview(card, columns=columns, show="headings", height=8)

        headings = {
            "id": "Slip",
            "sr_no": "SR No",
            "vehicle_no": "Vehicle No",
            "customer_name": "Customer",
            "first_weight": "1st",
            "second_weight": "2nd",
            "net_weight": "Net",
            "status": "Status",
            "paid_amount": "Paid",
            "first_date": "Date",
        }

        widths = {
            "id": 60,
            "sr_no": 95,
            "vehicle_no": 100,
            "customer_name": 150,
            "first_weight": 70,
            "second_weight": 70,
            "net_weight": 70,
            "status": 110,
            "paid_amount": 80,
            "first_date": 100,
        }

        for col in columns:
            self.tree.heading(col, text=headings[col])
            self.tree.column(col, width=widths[col], anchor="center")

        style = ttk.Style()
        style.configure("Treeview", rowheight=28, font=("Arial", 10))
        style.configure("Treeview.Heading", font=("Arial", 10, "bold"))

        scrollbar = ttk.Scrollbar(card, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.tree.bind("<Double-1>", self.load_selected_ticket)

    def _build_live_panel(self, parent: tk.Frame) -> None:
        panel = tk.LabelFrame(parent, text="Live Weight", bg="#efefef", padx=10, pady=10)
        panel.pack(fill="x")

        tk.Label(
            panel,
            text="LIVE WEIGHT",
            bg="#efefef",
            fg="#111827",
            font=("Arial", 14, "bold"),
        ).pack(pady=(0, 8))

        tk.Label(
            panel,
            textvariable=self.live_weight_var,
            bg="black",
            fg="red",
            width=14,
            height=2,
            font=("Consolas", 28, "bold"),
        ).pack(pady=4)

        self.stability_label = tk.Label(
            panel,
            textvariable=self.stability_var,
            bg="#efefef",
            fg="#b91c1c",
            font=("Arial", 12, "bold"),
        )
        self.stability_label.pack(pady=4)

        self.workflow_label = tk.Label(
            panel,
            text="CURRENT MODE: FIRST PASS",
            bg="#efefef",
            fg="#1d4ed8",
            font=("Arial", 11, "bold"),
        )
        self.workflow_label.pack(pady=2)

        shortcuts = tk.LabelFrame(parent, text="Shortcuts", bg="#efefef", padx=10, pady=10)
        shortcuts.pack(fill="x", pady=8)

        tk.Label(
            shortcuts,
            justify="left",
            anchor="w",
            bg="#efefef",
            font=("Consolas", 10),
            text=(
                "F1 = Select 1st Weight\n"
                "F2 = Select 2nd Weight\n"
                "F3 = Preview Ticket\n"
                "F4 = Save\n"
                "F5 = Fetch From Scale\n"
                "F6 = Save & Print\n"
                "F9 = Calculator"
            ),
        ).pack(fill="x")

        settings = tk.LabelFrame(parent, text="Options", bg="#efefef", padx=10, pady=10)
        settings.pack(fill="x", pady=8)

        tk.Label(settings, text="COM Port", bg="#efefef", font=("Arial", 10, "bold")).grid(row=0, column=0, sticky="w")
        ports = self.serial_service.list_ports()
        ttk.Combobox(
            settings,
            textvariable=self.port_var,
            values=ports if ports else [config.SERIAL_PORT],
            state="readonly",
            width=18,
        ).grid(row=0, column=1, sticky="w", pady=4)

        tk.Checkbutton(
            settings,
            text="Demo Mode",
            variable=self.demo_mode_var,
            bg="#efefef",
            command=self.toggle_demo_mode,
        ).grid(row=1, column=0, sticky="w", pady=4)

        tk.Checkbutton(
            settings,
            text="Auto Capture",
            variable=self.auto_capture_var,
            bg="#efefef",
        ).grid(row=1, column=1, sticky="w", pady=4)

        tk.Button(
            settings,
            text="Reconnect",
            width=14,
            bg="#2563eb",
            fg="white",
            command=self.reconnect_serial,
        ).grid(row=2, column=0, pady=8, sticky="w")

        tk.Button(
            settings,
            text="Get Scale",
            width=14,
            bg="#0f766e",
            fg="white",
            command=self.fetch_scale_to_active_field,
        ).grid(row=2, column=1, pady=8, sticky="w")

    def _build_status_bar(self) -> None:
        status_bar = tk.Frame(self.root, bg="#111827", height=28)
        status_bar.pack(fill="x", side="bottom")

        tk.Label(
            status_bar,
            textvariable=self.status_var,
            bg="#111827",
            fg="white",
            font=("Arial", 9),
        ).pack(side="left", padx=10)

    # =========================================================
    # SHORTCUTS
    # =========================================================
    def _bind_shortcuts(self) -> None:
        self.root.bind("<F1>", lambda event: self.select_first_pass())
        self.root.bind("<F2>", lambda event: self.select_second_pass())
        self.root.bind("<F3>", lambda event: self.preview_current_ticket())
        self.root.bind("<F4>", lambda event: self.save_current())
        self.root.bind("<F5>", lambda event: self.fetch_scale_to_active_field())
        self.root.bind("<F6>", lambda event: self.save_and_print())
        self.root.bind("<F9>", lambda event: self.open_calculator())
        self.root.bind("<Control-s>", lambda event: self.save_current())

    # =========================================================
    # SERIAL
    # =========================================================
    def _connect_serial(self) -> None:
        _, message = self.serial_service.connect()
        self.status_var.set(message)

    def reconnect_serial(self) -> None:
        self.serial_service.disconnect()
        self.serial_service.port = self.port_var.get().strip() or config.SERIAL_PORT
        self.serial_service.demo_mode = self.demo_mode_var.get()
        _, message = self.serial_service.connect()
        self.status_var.set(message)

    def toggle_demo_mode(self) -> None:
        self.serial_service.demo_mode = self.demo_mode_var.get()
        self.reconnect_serial()

    def _refresh_weight_loop(self) -> None:
        self.current_live_weight = self.serial_service.read_weight()
        self.live_weight_var.set(f"{self.current_live_weight} KG")

        if self.serial_service.is_stable():
            stable = self.serial_service.stable_weight()
            self.stability_var.set(f"STABLE ({stable} KG)")
            self.stability_label.configure(fg="#15803d")

            if self.auto_capture_var.get() and not self.auto_capture_done:
                self.fetch_scale_to_active_field()
                self.auto_capture_done = True
        else:
            self.stability_var.set("UNSTABLE")
            self.stability_label.configure(fg="#b91c1c")
            self.auto_capture_done = False

        self.root.after(config.READ_INTERVAL_MS, self._refresh_weight_loop)

    # =========================================================
    # HELPERS
    # =========================================================
    def _safe_int(self, value: Any) -> int:
        try:
            return abs(int(str(value).replace("KG", "").replace("kg", "").strip()))
        except Exception:
            return 0

    def _safe_float(self, value: Any) -> float:
        try:
            raw = str(value).strip()
            return float(raw) if raw else 0.0
        except Exception:
            return 0.0

    def _update_payment_status(self) -> None:
        amount = self._safe_float(self.paid_amount_var.get())
        self.payment_status_var.set("Paid" if amount > 0 else "Pending")

    def _update_info_panel(self) -> None:
        self.info_loaded_sr_var.set(self.current_loaded_ticket_sr_no or self.sr_no_var.get().strip() or "-")
        self.info_loaded_status_var.set(self.current_loaded_ticket_status or "-")
        self.info_vehicle_var.set(self.vehicle_no_var.get().strip() or "-")

        first_dt = "-"
        if self.first_pass_date or self.first_pass_time:
            first_dt = f"{self.first_pass_date} {self.first_pass_time}".strip()
        self.info_first_dt_var.set(first_dt)

        second_dt = "-"
        if self.second_pass_date or self.second_pass_time:
            second_dt = f"{self.second_pass_date} {self.second_pass_time}".strip()
        self.info_second_dt_var.set(second_dt)

    def _on_paid_amount_focus_in(self, event=None) -> None:
        if self.paid_amount_var.get().strip() in {"0", "0.0", "0.00"}:
            self.paid_amount_var.set("")
        self.entries["Paid Amount"].focus_set()
        self.entries["Paid Amount"].selection_range(0, tk.END)

    def _on_paid_amount_focus_out(self, event=None) -> None:
        if not self.paid_amount_var.get().strip():
            self.paid_amount_var.set("0")
        self._update_payment_status()

    def _on_paid_amount_changed(self, event=None) -> None:
        self._update_payment_status()

    def calculate_net(self) -> None:
        first_weight = self._safe_int(self.first_weight_var.get())
        second_weight = self._safe_int(self.second_weight_var.get())
        self.net_weight_var.set(str(abs(first_weight - second_weight)))

    def _focus_active_weight_field(self) -> None:
        if self.current_workflow == "FIRST":
            self.first_weight_entry.focus_set()
            self.first_weight_entry.selection_range(0, tk.END)
        else:
            self.second_weight_entry.focus_set()
            self.second_weight_entry.selection_range(0, tk.END)

    def _set_first_pass_datetime(self, date_value: str, time_value: str) -> None:
        self.first_pass_date = date_value or ""
        self.first_pass_time = time_value or ""
        self._update_info_panel()

    def _set_second_pass_datetime(self, date_value: str, time_value: str) -> None:
        self.second_pass_date = date_value or ""
        self.second_pass_time = time_value or ""
        self._update_info_panel()

    def _ensure_first_pass_datetime(self) -> None:
        if not self.first_pass_date or not self.first_pass_time:
            now = datetime.now()
            self._set_first_pass_datetime(now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S"))

    def _clear_second_pass_datetime(self) -> None:
        self._set_second_pass_datetime("", "")

    def _filter_kwargs_for_callable(self, func: Callable[..., Any], kwargs: Dict[str, Any]) -> Dict[str, Any]:
        try:
            signature = inspect.signature(func)
            accepted = set(signature.parameters.keys())
            return {key: value for key, value in kwargs.items() if key in accepted}
        except Exception:
            return kwargs

    def _db_insert_ticket(self, **kwargs: Any) -> int:
        filtered = self._filter_kwargs_for_callable(self.db.insert_ticket, kwargs)
        return self.db.insert_ticket(**filtered)

    def _db_update_ticket(self, **kwargs: Any) -> Any:
        filtered = self._filter_kwargs_for_callable(self.db.update_ticket, kwargs)
        return self.db.update_ticket(**filtered)

    def _find_open_ticket_for_vehicle(self, vehicle_no: str) -> Optional[Any]:
        vehicle_no = vehicle_no.strip()
        if not vehicle_no:
            return None

        try:
            ticket = self.db.find_open_ticket(vehicle_no)
            if ticket:
                return ticket
        except Exception:
            pass

        try:
            tickets = self.db.find_by_vehicle_or_sr(vehicle_no)
            for item in tickets:
                item_vehicle = str(self._row_value(item, "vehicle_no", "")).strip().lower()
                item_status = str(self._row_value(item, "status", "")).upper()
                if item_vehicle == vehicle_no.lower() and item_status == "OPEN":
                    return item
        except Exception:
            pass

        return None

    def _get_loaded_ticket_from_db(self) -> Optional[Any]:
        if not self.current_loaded_ticket_id:
            return None
        try:
            return self.db.find_ticket_by_id(self.current_loaded_ticket_id)
        except Exception:
            return None

    def _hydrate_datetime_from_ticket(self, ticket: Any) -> None:
        first_date = str(self._row_value(ticket, "first_date", "") or "")
        first_time = str(self._row_value(ticket, "first_time", "") or "")
        second_date = str(self._row_value(ticket, "second_date", "") or "")
        second_time = str(self._row_value(ticket, "second_time", "") or "")

        self._set_first_pass_datetime(first_date, first_time)
        self._set_second_pass_datetime(second_date, second_time)

    def _build_current_payload(self) -> Dict[str, Any]:
        self.calculate_net()
        self._update_payment_status()

        first_weight = self._safe_int(self.first_weight_var.get())
        second_weight = self._safe_int(self.second_weight_var.get())
        net_weight = abs(first_weight - second_weight)

        return {
            "id": self.current_loaded_ticket_id,
            "slip_no": str(self.current_loaded_ticket_id or "").strip(),
            "sr_no": self.sr_no_var.get().strip(),
            "vehicle_no": self.vehicle_no_var.get().strip(),
            "customer_name": self.customer_name_var.get().strip(),
            "material_name": self.material_name_var.get().strip(),
            "first_weight": first_weight,
            "second_weight": second_weight,
            "net_weight": net_weight,
            "payment_status": self.payment_status_var.get().strip(),
            "paid_amount": self._safe_float(self.paid_amount_var.get()),
            "remarks": self.remarks_var.get().strip(),
            "first_date": self.first_pass_date or "",
            "first_time": self.first_pass_time or "",
            "second_date": self.second_pass_date or "",
            "second_time": self.second_pass_time or "",
            "first_mode": "WithOut Driver",
            "second_mode": "WithOut Driver" if second_weight > 0 else "",
            "status": "COMPLETED" if second_weight > 0 else "OPEN",
        }

    def _build_payload_from_db_ticket(self, ticket: Any) -> Dict[str, Any]:
        payload = self._row_to_dict(ticket)

        first_weight = self._safe_int(self._row_value(ticket, "first_weight", 0))
        second_weight = self._safe_int(self._row_value(ticket, "second_weight", 0))

        payload["id"] = self._row_value(ticket, "id")
        payload["slip_no"] = str(self._row_value(ticket, "id", "") or "")
        payload["sr_no"] = self._row_value(ticket, "sr_no", "")
        payload["vehicle_no"] = self._row_value(ticket, "vehicle_no", "")
        payload["customer_name"] = self._row_value(ticket, "customer_name", "")
        payload["material_name"] = self._row_value(ticket, "material_name", "")
        payload["first_weight"] = first_weight
        payload["second_weight"] = second_weight
        payload["net_weight"] = abs(first_weight - second_weight)
        payload["payment_status"] = self._row_value(ticket, "payment_status", "Pending")
        payload["paid_amount"] = self._safe_float(self._row_value(ticket, "paid_amount", 0))
        payload["remarks"] = self._row_value(ticket, "remarks", "")
        payload["first_date"] = self._row_value(ticket, "first_date", "")
        payload["first_time"] = self._row_value(ticket, "first_time", "")
        payload["second_date"] = self._row_value(ticket, "second_date", "")
        payload["second_time"] = self._row_value(ticket, "second_time", "")
        payload["first_mode"] = self._row_value(ticket, "first_mode", "WithOut Driver")
        payload["second_mode"] = self._row_value(ticket, "second_mode", "WithOut Driver" if second_weight > 0 else "")
        payload["status"] = self._row_value(ticket, "status", "OPEN")
        return payload

    def _persist_before_output(self) -> Optional[int]:
        """
        Every preview/print must hit DB first.
        - FIRST workflow: always upsert first pass.
        - SECOND workflow: always save second pass.
        - If a completed ticket is merely loaded for viewing while user is still in FIRST,
          do not wipe 2nd pass data; just use existing row.
        """
        loaded_ticket = self._get_loaded_ticket_from_db()
        loaded_status = str(self._row_value(loaded_ticket, "status", self.current_loaded_ticket_status or "") or "").upper()

        if self.current_workflow == "SECOND":
            return self.save_second_pass()

        if loaded_ticket is not None and loaded_status == "COMPLETED":
            self.current_loaded_ticket_status = "COMPLETED"
            return int(self._row_value(loaded_ticket, "id", 0)) or None

        return self.save_first_pass()

    # =========================================================
    # WORKFLOW SELECTION
    # =========================================================
    def select_first_pass(self) -> None:
        self.current_workflow = "FIRST"
        self.workflow_var.set("FIRST PASS")
        self.workflow_label.configure(text="CURRENT MODE: FIRST PASS")
        self.status_var.set("1st weight mode selected. Type manually or press F5 to fetch from scale.")
        self._focus_active_weight_field()

    def select_second_pass(self) -> None:
        self.current_workflow = "SECOND"
        self.workflow_var.set("SECOND PASS")
        self.workflow_label.configure(text="CURRENT MODE: SECOND PASS")
        self.status_var.set("2nd weight mode selected. Type manually or press F5 to fetch from scale.")
        self._focus_active_weight_field()

    # =========================================================
    # SCALE FETCH
    # =========================================================
    def fetch_scale_to_active_field(self) -> None:
        weight = self.serial_service.stable_weight() if self.serial_service.is_stable() else self.current_live_weight

        if weight <= 0:
            self.status_var.set("No valid scale weight found.")
            return

        if self.current_workflow == "FIRST":
            self.first_weight_var.set(str(weight))
            self.status_var.set(f"1st weight fetched from scale: {weight} KG")
        else:
            self.second_weight_var.set(str(weight))
            self.status_var.set(f"2nd weight fetched from scale: {weight} KG")

        self.calculate_net()
        self._focus_active_weight_field()

    # =========================================================
    # VALIDATION
    # =========================================================
    def _validate_common(self) -> bool:
        if not self.vehicle_no_var.get().strip():
            messagebox.showerror("Validation Error", "Vehicle No is required.")
            return False
        return True

    def _validate_first_save(self) -> bool:
        if not self._validate_common():
            return False
        if self._safe_int(self.first_weight_var.get()) <= 0:
            messagebox.showerror("Validation Error", "1st weight is required.")
            return False
        return True

    def _validate_second_save(self) -> bool:
        if not self._validate_common():
            return False
        if self._safe_int(self.second_weight_var.get()) <= 0:
            messagebox.showerror("Validation Error", "2nd weight is required.")
            return False
        return True

    # =========================================================
    # SAVE LOGIC
    # =========================================================
    def save_first_pass(self) -> Optional[int]:
        if not self._validate_first_save():
            return None

        self._update_payment_status()
        self.calculate_net()
        self._ensure_first_pass_datetime()
        self._clear_second_pass_datetime()

        vehicle_no = self.vehicle_no_var.get().strip()
        customer_name = self.customer_name_var.get().strip()
        material_name = self.material_name_var.get().strip()
        first_weight = self._safe_int(self.first_weight_var.get())
        paid_amount = self._safe_float(self.paid_amount_var.get())
        payment_status = self.payment_status_var.get().strip()
        remarks = self.remarks_var.get().strip() or "First Pass"

        current_ticket = self._get_loaded_ticket_from_db()
        open_ticket = None

        if current_ticket and str(self._row_value(current_ticket, "status", "")).upper() == "OPEN":
            open_ticket = current_ticket
        else:
            open_ticket = self._find_open_ticket_for_vehicle(vehicle_no)

        if open_ticket:
            open_ticket_id = int(self._row_value(open_ticket, "id", 0))
            sr_no = str(self._row_value(open_ticket, "sr_no", "") or self.sr_no_var.get().strip() or self.db.next_sr_no())

            existing_first_date = str(self._row_value(open_ticket, "first_date", "") or "")
            existing_first_time = str(self._row_value(open_ticket, "first_time", "") or "")

            if existing_first_date and existing_first_time:
                self._set_first_pass_datetime(existing_first_date, existing_first_time)

            update_kwargs = {
                "ticket_id": open_ticket_id,
                "sr_no": sr_no,
                "vehicle_no": vehicle_no,
                "customer_name": customer_name,
                "material_name": material_name,
                "first_weight": first_weight,
                "second_weight": 0,
                "net_weight": 0,
                "weight_type": "Difference",
                "payment_status": payment_status,
                "paid_amount": paid_amount,
                "remarks": remarks,
                "first_date": self.first_pass_date,
                "first_time": self.first_pass_time,
                "first_mode": "WithOut Driver",
                "second_date": "",
                "second_time": "",
                "second_mode": "",
                "status": "OPEN",
            }
            self._db_update_ticket(**update_kwargs)

            self.current_loaded_ticket_id = open_ticket_id
            self.current_loaded_ticket_sr_no = sr_no
            self.current_loaded_ticket_status = "OPEN"
            self.sr_no_var.set(sr_no)

            self.status_var.set(f"1st pass updated: {sr_no}")
        else:
            sr_no = self.sr_no_var.get().strip() or self.db.next_sr_no()

            insert_kwargs = {
                "sr_no": sr_no,
                "vehicle_no": vehicle_no,
                "customer_name": customer_name,
                "material_name": material_name,
                "first_weight": first_weight,
                "first_date": self.first_pass_date,
                "first_time": self.first_pass_time,
                "first_mode": "WithOut Driver",
                "payment_status": payment_status,
                "paid_amount": paid_amount,
                "remarks": remarks,
            }
            ticket_id = self._db_insert_ticket(**insert_kwargs)

            self.current_loaded_ticket_id = int(ticket_id)
            self.current_loaded_ticket_sr_no = sr_no
            self.current_loaded_ticket_status = "OPEN"
            self.sr_no_var.set(sr_no)

            self.status_var.set(f"1st pass saved: {sr_no}")

        saved_ticket = self.db.find_ticket_by_id(self.current_loaded_ticket_id)
        if saved_ticket:
            self._hydrate_datetime_from_ticket(saved_ticket)
            self.last_print_payload = self._build_payload_from_db_ticket(saved_ticket)
        else:
            self.last_print_payload = self._build_current_payload()

        self._update_info_panel()
        self._load_recent_tickets()
        return self.current_loaded_ticket_id

    def save_second_pass(self) -> Optional[int]:
        if not self._validate_second_save():
            return None

        self._update_payment_status()
        self.calculate_net()

        vehicle_no = self.vehicle_no_var.get().strip()
        loaded_ticket = self._get_loaded_ticket_from_db()

        ticket = None
        if loaded_ticket and str(self._row_value(loaded_ticket, "status", "")).upper() == "OPEN":
            ticket = loaded_ticket
        else:
            ticket = self._find_open_ticket_for_vehicle(vehicle_no)

        if ticket is None:
            messagebox.showerror("Not Found", "No OPEN ticket found for this vehicle.")
            return None

        ticket_id = int(self._row_value(ticket, "id", 0))
        sr_no = str(self._row_value(ticket, "sr_no", "") or "")
        first_weight = self._safe_int(self._row_value(ticket, "first_weight", 0))
        second_weight = self._safe_int(self.second_weight_var.get())
        net_weight = abs(first_weight - second_weight)

        if first_weight <= 0:
            messagebox.showerror("Validation Error", "Selected/open ticket does not contain valid 1st weight.")
            return None

        original_first_date = str(self._row_value(ticket, "first_date", "") or "")
        original_first_time = str(self._row_value(ticket, "first_time", "") or "")

        if not original_first_date or not original_first_time:
            self._ensure_first_pass_datetime()
            original_first_date = self.first_pass_date
            original_first_time = self.first_pass_time
        else:
            self._set_first_pass_datetime(original_first_date, original_first_time)

        now = datetime.now()
        self._set_second_pass_datetime(now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S"))

        self.first_weight_var.set(str(first_weight))
        self.second_weight_var.set(str(second_weight))
        self.net_weight_var.set(str(net_weight))

        update_kwargs = {
            "ticket_id": ticket_id,
            "sr_no": sr_no,
            "vehicle_no": vehicle_no,
            "customer_name": self.customer_name_var.get().strip(),
            "material_name": self.material_name_var.get().strip(),
            "first_weight": first_weight,
            "second_weight": second_weight,
            "net_weight": net_weight,
            "weight_type": "Difference",
            "payment_status": self.payment_status_var.get().strip(),
            "paid_amount": self._safe_float(self.paid_amount_var.get()),
            "remarks": self.remarks_var.get().strip(),
            "first_date": original_first_date,
            "first_time": original_first_time,
            "first_mode": "WithOut Driver",
            "second_date": self.second_pass_date,
            "second_time": self.second_pass_time,
            "second_mode": "WithOut Driver",
            "status": "COMPLETED",
        }
        self._db_update_ticket(**update_kwargs)

        self.current_loaded_ticket_id = ticket_id
        self.current_loaded_ticket_sr_no = sr_no
        self.current_loaded_ticket_status = "COMPLETED"
        self.sr_no_var.set(sr_no)

        saved_ticket = self.db.find_ticket_by_id(self.current_loaded_ticket_id)
        if saved_ticket:
            self._hydrate_datetime_from_ticket(saved_ticket)
            self.last_print_payload = self._build_payload_from_db_ticket(saved_ticket)
        else:
            self.last_print_payload = self._build_current_payload()

        self._update_info_panel()
        self.status_var.set(f"2nd pass saved: {sr_no}")
        self._load_recent_tickets()
        return self.current_loaded_ticket_id

    def save_current(self) -> Optional[int]:
        self._update_payment_status()
        self.calculate_net()
        return self.save_first_pass() if self.current_workflow == "FIRST" else self.save_second_pass()

    def save_and_print(self) -> None:
        ticket_id = self._persist_before_output()
        if ticket_id is None:
            return

        ticket = self.db.find_ticket_by_id(ticket_id)
        if not ticket:
            messagebox.showerror("Error", "Failed to load saved ticket.")
            return

        payload = self._build_payload_from_db_ticket(ticket)
        self.printer.print_ticket(payload)
        self.last_print_payload = payload
        self.status_var.set(f"Printed: {self._row_value(ticket, 'sr_no', '')}")

    # =========================================================
    # PREVIEW / PRINT
    # =========================================================
    def preview_current_ticket(self) -> None:
        first_weight = self._safe_int(self.first_weight_var.get())
        second_weight = self._safe_int(self.second_weight_var.get())
        vehicle_no = self.vehicle_no_var.get().strip()

        if not vehicle_no and first_weight <= 0 and second_weight <= 0:
            messagebox.showerror("Validation Error", "Enter ticket data before preview.")
            return

        ticket_id = self._persist_before_output()
        if ticket_id is None:
            return

        ticket = self.db.find_ticket_by_id(ticket_id)
        payload = self._build_payload_from_db_ticket(ticket) if ticket else self._build_current_payload()

        self.printer.preview_ticket(self.root, payload)
        self.last_print_payload = payload
        self.status_var.set(f"Preview: {payload.get('sr_no', '') or 'UNSAVED'}")

    # =========================================================
    # TABLE
    # =========================================================
    def _clear_tree(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)

    def _load_recent_tickets(self) -> None:
        self._clear_tree()
        tickets = self.db.fetch_recent_tickets(limit=100)

        for ticket in tickets:
            self.tree.insert(
                "",
                "end",
                values=(
                    self._row_value(ticket, "id", ""),
                    self._row_value(ticket, "sr_no", ""),
                    self._row_value(ticket, "vehicle_no", ""),
                    self._row_value(ticket, "customer_name", ""),
                    self._row_value(ticket, "first_weight", 0),
                    self._row_value(ticket, "second_weight", 0),
                    self._row_value(ticket, "net_weight", 0),
                    self._row_value(ticket, "status", ""),
                    self._row_value(ticket, "paid_amount", 0),
                    self._row_value(ticket, "first_date", ""),
                ),
            )

    def search_tickets(self) -> None:
        keyword = self.search_var.get().strip()
        if not keyword:
            self._load_recent_tickets()
            return

        self._clear_tree()
        tickets = self.db.find_by_vehicle_or_sr(keyword)

        for ticket in tickets:
            self.tree.insert(
                "",
                "end",
                values=(
                    self._row_value(ticket, "id", ""),
                    self._row_value(ticket, "sr_no", ""),
                    self._row_value(ticket, "vehicle_no", ""),
                    self._row_value(ticket, "customer_name", ""),
                    self._row_value(ticket, "first_weight", 0),
                    self._row_value(ticket, "second_weight", 0),
                    self._row_value(ticket, "net_weight", 0),
                    self._row_value(ticket, "status", ""),
                    self._row_value(ticket, "paid_amount", 0),
                    self._row_value(ticket, "first_date", ""),
                ),
            )

        self.status_var.set(f"Found {len(tickets)} result(s)")

    def load_selected_ticket(self, event: tk.Event) -> None:
        selected = self.tree.selection()
        if not selected:
            return

        values = self.tree.item(selected[0], "values")
        if not values:
            return

        sr_no = values[1]
        ticket = self.db.find_ticket_by_sr_no(sr_no)
        if ticket is None:
            self.status_var.set("Ticket not found for loading.")
            return

        self.current_loaded_ticket_id = int(self._row_value(ticket, "id", 0))
        self.current_loaded_ticket_sr_no = str(self._row_value(ticket, "sr_no", "") or "")
        self.current_loaded_ticket_status = str(self._row_value(ticket, "status", "") or "")

        self.sr_no_var.set(str(self._row_value(ticket, "sr_no", "") or ""))
        self.vehicle_no_var.set(str(self._row_value(ticket, "vehicle_no", "") or ""))
        self.customer_name_var.set(str(self._row_value(ticket, "customer_name", "") or ""))
        self.material_name_var.set(str(self._row_value(ticket, "material_name", "") or ""))
        self.first_weight_var.set(str(self._row_value(ticket, "first_weight", 0) or 0))
        self.second_weight_var.set(str(self._row_value(ticket, "second_weight", 0) or 0))

        first_weight = self._safe_int(self._row_value(ticket, "first_weight", 0))
        second_weight = self._safe_int(self._row_value(ticket, "second_weight", 0))
        self.net_weight_var.set(str(abs(first_weight - second_weight)))

        self.paid_amount_var.set(str(self._row_value(ticket, "paid_amount", "0") or "0"))
        self.remarks_var.set(str(self._row_value(ticket, "remarks", "") or ""))

        self._hydrate_datetime_from_ticket(ticket)
        self._update_payment_status()
        self._update_info_panel()

        if str(self._row_value(ticket, "status", "")).upper() == "OPEN":
            self.select_second_pass()
        else:
            self.select_first_pass()

        self.status_var.set(f"Loaded ticket: {self.current_loaded_ticket_sr_no}")

    # =========================================================
    # CALCULATOR
    # =========================================================
    def open_calculator(self) -> None:
        calc = tk.Toplevel(self.root)
        calc.title("Quick Calculator")
        calc.geometry("320x130")
        calc.resizable(False, False)

        entry = tk.Entry(calc, width=32, font=("Consolas", 12))
        entry.pack(padx=10, pady=10, fill="x")

        def calculate() -> None:
            expression = entry.get().strip()
            if not expression:
                return
            try:
                result = safe_eval(expression)
                entry.delete(0, tk.END)
                entry.insert(0, str(result))
            except Exception:
                entry.delete(0, tk.END)
                entry.insert(0, "Error")

        tk.Button(calc, text="=", width=10, command=calculate, bg="#2563eb", fg="white").pack(pady=5)
        entry.focus_set()

    # =========================================================
    # RESET / CLOSE
    # =========================================================
    def _reset_form(self) -> None:
        self.current_loaded_ticket_id = None
        self.current_loaded_ticket_sr_no = None
        self.current_loaded_ticket_status = None
        self.last_print_payload = None

        self.first_pass_date = ""
        self.first_pass_time = ""
        self.second_pass_date = ""
        self.second_pass_time = ""

        self.sr_no_var.set(self.db.next_sr_no())
        self.vehicle_no_var.set("")
        self.customer_name_var.set("")
        self.material_name_var.set("")
        self.first_weight_var.set("0")
        self.second_weight_var.set("0")
        self.net_weight_var.set("0")
        self.paid_amount_var.set("0")
        self.payment_status_var.set("Pending")
        self.remarks_var.set("")

        self.select_first_pass()
        self._update_info_panel()
        self.status_var.set("Ready")
        self.entries["Vehicle No"].focus_set()

    def on_close(self) -> None:
        self.serial_service.disconnect()
        self.db.close()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    app = WeighbridgeApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
