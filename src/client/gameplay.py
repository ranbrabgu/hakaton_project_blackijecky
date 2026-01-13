# src/client/gameplay.py

import socket
from typing import Tuple

from src.common.constants import PAYLOAD_CLIENT_LEN, PAYLOAD_SERVER_LEN
from src.common.protocol import (
    build_payload_client,
    parse_payload_server,
    ProtocolError,
    PayloadServer,
)
from src.common.logging_utils import get_logger, log_packet

log = get_logger("client.gameplay")


def recv_exact(sock: socket.socket, n: int) -> bytes:
    chunks = []
    remaining = n
    while remaining > 0:
        data = sock.recv(remaining)
        if not data:
            raise ConnectionError("Server disconnected while receiving data")
        chunks.append(data)
        remaining -= len(data)
    return b"".join(chunks)


def send_decision(sock: socket.socket, server_addr: Tuple[str, int], decision: str) -> None:
    raw = build_payload_client(decision)
    sock.sendall(raw)
    log_packet(log, "OUT", "TCP", server_addr, raw, note=f"decision={decision}")


def recv_server_payload(sock: socket.socket, server_addr: Tuple[str, int]) -> PayloadServer:
    raw = recv_exact(sock, PAYLOAD_SERVER_LEN)
    log_packet(log, "IN", "TCP", server_addr, raw, note="server payload received")
    try:
        return parse_payload_server(raw)
    except ProtocolError as e:
        raise ProtocolError(f"Bad server payload: {e}") from e