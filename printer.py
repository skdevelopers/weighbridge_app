import os
import subprocess
import webbrowser
from pathlib import Path
from typing import Dict, Any

import config


class PrinterService:
    """
    HTML-based industrial printing engine for weighbridge slips.

    Features:
    - HTML/CSS receipt rendering
    - Save HTML before preview/print
    - Silent print via Chrome when available
    - Browser fallback for older systems
    - Layout closely matching the physical weighbridge slip
    """

    def __init__(self) -> None:
        self.output_dir = Path(getattr(config, "PRINT_OUTPUT_DIR", "prints"))
        self.output_dir.mkdir(parents=True, exist_ok=True)

    # =========================================================
    # HELPERS
    # =========================================================
    @staticmethod
    def _safe(value: Any) -> str:
        return "" if value is None else str(value)

    @staticmethod
    def _safe_int(value: Any) -> int:
        try:
            return abs(int(str(value).strip()))
        except Exception:
            return 0

    def _maund(self, kg: Any) -> str:
        kg_int = self._safe_int(kg)
        return f"{kg_int // 40}-{kg_int % 40}"

    def _second_pass_exists(self, ticket: Dict[str, Any]) -> bool:
        second_weight = ticket.get("second_weight", 0)
        try:
            return abs(int(second_weight)) > 0
        except Exception:
            return False

    # =========================================================
    # HTML TEMPLATE
    # =========================================================
    def _build_html(self, t: Dict[str, Any]) -> str:
        second_exists = self._second_pass_exists(t)

        second_date = self._safe(t.get("second_date")) if second_exists else ""
        second_time = self._safe(t.get("second_time")) if second_exists else ""
        second_mode = self._safe(t.get("second_mode")) if second_exists else ""

        customer_name = self._safe(t.get("customer_name"))
        vehicle_no = self._safe(t.get("vehicle_no"))
        sr_no = self._safe(t.get("sr_no"))
        first_date = self._safe(t.get("ticket_date"))
        first_time = self._safe(t.get("ticket_time"))
        material_name = self._safe(t.get("material_name"))
        first_weight = self._safe(t.get("first_weight"))
        second_weight = self._safe(t.get("second_weight"))
        net_weight = self._safe(t.get("net_weight"))
        paid_amount = self._safe(t.get("paid_amount") or "0")
        first_mode = self._safe(t.get("first_mode") or "WithOut Driver")
        payment_status = self._safe(t.get("payment_status"))

        return f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Slip {sr_no}</title>

<style>
@page {{
    size: 8.27in 5.84in;
    margin: 0;
}}

* {{
    box-sizing: border-box;
}}

body {{
    margin: 0;
    padding: 0;
    font-family: Arial, Helvetica, sans-serif;
    background: #ffffff;
    color: #000000;
}}

.page {{
    width: 8.27in;
    height: 5.84in;
    display: flex;
    justify-content: center;
    align-items: center;
}}

.ticket {{
    width: 7.80in;
    min-height: 5.30in;
    border: 2px solid #000;
    padding: 8px 10px 6px 10px;
}}

.header {{
    text-align: center;
    line-height: 1.15;
    margin-bottom: 6px;
}}

.header .title {{
    font-size: 16px;
    font-weight: 700;
    letter-spacing: 0.2px;
}}

.header .subtitle {{
    font-size: 11px;
    font-weight: 700;
    margin-top: 2px;
}}

.customer-row {{
    display: flex;
    gap: 6px;
    margin-bottom: 6px;
}}

.customer-left,
.customer-right {{
    border: 1px solid #000;
    min-height: 36px;
    display: flex;
    align-items: center;
    padding: 0;
}}

.customer-left {{
    width: 66%;
}}

.customer-right {{
    width: 34%;
}}

.label-chip {{
    background: #d9d9d9;
    border-right: 1px solid #000;
    font-weight: 700;
    min-width: 150px;
    padding: 8px 10px;
    height: 100%;
    display: flex;
    align-items: center;
}}

