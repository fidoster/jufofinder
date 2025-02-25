import sqlite3
from datetime import datetime

def init_db():
    conn = sqlite3.connect("search_history.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS searches
                 (id INTEGER PRIMARY KEY, keywords TEXT, timestamp TEXT, results TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS cache
                 (id INTEGER PRIMARY KEY, keywords TEXT, article TEXT UNIQUE)''')  # Cache unique articles
    conn.commit()
    conn.close()

def save_search(keywords, results):
    conn = sqlite3.connect("search_history.db")
    c = conn.cursor()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    results_str = str(results)
    c.execute("INSERT INTO searches (keywords, timestamp, results) VALUES (?, ?, ?)",
              (keywords, timestamp, results_str))
    conn.commit()
    conn.close()

def get_history():
    conn = sqlite3.connect("search_history.db")
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT keywords, timestamp, results FROM searches ORDER BY timestamp DESC")
    history = [{"keywords": row["keywords"], 
                "timestamp": row["timestamp"], 
                "results": row["results"], 
                "count": len(eval(row["results"]))} for row in c.fetchall()]
    conn.close()
    return history

def delete_search(keywords):
    conn = sqlite3.connect("search_history.db")
    c = conn.cursor()
    c.execute("DELETE FROM searches WHERE keywords = ?", (keywords,))
    c.execute("DELETE FROM cache WHERE keywords = ?", (keywords,))  # Clear cache too
    conn.commit()
    conn.close()

def get_cached_results(keywords):
    conn = sqlite3.connect("search_history.db")
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT article FROM cache WHERE keywords = ?", (keywords,))
    cached = [eval(row["article"]) for row in c.fetchall()]
    conn.close()
    return cached

def cache_results(keywords, results):
    conn = sqlite3.connect("search_history.db")
    c = conn.cursor()
    for result in results:
        try:
            c.execute("INSERT OR IGNORE INTO cache (keywords, article) VALUES (?, ?)",
                      (keywords, str(result)))
        except sqlite3.IntegrityError:
            pass  # Skip duplicates
    conn.commit()
    conn.close()