import socket
import threading
import subprocess
import re
from typing import Optional, Tuple, List

from src.common.protocol import build_offer
from src.common.constants import UDP_DISCOVERY_PORT
from src.common.logging_utils import get_logger, log_packet

log = get_logger("server.broadcaster")


def _parse_ifconfig_ipv4() -> List[Tuple[str, str, str]]:
    """
    Returns list of (iface, ip, broadcast_ip) for IPv4 interfaces.
    Prefer the explicit 'broadcast X' from ifconfig when available.
    """
    out = subprocess.check_output(["ifconfig"], text=True)

    results: List[Tuple[str, str, str]] = []
    blocks = re.split(r"\n(?=[a-zA-Z0-9]+: )", out)

    for block in blocks:
        m_iface = re.match(r"^([a-zA-Z0-9]+):", block)
        if not m_iface:
            continue
        iface = m_iface.group(1)

        # inet <ip> netmask <hex> broadcast <bcast>
        m = re.search(
            r"inet\s+(\d+\.\d+\.\d+\.\d+)\s+netmask\s+(0x[0-9a-fA-F]+)(?:\s+broadcast\s+(\d+\.\d+\.\d+\.\d+))?",
            block
        )
        if not m:
            continue

        ip = m.group(1)
        bcast = m.group(3)

        # If ifconfig didn't give broadcast, skip (rare on macOS for real interfaces)
        if not bcast:
            continue

        results.append((iface, ip, bcast))

    return results


def _pick_primary_iface(ifaces: List[Tuple[str, str, str]]) -> Optional[Tuple[str, str, str]]:
    """
    Prefer en0 (Wi-Fi) if present, else first interface.
    """
    for iface, ip, bcast in ifaces:
        if iface == "en0":
            return (iface, ip, bcast)
    return ifaces[0] if ifaces else None


def broadcast_offers(server_name: str, tcp_port: int, stop_event: threading.Event) -> None:
    pkt = build_offer(tcp_port=tcp_port, server_name=server_name)

    try:
        ifaces = _parse_ifconfig_ipv4()
    except Exception as e:
        log.warning(f"Failed to read interfaces via ifconfig: {e}")
        ifaces = []

    chosen = _pick_primary_iface(ifaces)
    if not chosen:
        log.warning("No IPv4 interface with broadcast address found. Are you offline or IPv6-only?")
        return

    iface, iface_ip, bcast_ip = chosen
    dest = (bcast_ip, UDP_DISCOVERY_PORT)

    log.info(f"Broadcasting offers on {iface} ({iface_ip}) -> {bcast_ip}:{UDP_DISCOVERY_PORT}")

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        # Force macOS to use the correct interface/route
        s.bind((iface_ip, 0))

        while not stop_event.is_set():
            try:
                s.sendto(pkt, dest)
                log_packet(
                    logger=log,
                    direction="OUT",
                    transport="UDP",
                    addr=dest,
                    raw=pkt,
                    parsed={"iface": iface, "iface_ip": iface_ip, "tcp_port": tcp_port, "server_name": server_name},
                    note="offer broadcast (forced en0)",
                )
            except OSError as e:
                log.warning(f"Broadcast failed on {iface} ({iface_ip} -> {bcast_ip}): {e}")

            stop_event.wait(1.0)