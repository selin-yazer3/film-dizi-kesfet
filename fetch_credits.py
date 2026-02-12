"""
Fetch actor/director data from TMDB API for all movies and series.
Adds 'cast' and 'director' columns to the database.

Requires TMDB_API_KEY in .env
"""
import os
import time
import json
import sqlalchemy
from sqlalchemy import text
import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()

DB_URL = f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
TMDB_API_KEY = os.getenv("TMDB_API_KEY")
TMDB_BASE = "https://api.themoviedb.org/3"
CHECKPOINT_FILE = "credits_checkpoint.json"

if not TMDB_API_KEY:
    print("❌ TMDB_API_KEY not found in .env!")
    print("Get one free at: https://www.themoviedb.org/settings/api")
    exit(1)

engine = sqlalchemy.create_engine(DB_URL)

def load_checkpoint():
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE, 'r') as f:
            return json.load(f)
    return {"movies_done": [], "series_done": []}

def save_checkpoint(cp):
    with open(CHECKPOINT_FILE, 'w') as f:
        json.dump(cp, f)

def ensure_columns():
    """Add cast and director columns if they don't exist."""
    with engine.connect() as conn:
        for table in ['movies', 'series']:
            for col in ['cast_names', 'director']:
                try:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} TEXT"))
                except:
                    pass
        conn.commit()
    print("✅ Columns ensured")

def fetch_movie_credits(movie_id):
    """Fetch cast and director for a movie from TMDB."""
    url = f"{TMDB_BASE}/movie/{movie_id}/credits"
    params = {"api_key": TMDB_API_KEY, "language": "tr-TR"}
    try:
        r = requests.get(url, params=params, timeout=10)
        if r.status_code == 200:
            data = r.json()
            # Top 5 actors
            cast = [c['name'] for c in data.get('cast', [])[:5]]
            # Director
            directors = [c['name'] for c in data.get('crew', []) if c.get('job') == 'Director']
            return ", ".join(cast), ", ".join(directors)
        elif r.status_code == 429:
            time.sleep(2)
            return fetch_movie_credits(movie_id)
    except Exception as e:
        print(f"  Error for movie {movie_id}: {e}")
    return None, None

def fetch_series_credits(series_id):
    """Fetch cast and creator for a series from TMDB."""
    url = f"{TMDB_BASE}/tv/{series_id}/credits"
    params = {"api_key": TMDB_API_KEY, "language": "tr-TR"}
    try:
        r = requests.get(url, params=params, timeout=10)
        if r.status_code == 200:
            data = r.json()
            cast = [c['name'] for c in data.get('cast', [])[:5]]
            # For series, get created_by from the main endpoint
            r2 = requests.get(f"{TMDB_BASE}/tv/{series_id}", params=params, timeout=10)
            creators = []
            if r2.status_code == 200:
                creators = [c['name'] for c in r2.json().get('created_by', [])]
            return ", ".join(cast), ", ".join(creators)
        elif r.status_code == 429:
            time.sleep(2)
            return fetch_series_credits(series_id)
    except Exception as e:
        print(f"  Error for series {series_id}: {e}")
    return None, None

def process_movies():
    checkpoint = load_checkpoint()
    done_ids = set(checkpoint.get("movies_done", []))
    
    with engine.connect() as conn:
        df = pd.read_sql(text("SELECT id FROM movies WHERE cast_names IS NULL OR director IS NULL ORDER BY id"), conn)
    
    total = len(df)
    print(f"\n🎬 Processing {total} movies...")
    
    for i, row in df.iterrows():
        mid = int(row['id'])
        if mid in done_ids:
            continue
        
        cast, director = fetch_movie_credits(mid)
        
        if cast or director:
            with engine.connect() as conn:
                conn.execute(text(
                    "UPDATE movies SET cast_names = :cast, director = :dir WHERE id = :id"
                ), {"cast": cast or "", "dir": director or "", "id": mid})
                conn.commit()
        
        done_ids.add(mid)
        
        if len(done_ids) % 50 == 0:
            checkpoint["movies_done"] = list(done_ids)
            save_checkpoint(checkpoint)
            print(f"  Movies: {len(done_ids)}/{total}")
        
        time.sleep(0.05)  # Rate limiting: ~20 requests/sec
    
    checkpoint["movies_done"] = list(done_ids)
    save_checkpoint(checkpoint)
    print(f"✅ Movies done: {len(done_ids)}")

def process_series():
    checkpoint = load_checkpoint()
    done_ids = set(checkpoint.get("series_done", []))
    
    with engine.connect() as conn:
        df = pd.read_sql(text("SELECT id FROM series WHERE cast_names IS NULL OR director IS NULL ORDER BY id"), conn)
    
    total = len(df)
    print(f"\n📺 Processing {total} series...")
    
    for i, row in df.iterrows():
        sid = int(row['id'])
        if sid in done_ids:
            continue
        
        cast, creator = fetch_series_credits(sid)
        
        if cast or creator:
            with engine.connect() as conn:
                conn.execute(text(
                    "UPDATE series SET cast_names = :cast, director = :dir WHERE id = :id"
                ), {"cast": cast or "", "dir": creator or "", "id": sid})
                conn.commit()
        
        done_ids.add(sid)
        
        if len(done_ids) % 50 == 0:
            checkpoint["series_done"] = list(done_ids)
            save_checkpoint(checkpoint)
            print(f"  Series: {len(done_ids)}/{total}")
        
        time.sleep(0.05)
    
    checkpoint["series_done"] = list(done_ids)
    save_checkpoint(checkpoint)
    print(f"✅ Series done: {len(done_ids)}")

if __name__ == "__main__":
    print("🎬 TMDB Credits Fetcher")
    print("=" * 40)
    ensure_columns()
    process_movies()
    process_series()
    print("\n🎉 All done!")
