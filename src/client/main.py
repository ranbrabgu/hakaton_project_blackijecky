# src/client/main.py

from src.common.logging_utils import setup_logging, get_logger
from src.client.discovery import listen_for_offer
import socket
from src.common.protocol import build_request
from src.common.logging_utils import log_packet

log = get_logger("client.main")


def main() -> None:
    setup_logging()
    log.info("Listening for offers...")

    try:
        offer, addr = listen_for_offer(timeout_sec=10.0)
    except TimeoutError as e:
        log.error(str(e))
        return


    server_ip, _server_udp_port = addr
    log.info(f"Found server '{offer.server_name}' at {server_ip}, TCP port {offer.tcp_port}")

    team_name = "RanTeam"   # later: from args/input
    rounds = 3              # later: from args/input

    req_bytes = build_request(rounds=rounds, team_name=team_name)

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(5.0)
        s.connect((server_ip, offer.tcp_port))
        log.info("Connected to server via TCP")

        s.sendall(req_bytes)
        log_packet(log, "OUT", "TCP", (server_ip, offer.tcp_port), req_bytes, note="request sent")

        # Temporary ack to confirm server parsed + responded
        ack = s.recv(64)
        log.info(f"Server ack: {ack!r}")


if __name__ == "__main__":
    main()