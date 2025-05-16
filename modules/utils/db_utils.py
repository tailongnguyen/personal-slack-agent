import sqlite3
import logging
from datetime import datetime
# Assuming THREAD_DATABASE_PATH is correctly defined in your config
# If not, you might need to adjust this import or definition
try:
    from ..config import THREAD_DATABASE_PATH
except ImportError:
    # Fallback if the config structure is different or not yet set up
    logging.warning("Could not import THREAD_DATABASE_PATH from ..config. Using default 'conversation_threads.db'.")
    THREAD_DATABASE_PATH = "conversation_threads.db"


# Database file path for thread persistence
DB_PATH = THREAD_DATABASE_PATH

# Initialize the database for thread persistence
def init_db():
    """Initialize the SQLite database with the necessary tables for thread persistence"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Create conversation_threads table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS conversation_threads (
        thread_key TEXT PRIMARY KEY,
        thread_id TEXT, -- OpenAI's thread_id
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    # Create thread_messages table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS thread_messages (
        message_id INTEGER PRIMARY KEY AUTOINCREMENT,
        thread_key TEXT NOT NULL,
        role TEXT NOT NULL, -- 'user' or 'assistant'
        content TEXT NOT NULL,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (thread_key) REFERENCES conversation_threads(thread_key) ON DELETE CASCADE
    )
    ''')
    conn.commit()
    conn.close()
    logging.info(f"Database initialized/verified: {DB_PATH}")

# Load threads from database
def load_threads_from_db():
    """Load all conversation threads from the database into a dictionary"""
    threads = {}
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT thread_key, thread_id FROM conversation_threads')
        for row in cursor.fetchall():
            threads[row[0]] = row[1]
    except sqlite3.Error as e:
        logging.error(f"Error loading threads from DB: {e}")
    finally:
        conn.close()
    logging.info(f"Loaded {len(threads)} conversation threads from database")
    return threads

# Save thread to database
def save_thread_to_db(thread_key, thread_id):
    """Save a new thread to the database or update an existing one's OpenAI thread_id"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute(
            'INSERT OR REPLACE INTO conversation_threads (thread_key, thread_id, last_used) VALUES (?, ?, datetime("now"))',
            (thread_key, thread_id)
        )
        conn.commit()
    except sqlite3.Error as e:
        logging.error(f"Error saving thread to DB: {e}")
    finally:
        conn.close()

# Update last used timestamp for a thread
def update_thread_timestamp(thread_key):
    """Update the last_used timestamp for a thread in the database"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute(
            'UPDATE conversation_threads SET last_used = datetime("now") WHERE thread_key = ?',
            (thread_key,)
        )
        conn.commit()
    except sqlite3.Error as e:
        logging.error(f"Error updating thread timestamp in DB: {e}")
    finally:
        conn.close()

# Add a message to a thread's history
def add_message_to_history(thread_key: str, role: str, content: str):
    """Adds a message to the specified thread's history in the database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO thread_messages (thread_key, role, content, timestamp) VALUES (?, ?, ?, datetime('now'))",
            (thread_key, role, content)
        )
        conn.commit()
        logging.debug(f"Message added to history for thread_key {thread_key}: Role={role}")
    except sqlite3.Error as e:
        logging.error(f"Error adding message to history for thread_key {thread_key}: {e}")
    finally:
        conn.close()

# Get conversation history for a thread from the database
def get_history_from_db(thread_key: str, limit: int = 20) -> list[dict]:
    """Retrieves conversation history for a given thread_key from the database, ordered by timestamp."""
    history = []
    conn = sqlite3.connect(DB_PATH)
    # Ensure rows are dictionaries
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    try:
        # Fetch the most recent 'limit' messages
        cursor.execute(
            "SELECT role, content, timestamp FROM thread_messages WHERE thread_key = ? ORDER BY timestamp DESC, message_id DESC LIMIT ?",
            (thread_key, limit)
        )
        # Convert rows to dict and reverse to get chronological order (oldest first)
        history = [dict(row) for row in cursor.fetchall()][::-1]
        logging.debug(f"Retrieved {len(history)} messages from history for thread_key {thread_key}")
    except sqlite3.Error as e:
        logging.error(f"Error retrieving history for thread_key {thread_key}: {e}")
    finally:
        conn.close()
    return history

# Delete old threads from the database
def cleanup_old_threads(days=30): # Defaulting to 30 days as in your original snippet
    """Delete conversation threads (and their messages due to CASCADE) 
       that haven't been used for the specified number of days."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    deleted_count = 0
    try:
        cursor.execute(
            'DELETE FROM conversation_threads WHERE last_used < datetime("now", ?)',
            (f'-{days} days',)
        )
        deleted_count = cursor.rowcount
        conn.commit()
    except sqlite3.Error as e:
        logging.error(f"Error cleaning up old threads: {e}")
    finally:
        conn.close()
    if deleted_count > 0:
        logging.info(f"Cleaned up {deleted_count} old conversation threads (and their messages).")
    return deleted_count