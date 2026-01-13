# src/client/main.py

from src.common.logging_utils import setup_logging, get_logger
from src.client.discovery import listen_for_offer

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

    # Next milestone (later): connect via TCP and send REQUEST.


if __name__ == "__main__":
    main()