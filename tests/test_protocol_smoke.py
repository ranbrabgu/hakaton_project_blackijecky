from src.common.protocol import *
from src.common.constants import *

def test_offer_roundtrip():
    b = build_offer(5555, "MyServer")
    o = parse_offer(b)
    assert o.tcp_port == 5555
    assert o.server_name == "MyServer"

def test_request_roundtrip():
    b = build_request(7, "TeamX")
    r = parse_request(b)
    assert r.rounds == 7
    assert r.team_name == "TeamX"

def test_payload_client_roundtrip():
    b = build_payload_client("Hittt")
    p = parse_payload_client(b)
    assert p.decision == "Hittt"

def test_payload_server_roundtrip():
    b = build_payload_server(RESULT_WIN, 13, "S")
    p = parse_payload_server(b)
    assert p.result == RESULT_WIN
    assert p.rank == 13
    assert p.suit == "S"