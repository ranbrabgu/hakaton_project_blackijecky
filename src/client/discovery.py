# src/client/discovery.py

import socket
from typing import Tuple

from src.common.constants import UDP_DISCOVERY_PORT
from src.common.protocol import parse_offer, Offer, ProtocolError
from src.common.logging_utils import get_logger, log_packet

log = get_logger("client.discovery")


def listen_for_offer(timeout_sec: float = 5.0) -> Tuple[Offer, Tuple[str, int]]:
    """
    Listen on UDP 13122 for an OFFER packet.
    Returns: (Offer, (server_ip, server_udp_port))
    Raises TimeoutError if none received within timeout_sec.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("", UDP_DISCOVERY_PORT))
        s.settimeout(timeout_sec)

        while True:
            try:
                data, addr = s.recvfrom(4096)
                log_packet(log, "IN", "UDP", addr, data, note="datagram received")

                try:
                    offer = parse_offer(data)
                    log_packet(
                        log,
                        "IN",
                        "UDP",
                        addr,
                        data,
                        parsed=offer,
                        note="valid offer",
                    )
                    return offer, addr
                except ProtocolError as e:
                    log_packet(
                        log,
                        "IN",
                        "UDP",
                        addr,
                        data,
                        note=f"rejected offer: {e}",
                    )
                    # keep listening

            except socket.timeout:
                raise TimeoutError(f"No offer received within {timeout_sec} seconds")