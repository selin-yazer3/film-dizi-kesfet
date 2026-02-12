import os
import pandas as pd
import sqlalchemy
from sqlalchemy import text
import ast
import traceback
from dotenv import load_dotenv

# Load config
load_dotenv()

DB_URL = f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"

import sys

# ... (imports)

def import_data():
    engine = sqlalchemy.create_engine(DB_URL)
    
    # Clean existing data
    # print("Cleaning existing data...", flush=True)
    # with engine.begin() as conn:
    #    conn.execute(text("TRUNCATE TABLE movie_genres, series_genres, movies, series, genres CASCADE;"))
    # print("Data cleaned.", flush=True)

    # Load Genres first to use for validation
    df_genres = pd.read_csv("genres.csv")
    valid_genre_ids = set(df_genres['id'].tolist())
    
    # Import Genres
    print("Importing Genres...", flush=True)
    df_genres = df_genres.where(pd.notnull(df_genres), None)
    df_genres.to_sql("genres", engine, if_exists="append", index=False)
    print(f"Imported {len(df_genres)} genres.", flush=True)

    # Import Movies & collect valid movie IDs
    print("Importing Movies...", flush=True)
    df_movies = pd.read_csv("movies_raw.csv")
    df_movies_clean = df_movies[['id', 'title', 'overview', 'release_date', 'vote_average', 'vote_count', 'popularity', 'poster_path', 'backdrop_path', 'original_language']].copy()
    df_movies_clean.drop_duplicates(subset=['id'], inplace=True)
    df_movies_clean = df_movies_clean.where(pd.notnull(df_movies_clean), None)
    df_movies_clean.to_sql("movies", engine, if_exists="append", index=False)
    valid_movie_ids = set(df_movies_clean['id'].tolist())
    print(f"Imported {len(df_movies_clean)} movies.", flush=True)

    # Import Series & collect valid series IDs
    print("Importing Series...", flush=True)
    df_series = pd.read_csv("series_raw.csv")
    df_series_clean = df_series[['id', 'name', 'overview', 'first_air_date', 'vote_average', 'vote_count', 'popularity', 'poster_path', 'backdrop_path', 'original_language']].copy()
    df_series_clean.drop_duplicates(subset=['id'], inplace=True)
    df_series_clean = df_series_clean.where(pd.notnull(df_series_clean), None)
    df_series_clean.to_sql("series", engine, if_exists="append", index=False)
    valid_series_ids = set(df_series_clean['id'].tolist())
    print(f"Imported {len(df_series_clean)} series.", flush=True)

    # Junction Tables with Validation
    print("Importing Junction Tables...", flush=True)
    try:
        # Movie Genres
        movie_genres_list = []
        for _, row in df_movies.iterrows():
            if row['id'] not in valid_movie_ids: continue
            try:
                g_ids = ast.literal_eval(row['genre_ids'])
                for g_id in g_ids:
                    if g_id in valid_genre_ids:
                        movie_genres_list.append({'movie_id': row['id'], 'genre_id': g_id})
            except:
                continue
        
        df_mg = pd.DataFrame(movie_genres_list)
        df_mg.drop_duplicates(inplace=True)
        # Handle NaN values (convert to None for SQL)
        df_mg = df_mg.where(pd.notnull(df_mg), None)
        # For testing, limit the number of rows
        # df_mg = df_mg.head(100)
        df_mg.to_sql("movie_genres", engine, if_exists="append", index=False)
        print(f"Imported {len(df_mg)} movie-genre relations.", flush=True)

        # Series Genres
        series_genres_list = []
        for _, row in df_series.iterrows():
            if row['id'] not in valid_series_ids: continue
            try:
                g_ids = ast.literal_eval(row['genre_ids'])
                for g_id in g_ids:
                    if g_id in valid_genre_ids:
                        series_genres_list.append({'series_id': row['id'], 'genre_id': g_id})
            except:
                continue
            
        df_sg = pd.DataFrame(series_genres_list)
        df_sg.drop_duplicates(inplace=True)
        df_sg.to_sql("series_genres", engine, if_exists="append", index=False)
        print(f"Imported {len(df_sg)} series-genre relations.", flush=True)

    except Exception as e:
        print(f"Error importing junction tables: {e}", flush=True)
        traceback.print_exc()

if __name__ == "__main__":
    import_data()

