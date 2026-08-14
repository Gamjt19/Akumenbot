"""
Root entry point for hosting environments (like KataBump) that expect `python main.py`.

Delegates execution directly to `bot.main.main()` without duplicating application logic.
"""

from bot.main import main

if __name__ == "__main__":
    main()
