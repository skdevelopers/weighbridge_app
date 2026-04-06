import os
import tempfile
import webbrowser
from typing import Any, Dict
import tkinter as tk
import config


class PrinterService:
    def __init__(self) -> None:
        self.company_name = config.COMPANY_NAME
        self.company_address = getattr(
            config,
            "COMPANY_ADDRESS",
            "Sargodha Road Sadhar Bypass Al Shafi Ice Factory Faisalabad",
        )
        self.company_phone = config.COMPANY_PHONE
        self.footer_line = f"{config.AUTHOR_BRAND} | {config.AUTHOR_NAME} | {config.AUTHOR_CONTACT}"

        self.page_width_in = getattr(config, "PAGE_WIDTH_IN", 8.27)
        self.page_height_in = getattr(config, "PAGE_HEIGHT_IN", 5.84)

    def _value(self, payload: Dict[str, Any], key: str, default: Any = "") -> Any:
        value = payload.get(key, default)
        return default if value is None else value

    def _safe_int(self, value: Any) -> int:
        try:
            return abs(int(float(str(value).strip())))
        except Exception:
            return 0

    def _safe_float(self, value: Any) -> float:
        try:
            return float(str(value).strip())
        except Exception:
            return 0.0

    def _format_amount(self, value: Any) -> str:
        amount = self._safe_float(value)
        if amount.is_integer():
            return str(int(amount))
        return f"{amount:.2f}"

    def _format_weight(self, value: Any) -> str:
        weight = self._safe_int(value)
        return f"{weight} Kg" if weight > 0 else ""

    def _kg_to_maund_string(self, kg_value: Any) -> str:
        kg = self._safe_int(kg_value)
        if kg <= 0:
            return ""
        maunds = kg // 40
        remainder_kg = kg % 40
        return f"{maunds}-{remainder_kg}"

    def _escape(self, value: Any) -> str:
        text = str(value if value is not None else "")
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

    def _normalize_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        first_weight = self._safe_int(self._value(payload, "first_weight", 0))
        second_weight = self._safe_int(self._value(payload, "second_weight", 0))
        raw_net_weight = self._safe_int(self._value(payload, "net_weight", 0))
        has_second_pass = second_weight > 0

        if has_second_pass:
            net_weight = raw_net_weight if raw_net_weight > 0 else abs(first_weight - second_weight)
            maund_source_weight = net_weight
        else:
            net_weight = 0
            maund_source_weight = first_weight

        first_date = str(self._value(payload, "first_date", self._value(payload, "ticket_date", "")))
        first_time = str(self._value(payload, "first_time", self._value(payload, "ticket_time", "")))
        second_date = str(self._value(payload, "second_date", ""))
        second_time = str(self._value(payload, "second_time", ""))

        customer_name = str(self._value(payload, "customer_name", ""))
        material_name = str(self._value(payload, "material_name", ""))
        vehicle_no = str(self._value(payload, "vehicle_no", ""))
        sr_no = str(self._value(payload, "sr_no", ""))
        slip_no = str(self._value(payload, "slip_no", self._value(payload, "id", "")))
        remarks = str(self._value(payload, "remarks", ""))

        paid_amount = self._safe_float(self._value(payload, "paid_amount", 0))
        first_mode = str(self._value(payload, "first_mode", "WithOut Driver")) or "WithOut Driver"
        second_mode = str(self._value(payload, "second_mode", ""))
        if has_second_pass and not second_mode:
            second_mode = "WithOut Driver"

        description = material_name if material_name else remarks

        return {
            "customer_name": customer_name,
            "description": description,
            "vehicle_no": vehicle_no,
            "sr_no": sr_no,
            "slip_no": slip_no,
            "first_date": first_date,
            "first_time": first_time,
            "second_date": second_date if has_second_pass else "",
            "second_time": second_time if has_second_pass else "",
            "first_weight_text": self._format_weight(first_weight),
            "second_weight_text": self._format_weight(second_weight) if has_second_pass else "",
            "net_weight_text": self._format_weight(net_weight) if has_second_pass else "",
            "maunds_text": self._kg_to_maund_string(maund_source_weight),
            "paid_amount_text": self._format_amount(paid_amount),
            "first_mode": first_mode,
            "second_mode": second_mode if has_second_pass else "",
            "show_second_pass": has_second_pass,
        }

    def _build_html(self, payload: Dict[str, Any], auto_print: bool = False) -> str:
        data = self._normalize_payload(payload)
        print_script = "window.onload = function(){ window.print(); };" if auto_print else ""

        second_date_block = self._escape(data["second_date"]) if data["show_second_pass"] else ""
        second_time_block = self._escape(data["second_time"]) if data["show_second_pass"] else ""
        second_weight_block = self._escape(data["second_weight_text"]) if data["show_second_pass"] else ""
        second_mode_block = self._escape(data["second_mode"]) if data["show_second_pass"] else ""

        return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Weighbridge Ticket - {self._escape(data["sr_no"])}</title>
