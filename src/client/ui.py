# src/client/ui.py

def ask_decision() -> str:
    """
    Returns "Hittt" or "Stand" (exactly as protocol expects).
    """
    while True:
        raw = input("Hit or Stand? ").strip().lower()
        if raw in ("hit", "h"):
            return "Hittt"
        if raw in ("stand", "s"):
            return "Stand"
        print("Type 'hit' or 'stand' (or h/s).")