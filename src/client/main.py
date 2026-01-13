# src/client/main.py

import socket
from src.common.protocol import build_request
from src.common.logging_utils import setup_logging, get_logger, log_packet
from src.common.constants import *
from src.common.cards import Card
from src.common.rules import *
from src.client.discovery import *
from src.client.gameplay import *
from src.client.ui import *


log = get_logger("client.main")


def main() -> None:
    setup_logging()
    print("Client started, listening for offer requests...")

    try:
        offers = collect_offers(window_sec=3.0)
        if not offers:
            print("No offers received, exiting.")
            return
        print("Available servers:")
        for i, (offer, (ip, _)) in enumerate(offers, start=1):
            print(f"{i}) {offer.server_name} ({ip}:{offer.tcp_port})")
        
        choice = int(input("Please choose a server: "))
        offer, (server_ip, _) = offers[choice - 1]

        print(f"Received offer from {server_ip}, attempting to connect...")
        server_addr = (server_ip, offer.tcp_port)

    except TimeoutError as e:
        log.error(str(e))
        return


    print(f"Received offer from {server_ip}, attempting to connect...")

    print(welcome_script())
    team_name = TEAMNAME    
    rounds = get_round_num()

    req_bytes = build_request(rounds=rounds, team_name=team_name)
    server_addr = (server_ip, offer.tcp_port)

    wins = losses = ties = 0
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(10.0)
        s.connect(server_addr)
        log.info("Connected to server via TCP")

        s.sendall(req_bytes)
        log_packet(log, "OUT", "TCP", server_addr, req_bytes, note="request sent")

        for r in range(rounds):
            log.info(f"===== ROUND {r+1}/{rounds} =====")

            # Receive 3 initial payloads: player, player, dealer up
            p1 = recv_server_payload(s, server_addr)
            p2 = recv_server_payload(s, server_addr)
            up = recv_server_payload(s, server_addr)

            player = [Card(p1.rank, p1.suit), Card(p2.rank, p2.suit)]
            dealer = [Card(up.rank, up.suit)]  # only upcard known initially

            log.info(f"Player: {p1.rank}{p1.suit}, {p2.rank}{p2.suit}  total={hand_value(player)}")
            log.info(f"Dealer up: {up.rank}{up.suit}")

            # Player turn
            while True:
                if is_bust(player):
                    # In our server flow, bust triggers server to reveal dealer hidden + final.
                    # We just consume until final shows up.
                    break

                decision = ask_decision()
                send_decision(s, server_addr, decision)

                if decision == "Hittt":
                    msg = recv_server_payload(s, server_addr)

                    # If server sends NOT_OVER, it's a new player card
                    if msg.result == RESULT_NOT_OVER:
                        c = Card(msg.rank, msg.suit)
                        player.append(c)
                        log.info(f"You drew: {c.rank}{c.suit}  total={hand_value(player)}")

                        # After a bust, server will send more packets (dealer hidden reveal + final),
                        # so we don't continue asking if we busted.
                        if is_bust(player):
                            log.info("You busted.")
                            # fall through to consume until final
                            break
                    else:
                        # In case server finalizes immediately (shouldn't for Hit, but safe)
                        final_result = msg.result
                        break

                elif decision == "Stand":
                    # Dealer phase: keep receiving until final
                    break

            # Dealer phase / consume until final result
            final_result = None
            while True:
                msg = recv_server_payload(s, server_addr)
                if msg.result == RESULT_NOT_OVER:
                    c = Card(msg.rank, msg.suit)
                    dealer.append(c)
                    log.info(f"Dealer shows/draws: {c.rank}{c.suit}")
                else:
                    final_result = msg.result
                    break

            # Print totals
            pv = hand_value(player)
            dv = hand_value(dealer)  # dealer list includes all revealed cards (up + hidden + hits)
            log.info(f"Final totals: Player={pv} Dealer={dv}")

            # Update stats
            if final_result == RESULT_WIN:
                wins += 1
                log.info("Result: WIN")
            elif final_result == RESULT_LOSS:
                losses += 1
                log.info("Result: LOSS")
            elif final_result == RESULT_TIE:
                ties += 1
                log.info("Result: TIE")
            else:
                log.info(f"Result: (unknown code {final_result})")

        log.info(f"===== MATCH OVER =====  W={wins} L={losses} T={ties}")



if __name__ == "__main__":
    main()