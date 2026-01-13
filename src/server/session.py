# src/server/session.py

import socket

from src.common.protocol import parse_request, ProtocolError
from src.common.constants import REQUEST_LEN
from src.common.logging_utils import get_logger, log_packet

log = get_logger("server.session")


def recv_exact(sock: socket.socket, n: int) -> bytes:
    """Receive exactly n bytes or raise ConnectionError."""
    chunks = []
    remaining = n
    while remaining > 0:
        data = sock.recv(remaining)
        if not data:
            raise ConnectionError("Client disconnected while receiving data")
        chunks.append(data)
        remaining -= len(data)
    return b"".join(chunks)


def handle_client(conn: socket.socket, addr: tuple[str, int]) -> None:
    """
    For now: receive a REQUEST packet and log it.
    Later: run blackjack rounds here.
    """
    log.info(f"Client connected: {addr[0]}:{addr[1]}")
    try:
        raw = recv_exact(conn, REQUEST_LEN)
        log_packet(log, "IN", "TCP", addr, raw, note="request received")

        req = parse_request(raw)
        log.info(f"Parsed request: team='{req.team_name}', rounds={req.rounds}")

        # Placeholder: keep connection alive briefly (or close immediately)
        # We'll replace this with gameplay loop next.
        conn.sendall(b"OK")  # temporary ack so client can confirm TCP works
    except (ProtocolError, ConnectionError, OSError) as e:
        log.warning(f"Session error with {addr[0]}:{addr[1]}: {e}")
    finally:
        conn.close()
        log.info(f"Client disconnected: {addr[0]}:{addr[1]}")