<style>
    @page {{
        size: {self.page_width_in}in {self.page_height_in}in;
        margin: 0.04in;
    }}

    html, body {{
        margin: 0;
        padding: 0;
        background: #dcdcdc;
        font-family: Arial, Helvetica, sans-serif;
    }}

    body {{
        width: 100%;
    }}

    .sheet {{
        width: calc({self.page_width_in}in - 0.08in);
        min-height: calc({self.page_height_in}in - 0.08in);
        margin: 0 auto;
        border: 1.2px solid #222;
        padding: 0.032in;
        box-sizing: border-box;
        background: #dcdcdc;
    }}

    .header {{
        text-align: center;
        line-height: 1.0;
        margin-bottom: 0.025in;
    }}

    .header .title {{
        font-size: 0.25in;
        font-weight: 900;
        letter-spacing: 0.01in;
    }}

    .header .sub {{
        font-size: 0.145in;
        font-weight: 700;
        margin-top: 0.01in;
    }}

    .header .phone {{
        font-size: 0.14in;
        font-weight: 700;
    }}

    .top-meta {{
        display: grid;
        grid-template-columns: 1fr 1.10in;
        gap: 0.025in;
        margin-bottom: 0.025in;
    }}

    .slip-box {{
        border: 1px solid #222;
        min-height: 0.27in;
        padding: 0.02in 0.05in;
        font-size: 0.145in;
        font-weight: 800;
        background: #dcdcdc;
        display: flex;
        align-items: center;
        justify-content: center;
    }}

    .customer-row {{
        display: grid;
        grid-template-columns: 1.38in 1fr;
        gap: 0.025in;
        margin-bottom: 0.025in;
    }}

    .label-box,
    .value-box,
    .small-head,
    .small-value,
    .weight-value,
    .weight-label,
    .thanks-box,
    .desc-box,
    .maund-box,
    .mini-box,
    .paid-box {{
        border: 1px solid #222;
        box-sizing: border-box;
        background: #dcdcdc;
    }}

    .label-box {{
        padding: 0.04in 0.07in;
        font-size: 0.145in;
        font-weight: 800;
        min-height: 0.31in;
        display: flex;
        align-items: center;
    }}

    .value-box {{
        padding: 0.04in 0.07in;
        font-size: 0.14in;
        min-height: 0.31in;
        display: flex;
        align-items: center;
    }}

    .main-grid {{
        display: grid;
        grid-template-columns: 64% 36%;
        gap: 0.025in;
        margin-bottom: 0.025in;
    }}

    .left-top {{
        border: 1.1px solid #222;
        border-radius: 0.16in;
        padding: 0.035in;
        background: #dcdcdc;
        min-height: 1.46in;
    }}

    .ticket-grid-head,
    .ticket-grid-values,
    .ticket-grid-values-2 {{
        display: grid;
        grid-template-columns: 20% 13% 31% 36%;
        gap: 0.025in;
        margin-bottom: 0.025in;
    }}

    .small-head {{
        text-align: center;
        font-size: 0.14in;
        font-weight: 800;
        padding: 0.035in 0.03in;
        min-height: 0.26in;
        display: flex;
        align-items: center;
        justify-content: center;
    }}

    .small-value {{
        font-size: 0.14in;
        padding: 0.04in 0.055in;
        min-height: 0.34in;
        display: flex;
        align-items: center;
        overflow: hidden;
        word-break: break-word;
    }}

    .right-weights {{
        display: grid;
        grid-template-rows: repeat(4, auto);
        gap: 0.025in;
    }}

    .weight-row {{
        display: grid;
        grid-template-columns: 1fr 1.43in;
    }}

    .weight-value {{
        min-height: 0.40in;
        display: flex;
        align-items: center;
        padding: 0 0.075in;
        font-size: 0.17in;
        font-weight: 700;
    }}

    .weight-label {{
        min-height: 0.40in;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 0.17in;
        font-weight: 800;
    }}

    .thanks-box {{
        min-height: 0.42in;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 0.15in;
        font-weight: 700;
    }}

    .bottom-grid {{
        display: grid;
        grid-template-columns: 64% 36%;
        gap: 0.025in;
        margin-bottom: 0.025in;
    }}

    .desc-maund {{
        display: grid;
        grid-template-columns: 62% 38%;
        gap: 0.025in;
    }}

    .desc-box, .maund-box {{
        min-height: 0.68in;
        padding: 0.045in 0.07in;
    }}

    .box-title {{
        font-size: 0.145in;
        font-weight: 800;
        margin-bottom: 0.025in;
    }}

    .box-value {{
        font-size: 0.14in;
    }}

    .paid-box {{
        min-height: 0.44in;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 0.19in;
        font-weight: 900;
    }}

    .kg-maund-row {{
        display: grid;
        grid-template-columns: 24% 1fr;
        gap: 0.025in;
        margin-top: 0.025in;
    }}

    .mini-box {{
        min-height: 0.34in;
        padding: 0.035in 0.075in;
        font-size: 0.145in;
        display: flex;
        align-items: center;
        box-sizing: border-box;
    }}

    .time-mode-row {{
        display: grid;
        grid-template-columns: 16% 35% 16% 33%;
        gap: 0.025in;
        margin-top: 0.025in;
    }}

    .time-label {{
        font-weight: 800;
    }}

    .foot {{
        text-align: center;
        font-size: 0.115in;
        margin-top: 0.025in;
    }}

    @media print {{
        html, body {{
            background: white;
        }}

        .sheet {{
            margin: 0 auto;
            background: white;
        }}
    }}
