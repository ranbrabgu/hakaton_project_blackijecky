# src/common/logging_utils.py

import logging
import os
from typing import Any, Optional, Tuple

# Environment switches:
#   LOG_LEVEL=DEBUG / INFO / WARNING / ERROR
#   LOG_HEX=1 to include hexdumps in logs
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_HEX = os.getenv("LOG_HEX", "0") == "1"


def setup_logging(level: str = LOG_LEVEL) -> None:
    """Call once at program start (client/main.py and server/main.py)."""
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s.%(msecs)03d [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def hexdump(data: bytes, max_len: int = 64) -> str:
    """Short hex dump: 'ab cd ef ...' limited to max_len bytes."""
    shown = data[:max_len]
    hex_part = " ".join(f"{b:02x}" for b in shown)
    if len(data) > max_len:
        hex_part += f" ... (+{len(data) - max_len} bytes)"
    return hex_part


def log_packet(
    logger: logging.Logger,
    direction: str,               # "IN" / "OUT"
    transport: str,               # "UDP" / "TCP"
    addr: Optional[Tuple[str, int]],
    raw: bytes,
    parsed: Optional[Any] = None,
    note: str = "",
    level: int = logging.DEBUG,
) -> None:
    """
    Unified packet log.
    addr: (ip, port) if known, else None.
    parsed: any parsed object (dataclass or dict) to print summary.
    """
    where = f"{addr[0]}:{addr[1]}" if addr else "-"
    base = f"[{transport}][{direction}] {where} len={len(raw)}"
    if note:
        base += f" | {note}"

    if parsed is not None:
        base += f" | parsed={parsed}"

    if LOG_HEX:
        base += f" | hex={hexdump(raw)}"

    logger.log(level, base)