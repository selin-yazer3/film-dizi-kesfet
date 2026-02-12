import os
import psycopg2
from psycopg2 import sql
from dotenv import load_dotenv

load_dotenv()

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "your_password")
DB_PORT = os.getenv("DB_PORT", "5432")
TARGET_DB = os.getenv("DB_NAME", "movie_recommendation_db")

def create_database():
    """Create the target database if it doesn't exist."""
    print(f"Connecting to 'postgres' database to create '{TARGET_DB}'...")
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            port=DB_PORT,
            dbname="postgres"  # Connect to default DB first
        )
        conn.autocommit = True
        cur = conn.cursor()

        # Check if database exists
        cur.execute("SELECT 1 FROM pg_catalog.pg_database WHERE datname = %s", (TARGET_DB,))
        exists = cur.fetchone()

        if not exists:
            cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(TARGET_DB)))
            print(f"Database '{TARGET_DB}' created successfully.")
        else:
            print(f"Database '{TARGET_DB}' already exists.")

        cur.close()
        conn.close()

    except Exception as e:
        print(f"Error creating database: {e}")
        print("Please check your PostgreSQL credentials in .env file.")
        raise

def create_tables():
    """Create tables in the target database."""
    print(f"Connecting to '{TARGET_DB}' to create tables...")
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            port=DB_PORT,
            dbname=TARGET_DB
        )
        cur = conn.cursor()

        # Drop existing tables to ensure clean slate
        print("Dropping existing tables...")
        cur.execute("DROP TABLE IF EXISTS movie_genres, series_genres, movies, series, genres CASCADE;")

        # Create Tables
        tables = [
            """
            CREATE TABLE movies (
                id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                overview TEXT,
                release_date DATE,
                vote_average FLOAT,
                vote_count INTEGER,
                popularity FLOAT,
                poster_path TEXT,
                backdrop_path TEXT,
                original_language TEXT
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS series (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                overview TEXT,
                first_air_date DATE,
                vote_average FLOAT,
                vote_count INTEGER,
                popularity FLOAT,
                poster_path TEXT,
                backdrop_path TEXT,
                original_language TEXT
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS genres (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS movie_genres (
                movie_id INTEGER REFERENCES movies(id),
                genre_id INTEGER REFERENCES genres(id),
                PRIMARY KEY (movie_id, genre_id)
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS series_genres (
                series_id INTEGER REFERENCES series(id),
                genre_id INTEGER REFERENCES genres(id),
                PRIMARY KEY (series_id, genre_id)
            );
            """
        ]

        for query in tables:
            cur.execute(query)
        
        conn.commit()
        print("All tables created successfully.")
        
        cur.close()
        conn.close()

    except Exception as e:
        print(f"Error creating tables: {e}")
        raise

if __name__ == "__main__":
    create_database()
    create_tables()
