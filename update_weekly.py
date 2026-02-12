"""
Haftalık güncelleme scripti: Son 7 günde eklenen/güncellenen film ve dizileri çeker.
Yeni içerikleri DB'ye ekler ve embedding'lerini üretir.

Kullanım:
  python update_weekly.py

Otomatik zamanlamak için:
  Windows Task Scheduler veya cron ile haftada bir çalıştırın.
"""
import os
import requests
import pandas as pd
import sqlalchemy
from sqlalchemy import text
import ast
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("TMDB_API_KEY")
DB_URL = f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
BASE_URL = "https://api.themoviedb.org/3"

def fetch_new_content(content_type, since_date):
    """Fetch recently released movies or TV shows from TMDB."""
    results = []
    page = 1
    endpoint = "discover/movie" if content_type == "movie" else "discover/tv"
    date_field = "primary_release_date" if content_type == "movie" else "first_air_date"
    
    while page <= 50:  # Max 1000 items per update
        params = {
            "api_key": API_KEY,
            "language": "tr-TR",
            "sort_by": "popularity.desc",
            f"{date_field}.gte": since_date,
            "vote_count.gte": 5,  # At least 5 votes to filter junk
            "page": page
        }
        
        try:
            response = requests.get(f"{BASE_URL}/{endpoint}", params=params)
            response.raise_for_status()
            data = response.json()
            
            items = data.get("results", [])
            if not items:
                break
            
            results.extend(items)
            total_pages = data.get("total_pages", 1)
            
            if page >= total_pages:
                break
            
            page += 1
            time.sleep(0.12)
            
        except Exception as e:
            print(f"  Error page {page}: {e}")
            time.sleep(2)
            continue
    
    return results

def fetch_credits_for_id(content_type, tmdb_id):
    """Fetch cast and director for a single item."""
    endpoint = f"{content_type}/{tmdb_id}/credits"
    try:
        resp = requests.get(f"{BASE_URL}/{endpoint}", params={"api_key": API_KEY, "language": "tr-TR"})
        resp.raise_for_status()
        data = resp.json()
        
        cast = [c["name"] for c in data.get("cast", [])[:5]]
        cast_str = ", ".join(cast) if cast else None
        
        crew = data.get("crew", [])
        directors = [c["name"] for c in crew if c.get("job") == "Director"]
        if not directors:
            directors = [c["name"] for c in crew if c.get("department") == "Directing"][:1]
        director_str = directors[0] if directors else None
        
        return cast_str, director_str
    except:
        return None, None

def insert_movies(engine, items, existing_ids):
    """Insert new movies into the database."""
    new_items = [item for item in items if item.get("id") not in existing_ids]
    if not new_items:
        return 0
    
    with engine.connect() as conn:
        valid_genres = set(r[0] for r in conn.execute(text("SELECT id FROM genres")).fetchall())
        
        count = 0
        for item in new_items:
            try:
                # Fetch credits
                cast_str, director_str = fetch_credits_for_id("movie", item["id"])
                time.sleep(0.12)
                
                conn.execute(text("""
                    INSERT INTO movies (id, title, overview, release_date, vote_average,
                                       vote_count, popularity, poster_path, backdrop_path, 
                                       original_language, cast_names, director)
                    VALUES (:id, :title, :overview, :release_date, :vote_average,
                            :vote_count, :popularity, :poster_path, :backdrop_path,
                            :original_language, :cast_names, :director)
                    ON CONFLICT (id) DO UPDATE SET
                        vote_average = EXCLUDED.vote_average,
                        vote_count = EXCLUDED.vote_count,
                        popularity = EXCLUDED.popularity
                """), {
                    "id": item["id"], "title": item.get("title"),
                    "overview": item.get("overview"), "release_date": item.get("release_date"),
                    "vote_average": item.get("vote_average"), "vote_count": item.get("vote_count"),
                    "popularity": item.get("popularity"), "poster_path": item.get("poster_path"),
                    "backdrop_path": item.get("backdrop_path"),
                    "original_language": item.get("original_language"),
                    "cast_names": cast_str, "director": director_str
                })
                
                # Genre relations
                for gid in item.get("genre_ids", []):
                    if gid in valid_genres:
                        try:
                            conn.execute(text("""
                                INSERT INTO movie_genres (movie_id, genre_id)
                                VALUES (:mid, :gid) ON CONFLICT DO NOTHING
                            """), {"mid": item["id"], "gid": gid})
                        except:
                            pass
                
                count += 1
                if count % 25 == 0:
                    print(f"  Film: {count}/{len(new_items)}")
                    
            except Exception as e:
                continue
        
        conn.commit()
    return count

