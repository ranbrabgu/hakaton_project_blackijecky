# src/client/discovery.py

import socket
import time
from typing import List, Tuple, Dict
from src.common.constants import UDP_DISCOVERY_PORT
from src.common.protocol import parse_offer, Offer, ProtocolError
from src.common.logging_utils import get_logger, log_packet

log = get_logger("client.discovery")


def collect_offers(window_sec: float = 3.0, max_offers: int = 20) -> List[Tuple[Offer, Tuple[str, int]]]:
    """
    Collect offers for a fixed time window. Returns list of (Offer, (ip, udp_src_port)).
    Deduplicates by (ip, offer.tcp_port, offer.server_name).
    """
    offers: Dict[Tuple[str, int, str], Tuple[Offer, Tuple[str, int]]] = {}

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("", UDP_DISCOVERY_PORT))
    s.settimeout(0.2)

    end = time.time() + window_sec

    try:
        while time.time() < end and len(offers) < max_offers:
            try:
                data, addr = s.recvfrom(2048)
            except socket.timeout:
                continue

            ip, src_port = addr
            try:
                offer = parse_offer(data)
            except ProtocolError:
                continue

            key = (ip, offer.tcp_port, offer.server_name)
            offers[key] = (offer, addr)

    finally:
        s.close()

    return list(offers.values())

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