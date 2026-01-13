# src/common/protocol.py

import struct
from dataclasses import dataclass
from typing import Tuple, Literal, Union
from .logging_utils import get_logger
import logging


from .constants import (
    MAGIC_COOKIE,
    TYPE_OFFER, TYPE_REQUEST, TYPE_PAYLOAD,
    NAME_LEN, DECISION_LEN,
    OFFER_LEN, REQUEST_LEN, PAYLOAD_CLIENT_LEN, PAYLOAD_SERVER_LEN,
    VALID_DECISIONS, VALID_RESULTS,
    SUIT_TO_CODE, CODE_TO_SUIT,
)
_log = get_logger("protocol")

# -------------------------
# Errors
# -------------------------
class ProtocolError(ValueError):
    """Raised when a packet is malformed or invalid."""
    pass


def _require(condition: bool, msg: str) -> None:
    if not condition:
        _log.warning(f"ProtocolError: {msg}")
        raise ProtocolError(msg)


def _pack_fixed_name(name: str, length: int = NAME_LEN) -> bytes:
    raw = name.encode("utf-8", errors="ignore")
    raw = raw[:length]
    return raw.ljust(length, b"\x00")


def _unpack_fixed_name(raw: bytes) -> str:
    return raw.split(b"\x00", 1)[0].decode("utf-8", errors="replace")


def _validate_header(cookie: int, msg_type: int, expected_type: int) -> None:
    _require(cookie == MAGIC_COOKIE, "Bad magic cookie")
    _require(msg_type == expected_type, f"Bad message type: expected {expected_type:#x}, got {msg_type:#x}")


# -------------------------
# Dataclasses (optional but nice)
# -------------------------
@dataclass(frozen=True)
class Offer:
    tcp_port: int
    server_name: str


@dataclass(frozen=True)
class Request:
    rounds: int
    team_name: str


@dataclass(frozen=True)
class PayloadClient:
    decision: Literal["Hittt", "Stand"]


@dataclass(frozen=True)
class PayloadServer:
    result: int
    rank: int          # 1..13
    suit: Literal["H", "D", "C", "S"]


Payload = Union[PayloadClient, PayloadServer]


# -------------------------
# OFFER (UDP): cookie(4) type(1) tcp_port(2) name(32) = 39 bytes
# -------------------------
def build_offer(tcp_port: int, server_name: str) -> bytes:
    _require(0 <= tcp_port <= 65535, "tcp_port must be uint16")
    name_bytes = _pack_fixed_name(server_name, NAME_LEN)
    return struct.pack("!I B H 32s", MAGIC_COOKIE, TYPE_OFFER, tcp_port, name_bytes)


def parse_offer(data: bytes) -> Offer:
    _require(len(data) == OFFER_LEN, f"Invalid offer length: expected {OFFER_LEN}, got {len(data)}")
    cookie, msg_type, tcp_port, name_raw = struct.unpack("!I B H 32s", data)
    _validate_header(cookie, msg_type, TYPE_OFFER)
    return Offer(tcp_port=tcp_port, server_name=_unpack_fixed_name(name_raw))


# -------------------------
# REQUEST (TCP): cookie(4) type(1) rounds(1) name(32) = 38 bytes
# -------------------------
def build_request(rounds: int, team_name: str) -> bytes:
    _require(0 <= rounds <= 255, "rounds must be uint8")
    name_bytes = _pack_fixed_name(team_name, NAME_LEN)
    return struct.pack("!I B B 32s", MAGIC_COOKIE, TYPE_REQUEST, rounds, name_bytes)


def parse_request(data: bytes) -> Request:
    _require(len(data) == REQUEST_LEN, f"Invalid request length: expected {REQUEST_LEN}, got {len(data)}")
    cookie, msg_type, rounds, name_raw = struct.unpack("!I B B 32s", data)
    _validate_header(cookie, msg_type, TYPE_REQUEST)
    return Request(rounds=rounds, team_name=_unpack_fixed_name(name_raw))


# -------------------------
# PAYLOAD (TCP)
#
# Client -> Server: cookie(4) type(1) decision(5) = 10 bytes
# decision must be ASCII "Hittt" or "Stand"
# -------------------------
def build_payload_client(decision: str) -> bytes:
    _require(decision in VALID_DECISIONS, 'decision must be "Hittt" or "Stand"')
    decision_bytes = decision.encode("ascii")
    _require(len(decision_bytes) == DECISION_LEN, "decision must be exactly 5 bytes")
    return struct.pack("!I B 5s", MAGIC_COOKIE, TYPE_PAYLOAD, decision_bytes)


def parse_payload_client(data: bytes) -> PayloadClient:
    _require(len(data) == PAYLOAD_CLIENT_LEN, f"Invalid client payload length: expected {PAYLOAD_CLIENT_LEN}, got {len(data)}")
    cookie, msg_type, decision_raw = struct.unpack("!I B 5s", data)
    _validate_header(cookie, msg_type, TYPE_PAYLOAD)
    decision = decision_raw.decode("ascii", errors="replace")
    _require(decision in VALID_DECISIONS, "Invalid decision in payload")
    # Type narrowing:
    return PayloadClient(decision=decision)  # type: ignore[arg-type]


# -------------------------
# Server -> Client: cookie(4) type(1) result(1) card(3) = 9 bytes
# card(3): rank uint16 (1..13) + suit uint8 (0..3: HDCS)
# -------------------------
def build_payload_server(result: int, rank: int, suit: str) -> bytes:
    _require(result in VALID_RESULTS, "Invalid result code")
    _require(1 <= rank <= 13, "rank must be 1..13")
    _require(suit in SUIT_TO_CODE, 'suit must be one of "H","D","C","S"')
    suit_code = SUIT_TO_CODE[suit]
    card_bytes = struct.pack("!H B", rank, suit_code)  # 3 bytes
    return struct.pack("!I B B", MAGIC_COOKIE, TYPE_PAYLOAD, result) + card_bytes


def parse_payload_server(data: bytes) -> PayloadServer:
    _require(len(data) == PAYLOAD_SERVER_LEN, f"Invalid server payload length: expected {PAYLOAD_SERVER_LEN}, got {len(data)}")
    cookie, msg_type, result = struct.unpack("!I B B", data[:6])
    _validate_header(cookie, msg_type, TYPE_PAYLOAD)
    _require(result in VALID_RESULTS, "Invalid result code")

    rank, suit_code = struct.unpack("!H B", data[6:9])
    _require(1 <= rank <= 13, "Invalid rank in payload")
    _require(suit_code in CODE_TO_SUIT, "Invalid suit code in payload")

    suit = CODE_TO_SUIT[suit_code]
    return PayloadServer(result=result, rank=rank, suit=suit)  # type: ignore[arg-type]


# Optional: auto-detect payload direction by length
def parse_payload_auto(data: bytes) -> Tuple[Literal["client", "server"], Payload]:
    if len(data) == PAYLOAD_CLIENT_LEN:
        return "client", parse_payload_client(data)
    if len(data) == PAYLOAD_SERVER_LEN:
        return "server", parse_payload_server(data)
    raise ProtocolError(f"Unknown payload length: {len(data)}")