.label-value {{
    padding: 8px 10px;
    flex: 1;
}}

.main-grid {{
    display: flex;
    gap: 8px;
}}

.left-panel {{
    width: 66%;
}}

.right-panel {{
    width: 34%;
}}

.block {{
    border: 1px solid #000;
    border-radius: 16px;
    padding: 8px;
    margin-bottom: 7px;
}}

.row {{
    display: flex;
    gap: 6px;
    align-items: stretch;
}}

.cell {{
    border: 1px solid #000;
    padding: 6px 8px;
    min-height: 34px;
    display: flex;
    align-items: center;
}}

.head-cell {{
    justify-content: center;
    font-weight: 700;
    background: #f7f7f7;
}}

.value-cell {{
    font-size: 12px;
}}

.w-vehicle {{ width: 19%; }}
.w-sr      {{ width: 13%; }}
.w-date    {{ width: 24%; }}
.w-time    {{ width: 24%; }}

.desc-row {{
    display: flex;
    gap: 6px;
    margin-bottom: 6px;
}}

.desc-box {{
    border: 1px solid #000;
    min-height: 60px;
    padding: 6px 8px;
}}

.desc-left {{
    width: 62%;
}}

.desc-right {{
    width: 38%;
}}

.desc-title {{
    font-weight: 700;
    margin-bottom: 4px;
}}

.small-row {{
    display: flex;
    gap: 6px;
    margin-bottom: 6px;
}}

.kg40 {{
    width: 25%;
    border: 1px solid #000;
    padding: 8px 10px;
    min-height: 40px;
    display: flex;
    align-items: center;
}}

.maund-box {{
    width: 75%;
    border: 1px solid #000;
    padding: 8px 10px;
    min-height: 40px;
    display: flex;
    align-items: center;
}}

.mode-row {{
    display: flex;
    gap: 6px;
}}

.mode-label,
.mode-value {{
    border: 1px solid #000;
    min-height: 40px;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 6px 8px;
}}

.mode-label {{
    width: 16%;
    font-weight: 700;
    background: #d9d9d9;
}}

.mode-value {{
    width: 34%;
}}

.weight-row {{
    display: flex;
    margin-bottom: 6px;
}}

.weight-value {{
    flex: 1;
    border: 1px solid #000;
    min-height: 45px;
    padding: 8px 10px;
    font-size: 16px;
    font-weight: 700;
    display: flex;
    align-items: center;
}}

.weight-label {{
    width: 120px;
    border: 1px solid #000;
    border-left: none;
    background: #d9d9d9;
    font-weight: 700;
    display: flex;
    align-items: center;
    justify-content: center;
    text-align: center;
    padding: 8px 6px;
}}

.thanks-box,
.paid-box {{
    border: 1px solid #000;
    min-height: 42px;
    display: flex;
    align-items: center;
    justify-content: center;
    text-align: center;
    margin-bottom: 6px;
    padding: 8px;
    font-weight: 700;
}}

.footer {{
    text-align: center;
    font-size: 10px;
    margin-top: 8px;
}}

.hidden-second {{
    visibility: hidden;
}}

.print-note {{
    display: none;
}}

@media screen {{
    body {{
        background: #f3f3f3;
    }}

    .page {{
        margin: 0 auto;
    }}
}}
</style>

<script>
window.onload = function() {{
    setTimeout(function() {{
        window.print();
    }}, 300);
}};
</script>

</head>

