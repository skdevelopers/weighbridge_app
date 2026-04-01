import ast
import operator as op
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
from typing import Optional, Dict, Any

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
    """
    Safe calculator evaluator.
    Supports +, -, *, /, //, %, ** and parentheses only.
    """
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
    """
    Final simplified weighbridge desktop app.

    Workflow:
    - F1: activate 1st weight field
    - F2: activate 2nd weight field
    - F5: fetch from scale into active field
    - F4: save to DB
    - F6: save and print
    - F3: preview
    - Manual entry allowed in both weight fields
    """

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
            demo_mode=config.DEMO_MODE
        )

        self.current_live_weight = 0
        self.current_workflow = "FIRST"
        self.current_loaded_ticket_id: Optional[int] = None
        self.current_loaded_ticket_sr_no: Optional[str] = None
        self.current_loaded_ticket_status: Optional[str] = None
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
            font=("Arial", 18, "bold")
        ).pack(side="left", padx=12, pady=10)

        tk.Label(
            header,
            text=config.COMPANY_PHONE,
            bg="#1f2937",
            fg="white",
            font=("Arial", 11, "bold")
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

    def _add_entry(self, parent: tk.Widget, label: str, var: tk.StringVar, row: int, readonly: bool = False) -> tk.Entry:
        tk.Label(
            parent,
            text=label,
            bg="#efefef",
            font=("Arial", 10, "bold")
        ).grid(row=row, column=0, sticky="w", pady=4)

        entry = tk.Entry(parent, textvariable=var, width=32)
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

        tk.Label(form, text="Current Mode", bg="#efefef", font=("Arial", 10, "bold")).grid(row=row, column=0, sticky="w", pady=4)
        tk.Entry(form, textvariable=self.workflow_var, width=32, state="readonly", readonlybackground="white").grid(row=row, column=1, sticky="w", pady=4)
        row += 1

        self.first_weight_entry = self._add_entry(form, "1st Weight", self.first_weight_var, row, readonly=False)
        tk.Button(
            form,
            text="Get Scale",
            width=12,
            command=self.fetch_scale_to_active_field,
            bg="#0ea5e9",
            fg="white"
        ).grid(row=row, column=2, padx=6)
        row += 1

        self.second_weight_entry = self._add_entry(form, "2nd Weight", self.second_weight_var, row, readonly=False)
        tk.Button(
            form,
            text="Get Scale",
            width=12,
            command=self.fetch_scale_to_active_field,
            bg="#0ea5e9",
            fg="white"
        ).grid(row=row, column=2, padx=6)
        row += 1

        self._add_entry(form, "Net Weight", self.net_weight_var, row, readonly=True)
        tk.Button(
            form,
            text="Recalculate",
            width=12,
            command=self.calculate_net,
            bg="#6b7280",
            fg="white"
        ).grid(row=row, column=2, padx=6)
        row += 1

        paid_entry = self._add_entry(form, "Paid Amount", self.paid_amount_var, row, readonly=False)
        paid_entry.bind("<FocusIn>", self._on_paid_amount_focus_in)
        paid_entry.bind("<FocusOut>", self._on_paid_amount_focus_out)
        paid_entry.bind("<KeyRelease>", self._on_paid_amount_changed)
        row += 1

        self._add_entry(form, "Payment Status", self.payment_status_var, row, readonly=True)
        row += 1

        self._add_entry(form, "Remarks", self.remarks_var, row)
        row += 1

        btns = tk.Frame(form, bg="#efefef")
        btns.grid(row=row, column=0, columnspan=3, pady=(10, 0), sticky="w")

        tk.Button(btns, text="New", width=10, bg="#2563eb", fg="white", command=self._reset_form).pack(side="left", padx=4)
        tk.Button(btns, text="1st Pass", width=10, bg="#0891b2", fg="white", command=self.select_first_pass).pack(side="left", padx=4)
        tk.Button(btns, text="2nd Pass", width=10, bg="#7c3aed", fg="white", command=self.select_second_pass).pack(side="left", padx=4)
        tk.Button(btns, text="Preview", width=10, bg="#4b5563", fg="white", command=self.preview_current_ticket).pack(side="left", padx=4)
        tk.Button(btns, text="Save", width=10, bg="#16a34a", fg="white", command=self.save_current).pack(side="left", padx=4)
        tk.Button(btns, text="Save+Print", width=12, bg="#15803d", fg="white", command=self.save_and_print).pack(side="left", padx=4)

        search_frame = tk.Frame(form, bg="#efefef")
        search_frame.grid(row=row + 1, column=0, columnspan=3, sticky="w", pady=(10, 0))

        self.search_var = tk.StringVar()
        tk.Label(search_frame, text="Find by SR/Vehicle", bg="#efefef", font=("Arial", 10, "bold")).pack(side="left", padx=(0, 6))
        tk.Entry(search_frame, textvariable=self.search_var, width=30).pack(side="left")
        tk.Button(search_frame, text="Go", width=8, bg="#7c3aed", fg="white", command=self.search_tickets).pack(side="left", padx=6)
        tk.Button(search_frame, text="Reload", width=8, bg="#6b7280", fg="white", command=self._load_recent_tickets).pack(side="left", padx=6)

    def _build_table(self, parent: tk.Frame) -> None:
        card = tk.LabelFrame(parent, text="Recent Tickets", bg="#efefef", padx=8, pady=8)
        card.pack(fill="both", expand=True)

        columns = (
            "sr_no",
            "vehicle_no",
            "customer_name",
            "first_weight",
            "second_weight",
            "net_weight",
            "status",
            "paid_amount",
            "ticket_date",
        )
        self.tree = ttk.Treeview(card, columns=columns, show="headings", height=12)

        headings = {
            "sr_no": "SR No",
            "vehicle_no": "Vehicle No",
            "customer_name": "Customer",
            "first_weight": "1st",
            "second_weight": "2nd",
            "net_weight": "Net",
            "status": "Status",
            "paid_amount": "Paid",
            "ticket_date": "Date",
        }

        widths = {
            "sr_no": 100,
            "vehicle_no": 110,
            "customer_name": 140,
            "first_weight": 70,
            "second_weight": 70,
            "net_weight": 70,
            "status": 90,
            "paid_amount": 70,
            "ticket_date": 90,
        }

        for col in columns:
            self.tree.heading(col, text=headings[col])
            self.tree.column(col, width=widths[col], anchor="center")

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
            font=("Arial", 14, "bold")
        ).pack(pady=(0, 8))

        tk.Label(
            panel,
            textvariable=self.live_weight_var,
            bg="black",
            fg="red",
            width=14,
            height=2,
            font=("Consolas", 28, "bold")
        ).pack(pady=4)

        self.stability_label = tk.Label(
            panel,
            textvariable=self.stability_var,
            bg="#efefef",
            fg="#b91c1c",
            font=("Arial", 12, "bold")
        )
        self.stability_label.pack(pady=4)

        self.workflow_label = tk.Label(
            panel,
            text="CURRENT MODE: FIRST PASS",
            bg="#efefef",
            fg="#1d4ed8",
            font=("Arial", 11, "bold")
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
            )
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
            width=18
        ).grid(row=0, column=1, sticky="w", pady=4)

        tk.Checkbutton(
            settings,
            text="Demo Mode",
            variable=self.demo_mode_var,
            bg="#efefef",
            command=self.toggle_demo_mode
        ).grid(row=1, column=0, sticky="w", pady=4)

        tk.Checkbutton(
            settings,
            text="Auto Capture",
            variable=self.auto_capture_var,
            bg="#efefef"
        ).grid(row=1, column=1, sticky="w", pady=4)

        tk.Button(
            settings,
            text="Reconnect",
            width=14,
            bg="#2563eb",
            fg="white",
            command=self.reconnect_serial
        ).grid(row=2, column=0, pady=8, sticky="w")

        tk.Button(
            settings,
            text="Get Scale",
            width=14,
            bg="#0f766e",
            fg="white",
            command=self.fetch_scale_to_active_field
        ).grid(row=2, column=1, pady=8, sticky="w")

    def _build_status_bar(self) -> None:
        status_bar = tk.Frame(self.root, bg="#111827", height=28)
        status_bar.pack(fill="x", side="bottom")

        tk.Label(
            status_bar,
            textvariable=self.status_var,
            bg="#111827",
            fg="white",
            font=("Arial", 9)
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
        self.live_weight_var.set("{0} KG".format(self.current_live_weight))

        if self.serial_service.is_stable():
            stable = self.serial_service.stable_weight()
            self.stability_var.set("STABLE ({0} KG)".format(stable))
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
            return float(str(value).strip())
        except Exception:
            return 0.0

    def _update_payment_status(self) -> None:
        amount = self._safe_float(self.paid_amount_var.get())
        self.payment_status_var.set("Paid" if amount > 0 else "Pending")

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
        net = abs(first_weight - second_weight)
        self.net_weight_var.set(str(net))

    def _focus_active_weight_field(self) -> None:
        if self.current_workflow == "FIRST":
            self.first_weight_entry.focus_set()
            self.first_weight_entry.selection_range(0, tk.END)
        else:
            self.second_weight_entry.focus_set()
            self.second_weight_entry.selection_range(0, tk.END)

    def _build_current_payload(self) -> Dict[str, Any]:
        """
        Build payload EXACTLY aligned with DB + printer
        """

        now = datetime.now()

        first_weight = self._safe_int(self.first_weight_var.get())
        second_weight = self._safe_int(self.second_weight_var.get())
        net_weight = abs(first_weight - second_weight)

        # FIRST TIME
        first_date = now.strftime("%Y-%m-%d")
        first_time = now.strftime("%H:%M:%S")

        # SECOND TIME ONLY IF EXISTS
        if second_weight > 0:
            second_date = now.strftime("%Y-%m-%d")
            second_time = now.strftime("%H:%M:%S")
        else:
            second_date = ""
            second_time = ""

        return {
            "sr_no": self.sr_no_var.get().strip(),
            "vehicle_no": self.vehicle_no_var.get().strip(),
            "customer_name": self.customer_name_var.get().strip(),
            "material_name": self.material_name_var.get().strip(),

            "first_weight": first_weight,
            "second_weight": second_weight,
            "net_weight": net_weight,

            "payment_status": self.payment_status_var.get().strip(),
            "paid_amount": self.paid_amount_var.get().strip(),

            "remarks": self.remarks_var.get().strip(),

            "ticket_date": first_date,
            "ticket_time": first_time,

            "second_date": second_date,
            "second_time": second_time,

            "first_mode": "WithOut Driver",
            "second_mode": "WithOut Driver" if second_weight > 0 else "",
        }

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
            self.status_var.set("1st weight fetched from scale: {0} KG".format(weight))
        else:
            self.second_weight_var.set(str(weight))
            self.status_var.set("2nd weight fetched from scale: {0} KG".format(weight))

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

        now = datetime.now()
        sr_no = self.sr_no_var.get().strip() or self.db.next_sr_no()

        ticket_id = self.db.insert_ticket(
            sr_no=sr_no,
            vehicle_no=self.vehicle_no_var.get().strip(),
            customer_name=self.customer_name_var.get().strip(),
            material_name=self.material_name_var.get().strip(),
            first_weight=self._safe_int(self.first_weight_var.get()),
            second_weight=0,
            net_weight=0,
            weight_type="Difference",
            payment_status=self.payment_status_var.get().strip(),
            paid_amount=self._safe_float(self.paid_amount_var.get()),
            remarks=self.remarks_var.get().strip() or "First Pass",
            ticket_date=now.strftime("%Y-%m-%d"),
            ticket_time=now.strftime("%H:%M:%S"),
            status="OPEN"
        )

        self.current_loaded_ticket_id = ticket_id
        self.current_loaded_ticket_sr_no = sr_no
        self.current_loaded_ticket_status = "OPEN"
        self.sr_no_var.set(sr_no)
        self.last_print_payload = self._build_current_payload()

        self.status_var.set("1st pass saved: {0}".format(sr_no))
        self._load_recent_tickets()
        return ticket_id

    def save_second_pass(self) -> Optional[int]:
        if not self._validate_second_save():
            return None

        vehicle_no = self.vehicle_no_var.get().strip()
        ticket = self.db.find_open_ticket(vehicle_no)

        if ticket is None:
            messagebox.showerror("Not Found", "No OPEN ticket found for this vehicle.")
            return None

        first_weight = self._safe_int(ticket["first_weight"])
        second_weight = self._safe_int(self.second_weight_var.get())

        net_weight = abs(first_weight - second_weight)

        now = datetime.now()

        second_date = now.strftime("%Y-%m-%d")
        second_time = now.strftime("%H:%M:%S")

        # ✅ FORCE UPDATE UI BEFORE SAVE
        self.first_weight_var.set(str(first_weight))
        self.second_weight_var.set(str(second_weight))
        self.net_weight_var.set(str(net_weight))

        self.db.update_ticket(
            ticket_id=ticket["id"],
            vehicle_no=vehicle_no,
            customer_name=self.customer_name_var.get().strip(),
            material_name=self.material_name_var.get().strip(),
            first_weight=first_weight,
            second_weight=second_weight,
            net_weight=net_weight,
            weight_type="Difference",
            payment_status=self.payment_status_var.get().strip(),
            paid_amount=self._safe_float(self.paid_amount_var.get()),
            remarks=self.remarks_var.get().strip(),

            ticket_date=ticket["ticket_date"],  # keep original
            ticket_time=ticket["ticket_time"],  # keep original

            status="COMPLETED"
        )

        self.current_loaded_ticket_id = ticket["id"]
        self.sr_no_var.set(ticket["sr_no"])

        self.status_var.set(f"2nd pass saved: {ticket['sr_no']}")
        self._load_recent_tickets()

        return ticket["id"]

    def save_current(self) -> Optional[int]:
        self._update_payment_status()
        self.calculate_net()

        if self.current_workflow == "FIRST":
            return self.save_first_pass()

        return self.save_second_pass()

    def save_and_print(self) -> None:
        """
        Save FIRST, then print from DB (secure)
        """

        ticket_id = self.save_current()

        if ticket_id is None:
            return

        ticket = self.db.find_ticket_by_id(ticket_id)

        if not ticket:
            messagebox.showerror("Error", "Failed to load saved ticket.")
            return

        payload = dict(ticket)

        filename = self.printer.print_ticket(payload)

        self.status_var.set(f"Printed: {ticket['sr_no']}")

    # =========================================================
    # PREVIEW / PRINT
    # =========================================================
    def preview_current_ticket(self) -> None:
        """
        Preview must ALWAYS save first (secure flow)
        """

        ticket_id = self.save_current()

        if ticket_id is None:
            return

        # reload from DB (single source of truth)
        ticket = self.db.find_ticket_by_id(ticket_id)

        if not ticket:
            messagebox.showerror("Error", "Failed to load saved ticket.")
            return

        payload = dict(ticket)

        self.printer.preview_ticket(self.root, payload)

        self.status_var.set(f"Preview (saved): {ticket['sr_no']}")

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
                    ticket["sr_no"],
                    ticket["vehicle_no"],
                    ticket["customer_name"],
                    ticket["first_weight"],
                    ticket["second_weight"],
                    ticket["net_weight"],
                    ticket["status"],
                    ticket["paid_amount"],
                    ticket["ticket_date"],
                )
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
                    ticket["sr_no"],
                    ticket["vehicle_no"],
                    ticket["customer_name"],
                    ticket["first_weight"],
                    ticket["second_weight"],
                    ticket["net_weight"],
                    ticket["status"],
                    ticket["paid_amount"],
                    ticket["ticket_date"],
                )
            )

        self.status_var.set("Found {0} result(s)".format(len(tickets)))

    def load_selected_ticket(self, event: tk.Event) -> None:
        selected = self.tree.selection()
        if not selected:
            return

        values = self.tree.item(selected[0], "values")
        if not values:
            return

        sr_no = values[0]
        ticket = self.db.find_ticket_by_sr_no(sr_no)
        if ticket is None:
            self.status_var.set("Ticket not found for loading.")
            return

        self.current_loaded_ticket_id = ticket["id"]
        self.current_loaded_ticket_sr_no = ticket["sr_no"]
        self.current_loaded_ticket_status = ticket["status"]

        self.sr_no_var.set(ticket["sr_no"])
        self.vehicle_no_var.set(ticket["vehicle_no"] or "")
        self.customer_name_var.set(ticket["customer_name"] or "")
        self.material_name_var.set(ticket["material_name"] or "")
        self.first_weight_var.set(str(ticket["first_weight"] or 0))
        self.second_weight_var.set(str(ticket["second_weight"] or 0))
        self.net_weight_var.set(str(abs((ticket["first_weight"] or 0) - (ticket["second_weight"] or 0))))
        self.paid_amount_var.set(str(ticket["paid_amount"] or "0"))
        self.remarks_var.set(ticket["remarks"] or "")
        self._update_payment_status()

        if ticket["status"] == "OPEN":
            self.select_second_pass()
        else:
            self.select_first_pass()

        self.status_var.set("Loaded ticket: {0}".format(ticket["sr_no"]))

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