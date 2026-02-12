"""
Semantic Search: Local Embedding Generation Script
Generates embeddings using local SentenceTransformer model (all-MiniLM-L6-v2).
No API limits. Runs offline.

Dimension: 384
"""

import os
import json
import time
import sqlalchemy
import pandas as pd
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv
from typing import List, Dict, Optional

load_dotenv()

# Configuration
DB_URL = f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
BATCH_SIZE = 100  # Local model is fast, can handle larger batches
CHECKPOINT_FILE = "embedding_checkpoint_local.json"
MODEL_NAME = 'paraphrase-multilingual-MiniLM-L12-v2'

def get_engine():
    return sqlalchemy.create_engine(DB_URL)

def load_checkpoint() -> Dict:
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE, 'r') as f:
            return json.load(f)
    return {"movies_processed": 0, "series_processed": 0, "last_movie_id": None, "last_series_id": None}

def save_checkpoint(checkpoint: Dict):
    with open(CHECKPOINT_FILE, 'w') as f:
        json.dump(checkpoint, f, indent=2)

def build_semantic_text_movie(row) -> str:
    parts = []
    if pd.notna(row.get('title')): parts.append(str(row['title']))
    if pd.notna(row.get('genre_names')) and row.get('genre_names'): parts.append(str(row['genre_names']))
    if pd.notna(row.get('overview')): parts.append(str(row['overview']))
    if pd.notna(row.get('cast_names')) and row.get('cast_names'): parts.append("Oyuncular: " + str(row['cast_names']))
    if pd.notna(row.get('director')) and row.get('director'): parts.append("Yönetmen: " + str(row['director']))
    if pd.notna(row.get('keywords')): parts.append(str(row['keywords']))
    return " ".join(parts).strip()

def build_semantic_text_series(row) -> str:
    parts = []
    if pd.notna(row.get('name')): parts.append(str(row['name']))
    if pd.notna(row.get('genre_names')) and row.get('genre_names'): parts.append(str(row['genre_names']))
    if pd.notna(row.get('overview')): parts.append(str(row['overview']))
    if pd.notna(row.get('cast_names')) and row.get('cast_names'): parts.append("Oyuncular: " + str(row['cast_names']))
    if pd.notna(row.get('director')) and row.get('director'): parts.append("Yapımcı: " + str(row['director']))
    if pd.notna(row.get('keywords')): parts.append(str(row['keywords']))
    return " ".join(parts).strip()

def process_movies(engine, model, checkpoint):
    print("\n🎬 Processing Movies (Local)...")
    
    query = """
        SELECT m.*, STRING_AGG(DISTINCT g.name, ', ') as genre_names
        FROM movies m
        LEFT JOIN movie_genres mg ON m.id = mg.movie_id
        LEFT JOIN genres g ON mg.genre_id = g.id
        WHERE m.embedding IS NULL
        GROUP BY m.id
        ORDER BY m.id
    """
    if checkpoint['last_movie_id']:
        query = f"""
            SELECT m.*, STRING_AGG(DISTINCT g.name, ', ') as genre_names
            FROM movies m
            LEFT JOIN movie_genres mg ON m.id = mg.movie_id
            LEFT JOIN genres g ON mg.genre_id = g.id
            WHERE m.embedding IS NULL AND m.id > {checkpoint['last_movie_id']}
            GROUP BY m.id
            ORDER BY m.id
        """
    
    df = pd.read_sql(query, engine)
    total = len(df)
    
    if total == 0:
        print("✅ All movies done!")
        return

    print(f"Found {total} movies to process.")
    
    processed_count = 0
    
    for i in range(0, total, BATCH_SIZE):
        batch = df.iloc[i : i + BATCH_SIZE]
        texts = []
        valid_rows = []
        
        for _, row in batch.iterrows():
            text = build_semantic_text_movie(row)
            if text:
                texts.append(text)
                valid_rows.append(row)
        
        if not texts:
            continue
            
        # Generate embeddings locally
        try:
            embeddings = model.encode(texts).tolist() # Returns list of lists
            
            with engine.connect() as conn:
                for row, emb, txt in zip(valid_rows, embeddings, texts):
                    emb_str = "[" + ",".join(map(str, emb)) + "]"
                    conn.execute(
                        sqlalchemy.text("""
                            UPDATE movies 
                            SET embedding = CAST(:emb AS vector), semantic_text = :txt 
                            WHERE id = :id
                        """),
                        {"emb": emb_str, "txt": txt, "id": row['id']}
                    )
                conn.commit()
            
            processed_count += len(valid_rows)
            checkpoint['movies_processed'] += len(valid_rows)
            checkpoint['last_movie_id'] = int(valid_rows[-1]['id'])
            save_checkpoint(checkpoint)
            
            print(f"  [{processed_count}/{total}] Processed batch.")
            
        except Exception as e:
            print(f"  ❌ Batch error: {e}")

def process_series(engine, model, checkpoint):
    print("\n📺 Processing Series (Local)...")
    
    query = """
        SELECT s.*, STRING_AGG(DISTINCT g.name, ', ') as genre_names
        FROM series s
        LEFT JOIN series_genres sg ON s.id = sg.series_id
        LEFT JOIN genres g ON sg.genre_id = g.id
        WHERE s.embedding IS NULL
        GROUP BY s.id
        ORDER BY s.id
    """
    if checkpoint['last_series_id']:
        query = f"""
            SELECT s.*, STRING_AGG(DISTINCT g.name, ', ') as genre_names
            FROM series s
            LEFT JOIN series_genres sg ON s.id = sg.series_id
            LEFT JOIN genres g ON sg.genre_id = g.id
            WHERE s.embedding IS NULL AND s.id > {checkpoint['last_series_id']}
            GROUP BY s.id
            ORDER BY s.id
        """
    
    df = pd.read_sql(query, engine)
    total = len(df)
    
    if total == 0:
        print("✅ All series done!")
        return

    print(f"Found {total} series to process.")
    
    processed_count = 0
    
    for i in range(0, total, BATCH_SIZE):
        batch = df.iloc[i : i + BATCH_SIZE]
        texts = []
        valid_rows = []
        
        for _, row in batch.iterrows():
            text = build_semantic_text_series(row)
            if text:
                texts.append(text)
                valid_rows.append(row)
        
        if not texts:
            continue
            
        try:
            embeddings = model.encode(texts).tolist()
            
            with engine.connect() as conn:
                for row, emb, txt in zip(valid_rows, embeddings, texts):
                    emb_str = "[" + ",".join(map(str, emb)) + "]"
                    conn.execute(
                        sqlalchemy.text("""
                            UPDATE series 
                            SET embedding = CAST(:emb AS vector), semantic_text = :txt 
                            WHERE id = :id
                        """),
                        {"emb": emb_str, "txt": txt, "id": row['id']}
                    )
                conn.commit()
            
            processed_count += len(valid_rows)
            checkpoint['series_processed'] += len(valid_rows)
            checkpoint['last_series_id'] = int(valid_rows[-1]['id'])
            save_checkpoint(checkpoint)
            
            print(f"  [{processed_count}/{total}] Processed batch.")
            
        except Exception as e:
            print(f"  ❌ Batch error: {e}")


def main():
    print(f"Loading model {MODEL_NAME}...")
    model = SentenceTransformer(MODEL_NAME)
    print("Model loaded.")
    
    engine = get_engine()
    checkpoint = load_checkpoint()
    
    process_movies(engine, model, checkpoint)
    process_series(engine, model, checkpoint)
    
    print("\n✅ Done!")

if __name__ == "__main__":
    main()