<body>
<div class="page">
    <div class="ticket">

        <div class="header">
            <div class="title">{config.COMPANY_NAME}</div>
            <div class="subtitle">{config.COMPANY_ADDRESS}</div>
            <div class="subtitle">{config.COMPANY_PHONE}</div>
        </div>

        <div class="customer-row">
            <div class="customer-left">
                <div class="label-chip">Customer Name:</div>
                <div class="label-value">{customer_name}</div>
            </div>
            <div class="customer-right"></div>
        </div>

        <div class="main-grid">

            <div class="left-panel">

                <div class="block">
                    <div class="row">
                        <div class="cell head-cell w-vehicle">Vehicle #</div>
                        <div class="cell head-cell w-sr">SR #</div>
                        <div class="cell head-cell w-date">Date</div>
                        <div class="cell head-cell w-time">Time</div>
                    </div>

                    <div class="row" style="margin-top: 4px;">
                        <div class="cell value-cell w-vehicle">{vehicle_no}</div>
                        <div class="cell value-cell w-sr">{sr_no}</div>
                        <div class="cell value-cell w-date">{first_date}</div>
                        <div class="cell value-cell w-time">{first_time}</div>
                    </div>

                    <div class="row" style="margin-top: 4px;">
                        <div class="cell value-cell w-vehicle {'hidden-second' if not second_exists else ''}"></div>
                        <div class="cell value-cell w-sr {'hidden-second' if not second_exists else ''}"></div>
                        <div class="cell value-cell w-date">{second_date}</div>
                        <div class="cell value-cell w-time">{second_time}</div>
                    </div>
                </div>

                <div class="desc-row">
                    <div class="desc-box desc-left">
                        <div class="desc-title">Description</div>
                        <div>{material_name}</div>
                    </div>
                    <div class="desc-box desc-right">
                        <div class="desc-title">Mounds</div>
                        <div>{self._maund(net_weight)}</div>
                    </div>
                </div>

                <div class="small-row">
                    <div class="kg40">40 kg</div>
                    <div class="maund-box">{self._maund(net_weight)}</div>
                </div>

                <div class="mode-row">
                    <div class="mode-label">1st Time</div>
                    <div class="mode-value">{first_mode}</div>
                    <div class="mode-label">2nd Time</div>
                    <div class="mode-value">{second_mode}</div>
                </div>

            </div>

            <div class="right-panel">

                <div class="weight-row">
                    <div class="weight-value">{first_weight} Kg</div>
                    <div class="weight-label">1st Weight</div>
                </div>

                <div class="weight-row">
                    <div class="weight-value">{second_weight if second_exists else ""}{" Kg" if second_exists else ""}</div>
                    <div class="weight-label">2nd Weight</div>
                </div>

                <div class="weight-row">
                    <div class="weight-value">{net_weight if second_exists else ""}{" Kg" if second_exists else ""}</div>
                    <div class="weight-label">Net Weight</div>
                </div>

                <div class="thanks-box">Received with Thanks</div>
                <div class="paid-box">Rs {paid_amount} Paid</div>

            </div>

        </div>

        <div class="footer">
            {config.AUTHOR_BRAND} | {config.AUTHOR_NAME} | {config.AUTHOR_CONTACT}
        </div>

    </div>
</div>
</body>
</html>
"""

    # =========================================================
    # SAVE
    # =========================================================
    def save_html(self, ticket: Dict[str, Any]) -> str:
        sr = ticket.get("sr_no") or "WB"
        file_path = self.output_dir / f"{sr}.html"

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(self._build_html(ticket))

        return str(file_path)

    # =========================================================
    # PREVIEW
    # =========================================================
    def preview_ticket(self, parent, ticket: Dict[str, Any]) -> None:
        path = self.save_html(ticket)
        webbrowser.open(path)

    # =========================================================
    # PRINT
    # =========================================================
    def print_ticket(self, ticket: Dict[str, Any]) -> str:
        path = self.save_html(ticket)

        try:
            chrome_paths = [
                r"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
                r"C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
            ]

            for chrome in chrome_paths:
                if os.path.exists(chrome):
                    subprocess.Popen([
                        chrome,
                        "--kiosk",
                        "--kiosk-printing",
                        path
                    ])
                    return path

            webbrowser.open(path)

        except Exception:
            webbrowser.open(path)

        return path