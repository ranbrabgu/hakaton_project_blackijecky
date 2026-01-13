# src/server/session.py  (NEW VERSION)

import socket
from typing import Tuple

from src.common.protocol import (
    parse_request,
    parse_payload_client,
    build_payload_server,
    ProtocolError,
)
from src.common.constants import (
    REQUEST_LEN,
    PAYLOAD_CLIENT_LEN,
    RESULT_NOT_OVER, RESULT_WIN, RESULT_LOSS, RESULT_TIE,
)
from src.common.cards import Deck, Card
from src.common.rules import hand_value, is_bust, dealer_should_hit
from src.common.logging_utils import get_logger, log_packet

log = get_logger("server.session")


def recv_exact(sock: socket.socket, n: int) -> bytes:
    chunks = []
    remaining = n
    while remaining > 0:
        data = sock.recv(remaining)
        if not data:
            raise ConnectionError("Client disconnected while receiving data")
        chunks.append(data)
        remaining -= len(data)
    return b"".join(chunks)


def _send_card(conn: socket.socket, addr: Tuple[str, int], result_code: int, card: Card, note: str) -> Card:
    msg = build_payload_server(result_code, card.rank, card.suit)
    conn.sendall(msg)
    log_packet(log, "OUT", "TCP", addr, msg, note=note)
    return card  # return the card we just sent (for last_sent_card tracking)


def play_one_round(conn: socket.socket, addr: Tuple[str, int], deck: Deck) -> int:
    """
    Plays exactly one round.
    Returns final result code: WIN/LOSS/TIE.
    """
    player = [deck.draw(), deck.draw()]
    dealer = [deck.draw(), deck.draw()]  # dealer[1] hidden until stand / bust / etc

    log.info(f"Initial hands: player={player} dealer_up={dealer[0]}")

    last_sent: Card | None = None

    # Send initial reveals: player2 + dealer upcard
    last_sent = _send_card(conn, addr, RESULT_NOT_OVER, player[0], "initial card reveal (player)")
    last_sent = _send_card(conn, addr, RESULT_NOT_OVER, player[1], "initial card reveal (player)")
    last_sent = _send_card(conn, addr, RESULT_NOT_OVER, dealer[0], "initial card reveal (dealer up)")

    # Player decision loop
    while True:
        raw_dec = recv_exact(conn, PAYLOAD_CLIENT_LEN)
        log_packet(log, "IN", "TCP", addr, raw_dec, note="client decision received")
        decision = parse_payload_client(raw_dec).decision

        if decision == "Hittt":
            c = deck.draw()
            player.append(c)
            last_sent = _send_card(conn, addr, RESULT_NOT_OVER, c, "player hit card")

            if is_bust(player):
                # Player bust -> LOSS immediately. Do NOT reveal dealer hidden card.
                # Final payload still needs a card field, so reuse the bust card (the last card sent).
                final = build_payload_server(RESULT_LOSS, last_sent.rank, last_sent.suit)
                conn.sendall(final)
                log_packet(log, "OUT", "TCP", addr, final, note=f"final result (player bust) pv={hand_value(player)}")
                return RESULT_LOSS

        elif decision == "Stand":
            break
        else:
            raise ProtocolError(f"Unknown decision: {decision}")

    # Dealer turn: reveal hidden first
    last_sent = _send_card(conn, addr, RESULT_NOT_OVER, dealer[1], "dealer reveal hidden")

    while dealer_should_hit(dealer):
        c = deck.draw()
        dealer.append(c)
        last_sent = _send_card(conn, addr, RESULT_NOT_OVER, c, "dealer hit card")

    pv = hand_value(player)
    dv = hand_value(dealer)

    if is_bust(dealer) or pv > dv:
        result = RESULT_WIN
    elif pv < dv:
        result = RESULT_LOSS
    else:
        result = RESULT_TIE

    # Final payload MUST include a card: we use the last card we actually sent
    final = build_payload_server(result, last_sent.rank, last_sent.suit)
    conn.sendall(final)
    log_packet(log, "OUT", "TCP", addr, final, note=f"final result pv={pv} dv={dv}")

    return result


def handle_client(conn: socket.socket, addr: tuple[str, int]) -> None:
    log.info(f"Client connected: {addr[0]}:{addr[1]}")
    try:
        raw = recv_exact(conn, REQUEST_LEN)
        log_packet(log, "IN", "TCP", addr, raw, note="request received")
        req = parse_request(raw)
        log.info(f"Parsed request: team='{req.team_name}', rounds={req.rounds}")

        deck = Deck()  # one deck per session (simple)

        # (3) Multiple rounds:
        for i in range(req.rounds):
            log.info(f"--- Round {i+1}/{req.rounds} ---")
            play_one_round(conn, addr, deck)

    except (ProtocolError, ConnectionError, OSError) as e:
        log.warning(f"Session error with {addr[0]}:{addr[1]}: {e}")
    finally:
        conn.close()
        log.info(f"Client disconnected: {addr[0]}:{addr[1]}")