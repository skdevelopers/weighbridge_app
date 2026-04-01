import random
import re
from collections import deque
from typing import Optional, Tuple, List
import serial
import serial.tools.list_ports

import config


class SerialService:
    """
    Industrial-grade Serial Service for Weighbridge Systems

    Features:
    - Stable weight detection
    - Noise filtering
    - RS232 fault tolerance
    - Demo mode support
    - Low memory optimized
    """

    def __init__(self, port: str, baud_rate: int, timeout: int = 1, demo_mode: bool = False) -> None:
        self.port = port
        self.baud_rate = baud_rate
        self.timeout = timeout
        self.demo_mode = demo_mode

        self.connection: Optional[serial.Serial] = None

        # SAFE CONFIG FALLBACKS (NO CRASH EVER)
        self.window_size = getattr(config, "STABLE_WINDOW_SIZE", 5)
        self.tolerance = getattr(config, "STABLE_TOLERANCE", 3)
        self.min_stable = getattr(config, "STABLE_MIN_COUNT", 3)

        self.recent_weights: deque[int] = deque(maxlen=self.window_size)

    # =========================
    # CONNECTION MANAGEMENT
    # =========================
    def connect(self) -> Tuple[bool, str]:
        if self.demo_mode:
            return True, "Demo mode enabled"

        try:
            self.connection = serial.Serial(
                port=self.port,
                baudrate=self.baud_rate,
                timeout=self.timeout
            )
            return True, f"Connected to {self.port}"
        except Exception as exc:
            self.connection = None
            return False, f"Serial connection failed: {exc}"

    def disconnect(self) -> None:
        try:
            if self.connection and self.connection.is_open:
                self.connection.close()
        except Exception:
            pass
        finally:
            self.connection = None

    # =========================
    # PORT LIST
    # =========================
    @staticmethod
    def list_ports() -> List[str]:
        ports = []
        try:
            for port in serial.tools.list_ports.comports():
                ports.append(port.device)
        except Exception:
            pass
        return ports

    # =========================
    # PARSER
    # =========================
    @staticmethod
    def parse_weight(raw_line: str) -> int:
        if not raw_line:
            return 0

        cleaned = raw_line.strip().upper()

        # Prefer KG pattern
        kg_match = re.search(r'([+-]?\d+)\s*KG', cleaned)
        if kg_match:
            try:
                return abs(int(kg_match.group(1)))
            except ValueError:
                return 0

        # fallback numeric
        generic_match = re.search(r'([+-]?\d+)', cleaned)
        if generic_match:
            try:
                return abs(int(generic_match.group(1)))
            except ValueError:
                return 0

        return 0

    # =========================
    # READ WEIGHT
    # =========================
    def read_weight(self) -> int:
        if self.demo_mode:
            weight = random.randint(
                getattr(config, "DEMO_MIN_WEIGHT", 1000),
                getattr(config, "DEMO_MAX_WEIGHT", 30000)
            )
            self._push_weight(weight)
            return weight

        if not self.connection or not self.connection.is_open:
            return 0

        try:
            raw = self.connection.readline().decode(errors="ignore").strip()
            weight = self.parse_weight(raw)

            # FILTER BAD VALUES
            if weight <= 0:
                return 0

            self._push_weight(weight)
            return weight

        except Exception:
            return 0

    # =========================
    # INTERNAL BUFFER
    # =========================
    def _push_weight(self, weight: int) -> None:
        """
        Add weight with noise filtering
        """
        if not self.recent_weights:
            self.recent_weights.append(weight)
            return

        last = self.recent_weights[-1]

        # ignore sudden spikes (industrial noise)
        if abs(weight - last) > 5000:
            return

        self.recent_weights.append(weight)

    # =========================
    # STABILITY CHECK
    # =========================
    def is_stable(self) -> bool:
        if len(self.recent_weights) < self.min_stable:
            return False

        values = list(self.recent_weights)

        # reject if any zero
        if any(v == 0 for v in values):
            return False

        return max(values) - min(values) <= self.tolerance

    # =========================
    # STABLE WEIGHT
    # =========================
    def stable_weight(self) -> int:
        if not self.recent_weights:
            return 0

        values = list(self.recent_weights)

        # use median (better than average for noise)
        values.sort()
        mid = len(values) // 2
        return values[mid]