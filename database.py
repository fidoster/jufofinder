import sqlite3
import time
import logging

# Configure logger
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

def init_db():
    conn = sqlite3.connect('search_history.db')
    c = conn.cursor()
    # Create tables if they don't exist
    c.execute('''CREATE TABLE IF NOT EXISTS searches 
                 (keywords TEXT, timestamp TEXT, results TEXT, count INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS cache 
                 (keyword TEXT, results TEXT)''')
    
    # Check if 'count' column exists in searches and add it if missing
    c.execute("PRAGMA table_info(searches)")
    columns = [col[1] for col in c.fetchall()]
    if 'count' not in columns:
        c.execute("ALTER TABLE searches ADD COLUMN count INTEGER")
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
        c.execute("SELECT rowid, results FROM cache WHERE keyword IS NULL")
        for row in c.fetchall():
            rowid, results = row
            c.execute("UPDATE cache SET keyword = ? WHERE rowid = ?", ("unknown", rowid))
    
    # Check if 'results' column exists in cache and add it if missing
    if 'results' not in columns:
        c.execute("ALTER TABLE cache ADD COLUMN results TEXT")
        c.execute("SELECT keyword FROM cache WHERE results IS NULL")
        for row in c.fetchall():
            keyword = row[0]
            c.execute("UPDATE cache SET results = ? WHERE keyword = ?", (str([]), keyword))
    
    conn.commit()
    conn.close()

def save_search(keywords, results):
    conn = sqlite3.connect('search_history.db')
    c = conn.cursor()
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    count = len(results)
    try:
        c.execute("INSERT INTO searches (keywords, timestamp, results, count) VALUES (?, ?, ?, ?)", 
                  (keywords, timestamp, str(results), count))
        conn.commit()
        logger.info(f"Search saved: {keywords}, count: {count}")
    except Exception as e:
        logger.error(f"Failed to save search: {e}")
        conn.rollback()
    finally:
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
    try:
        c.execute("DELETE FROM searches WHERE keywords = ?", (keywords,))
        conn.commit()
        logger.info(f"Search deleted: {keywords}")
    except Exception as e:
        logger.error(f"Failed to delete search: {e}")
        conn.rollback()
    finally:
        conn.close()

def cache_results(keyword, results):
    conn = sqlite3.connect('search_history.db')
    c = conn.cursor()
    try:
        c.execute("INSERT OR REPLACE INTO cache (keyword, results) VALUES (?, ?)", 
                  (keyword, str(results)))
        conn.commit()
        logger.info(f"Cache updated for keyword: {keyword}")
    except Exception as e:
        logger.error(f"Failed to cache results: {e}")
        conn.rollback()
    finally:
        conn.close()

def get_cached_results(keyword):
    conn = sqlite3.connect('search_history.db')
    c = conn.cursor()
    try:
        c.execute("SELECT results FROM cache WHERE keyword = ?", (keyword,))
        result = c.fetchone()
        return eval(result[0]) if result else []
    except Exception as e:
        logger.error(f"Error retrieving cached results: {e}")
        return []
    finally:
        conn.close()

def delete_article_from_search(keywords, link):
    conn = sqlite3.connect('search_history.db')
    c = conn.cursor()
    try:
        c.execute("SELECT results FROM searches WHERE keywords = ?", (keywords,))
        result = c.fetchone()
        if result:
            results = eval(result[0])
            updated_results = [r for r in results if r["link"] != link]
            if len(updated_results) < len(results):
                c.execute("UPDATE searches SET results = ?, count = ? WHERE keywords = ?", 
                          (str(updated_results), len(updated_results), keywords))
                conn.commit()
                logger.info(f"Article deleted from {keywords}, remaining count: {len(updated_results)}")
                return len(updated_results)
    except Exception as e:
        logger.error(f"Error deleting article: {e}")
        conn.rollback()
    finally:
        conn.close()
    return None