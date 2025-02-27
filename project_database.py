import sqlite3
import json

DB_NAME = 'projects.db'

def init_projects_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS sections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            title TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(project_id) REFERENCES projects(id)
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            section_id INTEGER,
            article_data TEXT,
            added_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(section_id) REFERENCES sections(id)
        )
    ''')
    conn.commit()
    conn.close()

def get_connection():
    return sqlite3.connect(DB_NAME)

def add_project(title, description):
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT INTO projects (title, description) VALUES (?, ?)", (title, description))
    conn.commit()
    conn.close()

def get_all_projects():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT id, title, description, created_at FROM projects ORDER BY created_at DESC")
    projects = [{'id': row[0], 'title': row[1], 'description': row[2], 'created_at': row[3]} for row in c.fetchall()]
    conn.close()
    return projects

def get_project(project_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT id, title, description, created_at FROM projects WHERE id = ?", (project_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return {'id': row[0], 'title': row[1], 'description': row[2], 'created_at': row[3]}
    return None

def delete_project(project_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM articles WHERE section_id IN (SELECT id FROM sections WHERE project_id = ?)", (project_id,))
    c.execute("DELETE FROM sections WHERE project_id = ?", (project_id,))
    c.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    conn.commit()
    conn.close()

def add_section(project_id, title):
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT INTO sections (project_id, title) VALUES (?, ?)", (project_id, title))
    conn.commit()
    conn.close()

def get_sections(project_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT id, title, created_at FROM sections WHERE project_id = ? ORDER BY created_at", (project_id,))
    sections = [{'id': row[0], 'title': row[1], 'created_at': row[2]} for row in c.fetchall()]
    conn.close()
    return sections

def get_project_id_by_section(section_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT project_id FROM sections WHERE id = ?", (section_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def delete_section(section_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM articles WHERE section_id = ?", (section_id,))
    c.execute("DELETE FROM sections WHERE id = ?", (section_id,))
    conn.commit()
    conn.close()

def add_article(section_id, article_data):
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT INTO articles (section_id, article_data) VALUES (?, ?)", (section_id, json.dumps(article_data)))
    conn.commit()
    conn.close()

def add_search_block(section_id, keywords):
    from database import get_history
    history = get_history()
    search_block = None
    for s in history:
        if s["keywords"] == keywords:
            search_block = s
            break
    if not search_block:
        return False
    block_data = {
        "block_type": "search",
        "keywords": keywords,
        "results": search_block["results"]
    }
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT INTO articles (section_id, article_data) VALUES (?, ?)", (section_id, json.dumps(block_data)))
    conn.commit()
    conn.close()
    return True

def get_articles(section_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT id, article_data, added_at FROM articles WHERE section_id = ? ORDER BY added_at", (section_id,))
    articles = []
    for row in c.fetchall():
        article = json.loads(row[1])
        article['id'] = row[0]
        article['added_at'] = row[2]
        articles.append(article)
    conn.close()
    return articles

def delete_article(article_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM articles WHERE id = ?", (article_id,))
    conn.commit()
    conn.close()

# NEW: Delete an individual article from a search block.
def delete_article_from_block(block_id, article_index):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT article_data FROM articles WHERE id = ?", (block_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return False
    try:
        block_data = json.loads(row[0])
    except Exception:
        conn.close()
        return False
    if block_data.get("block_type") != "search" or "results" not in block_data:
        conn.close()
        return False
    # Parse the stored results. They might be stored as JSON.
    try:
        results = json.loads(block_data["results"])
    except Exception:
        try:
            import ast
            results = ast.literal_eval(block_data["results"])
        except Exception:
            conn.close()
            return False
    if article_index < 0 or article_index >= len(results):
        conn.close()
        return False
    # Remove the article at the specified index.
    results.pop(article_index)
    # Save updated results back to block_data as JSON string.
    block_data["results"] = json.dumps(results)
    c.execute("UPDATE articles SET article_data = ? WHERE id = ?", (json.dumps(block_data), block_id))
    conn.commit()
    conn.close()
    return True

# Initialize the projects database when this module is loaded.
init_projects_db()
