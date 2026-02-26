import sqlite3
import datetime
from settings import DB_PATH

def get_connection():
    """Get database connection and ensure tables exist."""
    con = sqlite3.connect(DB_PATH)
    con.execute("""CREATE TABLE IF NOT EXISTS seen(
        feed TEXT, guid TEXT, url TEXT, published TEXT, seen_at TEXT,
        PRIMARY KEY(feed, guid)
    )""")
    con.execute("""CREATE TABLE IF NOT EXISTS feed_selections(
        feed_url TEXT PRIMARY KEY,
        last_selected_date TEXT,
        selection_count INTEGER DEFAULT 0
    )""")
    return con

def mark_seen(feed, guid, url, published):
    """Mark an entry as seen in the database."""
    con = get_connection()
    con.execute("INSERT OR IGNORE INTO seen(feed,guid,url,published,seen_at) VALUES(?,?,?,?,datetime('now'))",
                (feed, guid, url, published))
    con.commit()
    con.close()

def mark_unseen(feed):
    """Delete all seen records for a given feed."""
    con = get_connection()
    con.execute("DELETE FROM seen WHERE feed=?", (feed,))
    con.commit()
    con.close()

def already_seen(feed, guid):
    """Check if an entry was already seen."""
    con = get_connection()
    result = con.execute("SELECT 1 FROM seen WHERE feed=? AND guid=?", (feed, guid)).fetchone() is not None
    con.close()
    return result

def update_feed_selection(feed_url, selected_date=None):
    """Update the last selection date for a feed."""
    if selected_date is None:
        selected_date = datetime.date.today().isoformat()
    
    con = get_connection()
    con.execute("""
        INSERT OR REPLACE INTO feed_selections (feed_url, last_selected_date, selection_count)
        VALUES (?, ?, COALESCE((SELECT selection_count FROM feed_selections WHERE feed_url = ?), 0) + 1)
    """, (feed_url, selected_date, feed_url))
    con.commit()
    con.close()

def get_days_since_last_selection(feed_url):
    """Get number of days since this feed was last selected. Returns None if never selected."""
    con = get_connection()
    result = con.execute(
        "SELECT last_selected_date FROM feed_selections WHERE feed_url = ?", 
        (feed_url,)
    ).fetchone()
    con.close()
    
    if result is None:
        return None
        
    last_date = datetime.datetime.strptime(result[0], "%Y-%m-%d").date()
    today = datetime.date.today()
    return (today - last_date).days

def get_all_feed_selection_stats():
    """Get selection statistics for all feeds."""
    con = get_connection()
    results = con.execute("""
        SELECT feed_url, last_selected_date, selection_count,
               julianday('now') - julianday(last_selected_date) as days_since
        FROM feed_selections
        ORDER BY days_since DESC
    """).fetchall()
    con.close()
    
    stats = []
    for row in results:
        stats.append({
            'feed_url': row[0],
            'last_selected_date': row[1], 
            'selection_count': row[2],
            'days_since': int(row[3]) if row[3] is not None else None
        })
    return stats