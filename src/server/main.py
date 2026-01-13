# src/server/main.py
import socket
import threading
from src.common.logging_utils import setup_logging, get_logger
from src.server.broadcaster import broadcast_offers

log = get_logger("server.main")


def _create_tcp_listener() -> socket.socket:
    """
    Create a TCP listening socket on an ephemeral port (port 0).
    We only need the port now so we can broadcast it in offers.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("", 0))          # 0 = choose any free port
    s.listen()
    return s


def main() -> None:
    setup_logging()

    server_name = "BlackijeckyServer"  # change later / read from args
    stop_event = threading.Event()

    tcp_listener = _create_tcp_listener()
    tcp_port = tcp_listener.getsockname()[1]
    log.info(f"TCP listening on port {tcp_port}")

    t = threading.Thread(
        target=broadcast_offers,
        args=(server_name, tcp_port, stop_event),
        daemon=True,
    )
    t.start()

    log.info("Broadcasting offers. Press Ctrl+C to stop.")

    try:
        # For now: just keep the server alive.
        # Later: accept TCP clients and run sessions here.
        while True:
            tcp_listener.accept()[0].close()  # placeholder: immediately close
    except KeyboardInterrupt:
        log.info("Shutting down...")
    finally:
        stop_event.set()
        tcp_listener.close()


if __name__ == "__main__":
    main()