import sqlite3
import time

def init_db():
    conn = sqlite3.connect('search_history.db')
    c = conn.cursor()
    # Create tables if they don't exist
    c.execute('''CREATE TABLE IF NOT EXISTS searches 
                 (keywords TEXT, timestamp TEXT, results TEXT, count INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS cache 
                 (keyword TEXT, results TEXT)''')  # Ensure 'keyword' and 'results' columns exist
    
    # Check if 'count' column exists in searches and add it if missing
    c.execute("PRAGMA table_info(searches)")
    columns = [col[1] for col in c.fetchall()]
    if 'count' not in columns:
        c.execute("ALTER TABLE searches ADD COLUMN count INTEGER")
        # Populate count for existing rows based on results length
        c.execute("SELECT keywords, timestamp, results FROM searches WHERE count IS NULL")
        for row in c.fetchall():
            keywords, timestamp, results = row
            count = len(eval(results)) if results else 0
            c.execute("UPDATE searches SET count = ? WHERE keywords = ? AND timestamp = ?", 
                      (count, keywords, timestamp))
    
    # Check if 'keyword' column exists in cache and add it if missing
    c.execute("PRAGMA table_info(cache)")
    columns = [col[1] for col in c.fetchall()]
    if 'keyword' not in columns:
        c.execute("ALTER TABLE cache ADD COLUMN keyword TEXT")
        # Populate keyword for existing rows (if any) - assuming results is unique or handle accordingly
        c.execute("SELECT rowid, results FROM cache WHERE keyword IS NULL")
        for row in c.fetchall():
            rowid, results = row
            # If results exist, try to extract a keyword (e.g., default to 'unknown' or parse if possible)
            # Here, we'll use a placeholder; modify if you have specific logic
            c.execute("UPDATE cache SET keyword = ? WHERE rowid = ?", 
                      ("unknown", rowid))
    
    # Check if 'results' column exists in cache and add it if missing
    if 'results' not in columns:
        c.execute("ALTER TABLE cache ADD COLUMN results TEXT")
        # Populate results for existing rows (if any) - assuming keyword is unique
        c.execute("SELECT keyword FROM cache WHERE results IS NULL")
        for row in c.fetchall():
            keyword = row[0]
            # If you have logic to populate results, add it here (e.g., default empty list)
            c.execute("UPDATE cache SET results = ? WHERE keyword = ?", 
                      (str([]), keyword))
    
    conn.commit()
    conn.close()

def save_search(keywords, results):
    conn = sqlite3.connect('search_history.db')
    c = conn.cursor()
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    count = len(results)
    c.execute("INSERT INTO searches (keywords, timestamp, results, count) VALUES (?, ?, ?, ?)", 
              (keywords, timestamp, str(results), count))
    conn.commit()
    conn.close()

def get_history():
    conn = sqlite3.connect('search_history.db')
    c = conn.cursor()
    c.execute("SELECT keywords, timestamp, count FROM searches ORDER BY timestamp DESC")
    searches = [{"keywords": row[0], "timestamp": row[1], "count": row[2], "results": None} for row in c.fetchall()]
    for search in searches:
        c.execute("SELECT results FROM searches WHERE keywords = ? AND timestamp = ?", 
                  (search["keywords"], search["timestamp"]))
        search["results"] = c.fetchone()[0]
    conn.close()
    return searches

def delete_search(keywords):
    conn = sqlite3.connect('search_history.db')
    c = conn.cursor()
    c.execute("DELETE FROM searches WHERE keywords = ?", (keywords,))
    conn.commit()
    conn.close()

def cache_results(keyword, results):
    conn = sqlite3.connect('search_history.db')
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO cache (keyword, results) VALUES (?, ?)", 
              (keyword, str(results)))
    conn.commit()
    conn.close()

def get_cached_results(keyword):
    conn = sqlite3.connect('search_history.db')
    c = conn.cursor()
    c.execute("SELECT results FROM cache WHERE keyword = ?", (keyword,))
    result = c.fetchone()
    conn.close()
    return eval(result[0]) if result else []

def delete_article_from_search(keywords, link):
    conn = sqlite3.connect('search_history.db')
    c = conn.cursor()
    c.execute("SELECT results FROM searches WHERE keywords = ?", (keywords,))
    result = c.fetchone()
    if result:
        results = eval(result[0])
        updated_results = [r for r in results if r["link"] != link]
        if len(updated_results) < len(results):
            c.execute("UPDATE searches SET results = ?, count = ? WHERE keywords = ?", 
                      (str(updated_results), len(updated_results), keywords))
            conn.commit()
            conn.close()
            return len(updated_results)
    conn.close()
    return None