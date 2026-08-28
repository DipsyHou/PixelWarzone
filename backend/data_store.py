import os
import json
import logging
import sqlite3
from typing import Dict

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
DB_FILE = os.path.join(DATA_DIR, "pixel_warzone.db")

def _ensure_data_dir():
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)

class DataStore:
    """Singleton data store managing all persistent game data backed by SQLite."""

    def __init__(self):
        _ensure_data_dir()
        self.conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        self._init_db()
        
        self.users_db: Dict = {}
        self.sessions: Dict = {}
        self.user_rooms: Dict = {}
        self.rooms: Dict = {}
        
        self._load_from_db()

    def _init_db(self):
        with self.conn:
            self.conn.execute('''CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                data TEXT
            )''')
            self.conn.execute('''CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                data TEXT
            )''')
            self.conn.execute('''CREATE TABLE IF NOT EXISTS user_rooms (
                username TEXT PRIMARY KEY,
                room_id TEXT
            )''')
            self.conn.execute('''CREATE TABLE IF NOT EXISTS rooms (
                room_id TEXT PRIMARY KEY,
                data TEXT
            )''')

    def _load_from_db(self):
        cursor = self.conn.cursor()
        
        for row in cursor.execute("SELECT username, data FROM users"):
            self.users_db[row[0]] = json.loads(row[1])
            
        for row in cursor.execute("SELECT token, data FROM sessions"):
            self.sessions[row[0]] = json.loads(row[1])
            
        for row in cursor.execute("SELECT username, room_id FROM user_rooms"):
            self.user_rooms[row[0]] = row[1]

    def load_rooms(self):
        from room import Room
        cursor = self.conn.cursor()
        for row in cursor.execute("SELECT room_id, data FROM rooms"):
            self.rooms[row[0]] = Room.from_dict(json.loads(row[1]))

    def save_all(self):
        with self.conn:
            self.conn.execute("DELETE FROM users")
            self.conn.executemany(
                "INSERT INTO users (username, data) VALUES (?, ?)",
                [(k, json.dumps(v, ensure_ascii=False)) for k, v in self.users_db.items()]
            )
            
            self.conn.execute("DELETE FROM sessions")
            self.conn.executemany(
                "INSERT INTO sessions (token, data) VALUES (?, ?)",
                [(k, json.dumps(v, ensure_ascii=False)) for k, v in self.sessions.items()]
            )
            
            self.conn.execute("DELETE FROM user_rooms")
            self.conn.executemany(
                "INSERT INTO user_rooms (username, room_id) VALUES (?, ?)",
                [(k, v) for k, v in self.user_rooms.items()]
            )
            
            self.conn.execute("DELETE FROM rooms")
            self.conn.executemany(
                "INSERT INTO rooms (room_id, data) VALUES (?, ?)",
                [(k, json.dumps(v.to_dict(), ensure_ascii=False)) for k, v in self.rooms.items()]
            )

store = DataStore()
store.load_rooms()