def insert_series(engine, items, existing_ids):
    """Insert new series into the database."""
    new_items = [item for item in items if item.get("id") not in existing_ids]
    if not new_items:
        return 0
    
    with engine.connect() as conn:
        valid_genres = set(r[0] for r in conn.execute(text("SELECT id FROM genres")).fetchall())
        
        count = 0
        for item in new_items:
            try:
                cast_str, director_str = fetch_credits_for_id("tv", item["id"])
                time.sleep(0.12)
                
                conn.execute(text("""
                    INSERT INTO series (id, name, overview, first_air_date, vote_average,
                                       vote_count, popularity, poster_path, backdrop_path,
                                       original_language, cast_names, director)
                    VALUES (:id, :name, :overview, :first_air_date, :vote_average,
                            :vote_count, :popularity, :poster_path, :backdrop_path,
                            :original_language, :cast_names, :director)
                    ON CONFLICT (id) DO UPDATE SET
                        vote_average = EXCLUDED.vote_average,
                        vote_count = EXCLUDED.vote_count,
                        popularity = EXCLUDED.popularity
                """), {
                    "id": item["id"], "name": item.get("name"),
                    "overview": item.get("overview"), "first_air_date": item.get("first_air_date"),
                    "vote_average": item.get("vote_average"), "vote_count": item.get("vote_count"),
                    "popularity": item.get("popularity"), "poster_path": item.get("poster_path"),
                    "backdrop_path": item.get("backdrop_path"),
                    "original_language": item.get("original_language"),
                    "cast_names": cast_str, "director": director_str
                })
                
                for gid in item.get("genre_ids", []):
                    if gid in valid_genres:
                        try:
                            conn.execute(text("""
                                INSERT INTO series_genres (series_id, genre_id)
                                VALUES (:sid, :gid) ON CONFLICT DO NOTHING
                            """), {"sid": item["id"], "gid": gid})
                        except:
                            pass
                
                count += 1
                if count % 25 == 0:
                    print(f"  Dizi: {count}/{len(new_items)}")
                    
            except Exception as e:
                continue
        
        conn.commit()
    return count