</style>
<script>
{print_script}
</script>
</head>
<body>
    <div class="sheet">
        <div class="header">
            <div class="title">{self._escape(self.company_name)}</div>
            <div class="sub">{self._escape(self.company_address)}</div>
            <div class="phone">{self._escape(self.company_phone)}</div>
        </div>

        <div class="top-meta">
            <div></div>
            <div class="slip-box">Slip No: {self._escape(data["slip_no"])}</div>
        </div>

        <div class="customer-row">
            <div class="label-box">Customer Name:</div>
            <div class="value-box">{self._escape(data["customer_name"])}</div>
        </div>

        <div class="main-grid">
            <div class="left-top">
                <div class="ticket-grid-head">
                    <div class="small-head">Vehicle #</div>
                    <div class="small-head">SR #</div>
                    <div class="small-head">Date</div>
                    <div class="small-head">Time</div>
                </div>

                <div class="ticket-grid-values">
                    <div class="small-value">{self._escape(data["vehicle_no"])}</div>
                    <div class="small-value">{self._escape(data["sr_no"])}</div>
                    <div class="small-value">{self._escape(data["first_date"])}</div>
                    <div class="small-value">{self._escape(data["first_time"])}</div>
                </div>

                <div class="ticket-grid-values-2">
                    <div class="small-value"></div>
                    <div class="small-value"></div>
                    <div class="small-value">{second_date_block}</div>
                    <div class="small-value">{second_time_block}</div>
                </div>
            </div>

            <div class="right-weights">
                <div class="weight-row">
                    <div class="weight-value">{self._escape(data["first_weight_text"])}</div>
                    <div class="weight-label">1st Weight</div>
                </div>

                <div class="weight-row">
                    <div class="weight-value">{second_weight_block}</div>
                    <div class="weight-label">2nd Weight</div>
                </div>

                <div class="weight-row">
                    <div class="weight-value">{self._escape(data["net_weight_text"])}</div>
                    <div class="weight-label">Net Weight</div>
                </div>

                <div class="thanks-box">Received with Thanks</div>
            </div>
        </div>

        <div class="bottom-grid">
            <div>
                <div class="desc-maund">
                    <div class="desc-box">
                        <div class="box-title">Description</div>
                        <div class="box-value">{self._escape(data["description"])}</div>
                    </div>

                    <div class="maund-box">
                        <div class="box-title">Mounds</div>
                        <div class="box-value">{self._escape(data["maunds_text"])}</div>
                    </div>
                </div>

                <div class="kg-maund-row">
                    <div class="mini-box">40 kg</div>
                    <div class="mini-box">{self._escape(data["maunds_text"])}</div>
                </div>

                <div class="time-mode-row">
                    <div class="mini-box time-label">1st Time</div>
                    <div class="mini-box">{self._escape(data["first_mode"])}</div>
                    <div class="mini-box time-label">2nd Time</div>
                    <div class="mini-box">{second_mode_block}</div>
                </div>
            </div>

            <div>
                <div class="paid-box">Rs {self._escape(data["paid_amount_text"])} Paid</div>
            </div>
        </div>

        <div class="foot">{self._escape(self.footer_line)}</div>
    </div>
</body>
</html>
"""

    def _write_html_file(self, html: str, prefix: str = "ticket_") -> str:
        fd, filepath = tempfile.mkstemp(prefix=prefix, suffix=".html")
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            file.write(html)
        return filepath

    def preview_ticket(self, root: tk.Tk, payload: Dict[str, Any]) -> str:
        html = self._build_html(payload, auto_print=False)
        filepath = self._write_html_file(html, prefix="ticket_preview_")
        webbrowser.open(f"file://{os.path.abspath(filepath)}")
        return filepath

    def print_ticket(self, payload: Dict[str, Any]) -> str:
        html = self._build_html(payload, auto_print=True)
        filepath = self._write_html_file(html, prefix="ticket_print_")
        webbrowser.open(f"file://{os.path.abspath(filepath)}")
        return filepath
