# src/client/ui.py

def welcome_script() -> str:
    return "welcome to BLACKIKACKY!"

def get_round_num() -> int:
    round_num_str = ''
    while not round_num_str.isdigit():
        round_num_str = input("Please enter the number of rounds: ")
    return int(round_num_str)

def ask_decision() -> str:
    """
    Returns "Hittt" or "Stand" (exactly as protocol expects).
    """
    while True:
        raw = input().strip().lower()
        if raw in ("hit", "h"):
            return "Hittt"
        if raw in ("stand", "s"):
            return "Stand"