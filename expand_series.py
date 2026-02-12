"""
Dizi veritabanını genişlet: Birden fazla TMDB endpoint'inden dizi çekerek 5000+ diziye ulaş.
Mevcut dizileri bozmaz, sadece yeni dizileri ekler.
"""
import os
import requests
import pandas as pd
import sqlalchemy
from sqlalchemy import text
import ast
import time
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("TMDB_API_KEY")
DB_URL = f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"

BASE_URL = "https://api.themoviedb.org/3"

def fetch_series_from_endpoint(endpoint, max_pages=250):
    """Fetch series from a specific TMDB endpoint."""
    results = []
    page = 1
    
    while page <= max_pages:
        params = {
            "api_key": API_KEY,
            "language": "tr-TR",
            "page": page
        }
        
        try:
            response = requests.get(f"{BASE_URL}/{endpoint}", params=params)
            response.raise_for_status()
            data = response.json()
            
            items = data.get("results", [])
            if not items:
                break
            
            total_pages = data.get("total_pages", max_pages)
            max_pages = min(max_pages, total_pages)
            
            results.extend(items)
            
            if page % 50 == 0:
                print(f"  {endpoint}: Page {page}/{max_pages} — {len(results)} items")
            
            page += 1
            time.sleep(0.12)  # Rate limit
            
        except Exception as e:
            print(f"  Error on {endpoint} page {page}: {e}")
            time.sleep(2)
            continue
    
    return results

def save_batch(engine, items, existing_ids):
    """Save a batch of series to the database."""
    if not items:
        return 0
        
    new_items_list = [item for item in items if item.get("id") not in existing_ids]
    if not new_items_list:
        return 0
        
    df = pd.DataFrame(new_items_list)
    
    # Prepare columns
    columns = ['id', 'name', 'overview', 'first_air_date', 'vote_average', 
               'vote_count', 'popularity', 'poster_path', 'backdrop_path', 'original_language']
    
    for col in columns:
        if col not in df.columns:
            df[col] = None
            
    df_clean = df[columns].copy()
    df_clean.drop_duplicates(subset=['id'], inplace=True)
    df_clean.replace("", None, inplace=True)
    df_clean = df_clean.where(pd.notnull(df_clean), None)
    
    inserted_count = 0
    with engine.connect() as conn:
        # Insert Series
        for _, row in df_clean.iterrows():
            try:
                conn.execute(text("""
                    INSERT INTO series (id, name, overview, first_air_date, vote_average, 
                                       vote_count, popularity, poster_path, backdrop_path, original_language)
                    VALUES (:id, :name, :overview, :first_air_date, :vote_average,
                            :vote_count, :popularity, :poster_path, :backdrop_path, :original_language)
                    ON CONFLICT (id) DO NOTHING
                """), dict(row))
                inserted_count += 1
            except Exception as e:
                print(f"Error inserting series {row.get('id')}: {e}")
                continue
                
        # Insert Genres
        valid_genres = set(r[0] for r in conn.execute(text("SELECT id FROM genres")).fetchall())
        for item in new_items_list:
            sid = item.get("id")
            genre_ids = item.get("genre_ids", [])
            if isinstance(genre_ids, str):
                try: genre_ids = ast.literal_eval(genre_ids)
                except: genre_ids = []
            
            for gid in genre_ids:
                if gid in valid_genres:
                    try:
                        conn.execute(text("""
                            INSERT INTO series_genres (series_id, genre_id)
                            VALUES (:sid, :gid) ON CONFLICT DO NOTHING
                        """), {"sid": sid, "gid": gid})
                    except:
                        pass
        conn.commit()
        
    return inserted_count

def fetch_and_save(endpoint, engine, existing_ids, max_pages=250):
    """Fetch from endpoint and save immediately in chunks."""
    page = 1
    total_new = 0
    
    print(f"\n📺 Fetching: {endpoint}")
    
    while page <= max_pages:
        params = {
            "api_key": API_KEY,
            "language": "tr-TR",
            "page": page
        }
        
        try:
            response = requests.get(f"{BASE_URL}/{endpoint}", params=params)
            response.raise_for_status()
            data = response.json()
            
            items = data.get("results", [])
            if not items:
                break
                
            # Update max_pages based on API response
            total_pages = data.get("total_pages", max_pages)
            max_pages = min(max_pages, total_pages)
            
            # Save this chunk immediately
            count = save_batch(engine, items, existing_ids)
            if count > 0:
                total_new += count
                # Add new IDs to existing set so we don't try to insert them again
                for item in items:
                    existing_ids.add(item.get("id"))
            
            if page % 10 == 0:
                print(f"  Page {page}/{max_pages} — {count} saved (Total new: {total_new})")
            
            page += 1
            time.sleep(0.12)
            
        except Exception as e:
            print(f"  Error on {endpoint} page {page}: {e}")
            time.sleep(2)
            # Don't break, try next page
            page += 1
            continue
            
    return total_new

def main():
    engine = sqlalchemy.create_engine(DB_URL)
    
    # Get initial existing IDs
    with engine.connect() as conn:
        existing = conn.execute(text("SELECT id FROM series")).fetchall()
    existing_ids = set(r[0] for r in existing)
    print(f"Mevcut dizi sayısı: {len(existing_ids)}")
    
    endpoints = [
        ("tv/top_rated", 250),
        ("tv/popular", 250),
        ("discover/tv", 250),
    ]
    
    total_added = 0
    for endpoint, pages in endpoints:
        added = fetch_and_save(endpoint, engine, existing_ids, pages)
        total_added += added
        
    print(f"\n✅ İşlem tamamlandı! Toplam {total_added} yeni dizi eklendi.")
    
    # Final count
    with engine.connect() as conn:
        final_count = conn.execute(text("SELECT COUNT(*) FROM series")).scalar()
    print(f"📊 Veritabanındaki güncel dizi sayısı: {final_count}")

if __name__ == "__main__":
    main()
