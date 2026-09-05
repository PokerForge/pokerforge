from config.paths import app_data_dir
from database.repository import PokerDatabase

DB_PATH = app_data_dir() / "sf_poker.db"

if __name__ == "__main__":
    db = PokerDatabase(DB_PATH)
    n = db.rebuild_hand_player_stats()
    print(f"Rebuilt {n} hands")
    db.close()
