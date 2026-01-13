# src/common/constants.py

MAGIC_COOKIE = 0xabcddcba

# Message types
TYPE_OFFER = 0x2
TYPE_REQUEST = 0x3
TYPE_PAYLOAD = 0x4

# Fixed sizes
NAME_LEN = 32
DECISION_LEN = 5

# Packet lengths (bytes)
OFFER_LEN = 4 + 1 + 2 + NAME_LEN     # 39
REQUEST_LEN = 4 + 1 + 1 + NAME_LEN   # 38
PAYLOAD_CLIENT_LEN = 4 + 1 + DECISION_LEN  # 10
PAYLOAD_SERVER_LEN = 4 + 1 + 1 + 3   # 9

# UDP discovery port (client listens here)
UDP_DISCOVERY_PORT = 13122

# Server payload round result codes
RESULT_NOT_OVER = 0x0
RESULT_TIE = 0x1
RESULT_LOSS = 0x2
RESULT_WIN = 0x3

VALID_RESULTS = {RESULT_NOT_OVER, RESULT_TIE, RESULT_LOSS, RESULT_WIN}

# Suit encoding: HDCS -> 0..3
SUIT_TO_CODE = {"H": 0, "D": 1, "C": 2, "S": 3}
CODE_TO_SUIT = {v: k for k, v in SUIT_TO_CODE.items()}

VALID_DECISIONS = {"Hittt", "Stand"}

TEAMNAME = "MITSY MITSY MREOW MEOW =^.^="