def generate_embeddings_for_new(engine):
    """Generate embeddings for items that don't have one yet."""
    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
    except Exception as e:
        print(f"⚠️ Embedding model yüklenemedi: {e}")
        return 0
    
    count = 0
    
    # Movies without embeddings
    query = """
        SELECT m.*, STRING_AGG(DISTINCT g.name, ', ') as genre_names
        FROM movies m
        LEFT JOIN movie_genres mg ON m.id = mg.movie_id
        LEFT JOIN genres g ON mg.genre_id = g.id
        WHERE m.embedding IS NULL
        GROUP BY m.id ORDER BY m.id
    """
    df = pd.read_sql(query, engine)
    
    if len(df) > 0:
        print(f"  🎬 {len(df)} film embedding'i üretiliyor...")
        for _, row in df.iterrows():
            parts = []
            if pd.notna(row.get('title')): parts.append(str(row['title']))
            if pd.notna(row.get('genre_names')) and row.get('genre_names'): parts.append(str(row['genre_names']))
            if pd.notna(row.get('overview')): parts.append(str(row['overview']))
            if pd.notna(row.get('cast_names')) and row.get('cast_names'): parts.append("Oyuncular: " + str(row['cast_names']))
            if pd.notna(row.get('director')) and row.get('director'): parts.append("Yönetmen: " + str(row['director']))
            txt = " ".join(parts).strip()
            
            if txt:
                emb = model.encode(txt).tolist()
                emb_str = "[" + ",".join(map(str, emb)) + "]"
                with engine.connect() as conn:
                    conn.execute(text("""
                        UPDATE movies SET embedding = CAST(:emb AS vector), semantic_text = :txt WHERE id = :id
                    """), {"emb": emb_str, "txt": txt, "id": row['id']})
                    conn.commit()
                count += 1
    
    # Series without embeddings
    query = """
        SELECT s.*, STRING_AGG(DISTINCT g.name, ', ') as genre_names
        FROM series s
        LEFT JOIN series_genres sg ON s.id = sg.series_id
        LEFT JOIN genres g ON sg.genre_id = g.id
        WHERE s.embedding IS NULL
        GROUP BY s.id ORDER BY s.id
    """
    df = pd.read_sql(query, engine)
    
    if len(df) > 0:
        print(f"  📺 {len(df)} dizi embedding'i üretiliyor...")
        for _, row in df.iterrows():
            parts = []
            if pd.notna(row.get('name')): parts.append(str(row['name']))
            if pd.notna(row.get('genre_names')) and row.get('genre_names'): parts.append(str(row['genre_names']))
            if pd.notna(row.get('overview')): parts.append(str(row['overview']))
            if pd.notna(row.get('cast_names')) and row.get('cast_names'): parts.append("Oyuncular: " + str(row['cast_names']))
            if pd.notna(row.get('director')) and row.get('director'): parts.append("Yapımcı: " + str(row['director']))
            txt = " ".join(parts).strip()
            
            if txt:
                emb = model.encode(txt).tolist()
                emb_str = "[" + ",".join(map(str, emb)) + "]"
                with engine.connect() as conn:
                    conn.execute(text("""
                        UPDATE series SET embedding = CAST(:emb AS vector), semantic_text = :txt WHERE id = :id
                    """), {"emb": emb_str, "txt": txt, "id": row['id']})
                    conn.commit()
                count += 1
    
    return count

def main():
    print("=" * 60)
    print(f"🔄 Haftalık Güncelleme — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)
    
    engine = sqlalchemy.create_engine(DB_URL)
    
    # Date range: last 7 days
    since_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    print(f"📅 {since_date} tarihinden itibaren yeni içerikler aranıyor...\n")
    
    # Get existing IDs
    with engine.connect() as conn:
        movie_ids = set(r[0] for r in conn.execute(text("SELECT id FROM movies")).fetchall())
        series_ids = set(r[0] for r in conn.execute(text("SELECT id FROM series")).fetchall())
    print(f"Mevcut: {len(movie_ids)} film, {len(series_ids)} dizi")
    
    # Fetch new movies
    print("\n🎬 Yeni filmler aranıyor...")
    new_movies = fetch_new_content("movie", since_date)
    print(f"  TMDB'de {len(new_movies)} film bulundu")
    movie_count = insert_movies(engine, new_movies, movie_ids)
    print(f"  ✅ {movie_count} yeni film eklendi")
    
    # Fetch new series
    print("\n📺 Yeni diziler aranıyor...")
    new_series = fetch_new_content("tv", since_date)
    print(f"  TMDB'de {len(new_series)} dizi bulundu")
    series_count = insert_series(engine, new_series, series_ids)
    print(f"  ✅ {series_count} yeni dizi eklendi")
    
    # Generate embeddings for new items
    total_new = movie_count + series_count
    if total_new > 0:
        print(f"\n🧠 {total_new} yeni içerik için embedding üretiliyor...")
        emb_count = generate_embeddings_for_new(engine)
        print(f"  ✅ {emb_count} embedding üretildi")
    else:
        print("\n✨ Yeni içerik yok, her şey güncel!")
    
    # Final stats
    with engine.connect() as conn:
        m_total = conn.execute(text("SELECT COUNT(*) FROM movies")).scalar()
        s_total = conn.execute(text("SELECT COUNT(*) FROM series")).scalar()
        m_emb = conn.execute(text("SELECT COUNT(*) FROM movies WHERE embedding IS NOT NULL")).scalar()
        s_emb = conn.execute(text("SELECT COUNT(*) FROM series WHERE embedding IS NOT NULL")).scalar()
    
    print(f"\n{'=' * 60}")
    print(f"📊 Toplam: {m_total} film ({m_emb} embedded), {s_total} dizi ({s_emb} embedded)")
    print(f"{'=' * 60}")

if __name__ == "__main__":
    main()
