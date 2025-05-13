import sqlite3
import logging
from datetime import datetime

# Database file path for thread persistence
DB_PATH = "conversation_threads.db"

# Initialize the database for thread persistence
def init_db():
    """Initialize the SQLite database with the necessary tables for thread persistence"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS conversation_threads (
        thread_key TEXT PRIMARY KEY,
        thread_id TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    conn.commit()
    conn.close()
    logging.info(f"Database initialized: {DB_PATH}")

# Load threads from database
def load_threads_from_db():
    """Load all conversation threads from the database into a dictionary"""
    threads = {}
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT thread_key, thread_id FROM conversation_threads')
    for row in cursor.fetchall():
        threads[row[0]] = row[1]
    conn.close()
    logging.info(f"Loaded {len(threads)} conversation threads from database")
    return threads

# Save thread to database
def save_thread_to_db(thread_key, thread_id):
    """Save a new thread to the database or update an existing one"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        'INSERT OR REPLACE INTO conversation_threads (thread_key, thread_id, last_used) VALUES (?, ?, datetime("now"))',
        (thread_key, thread_id)
    )
    conn.commit()
    conn.close()

# Update last used timestamp for a thread
def update_thread_timestamp(thread_key):
    """Update the last_used timestamp for a thread in the database"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        'UPDATE conversation_threads SET last_used = datetime("now") WHERE thread_key = ?',
        (thread_key,)
    )
    conn.commit()
    conn.close()

# Delete old threads from the database
def cleanup_old_threads(days=30):
    """Delete conversation threads that haven't been used for the specified number of days"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        'DELETE FROM conversation_threads WHERE last_used < datetime("now", ?)',
        (f'-{days} days',)
    )
    deleted_count = cursor.rowcount
    conn.commit()
    conn.close()
    logging.info(f"Cleaned up {deleted_count} old conversation threads")
    return deleted_count