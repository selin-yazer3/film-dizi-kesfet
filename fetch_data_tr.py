import os
import requests
import pandas as pd
import time
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("TMDB_API_KEY")

if not API_KEY:
    raise ValueError("TMDB_API_KEY not found in .env file")

BASE_URL = "https://api.themoviedb.org/3"

def fetch_tmdb_data(endpoint, total_items=5000):
    """Fetches data from TMDB API in Turkish with pagination."""
    results = []
    page = 1
    items_per_page = 20
    max_pages = total_items // items_per_page + 1
    
    print(f"Fetching {endpoint} (Turkish)...")
    
    while page <= max_pages:
        url = f"{BASE_URL}/{endpoint}"
        params = {
            "api_key": API_KEY,
            "language": "tr-TR",   # TURKISH!
            "page": page
        }
        
        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            items = data.get("results", [])
            if not items:
                break
                
            results.extend(items)
            
            if page % 25 == 0:
                print(f"  Page {page}/{max_pages} - {len(results)} items", flush=True)
            
            page += 1
            time.sleep(0.1)
            
        except Exception as e:
            print(f"Error page {page}: {e}")
            break
            
    return pd.DataFrame(results)

def main():
    # 1. Fetch Movies in Turkish
    print("--- Fetching Movies (TR) ---", flush=True)
    df_movies = fetch_tmdb_data("movie/top_rated", total_items=5000)
    df_movies.to_csv("movies_raw.csv", index=False)
    print(f"Saved {len(df_movies)} movies", flush=True)

    # 2. Fetch Series in Turkish
    print("--- Fetching TV Series (TR) ---", flush=True)
    df_series = fetch_tmdb_data("tv/top_rated", total_items=5000)
    df_series.to_csv("series_raw.csv", index=False)
    print(f"Saved {len(df_series)} series", flush=True)
    
    # 3. Fetch Genres in Turkish
    print("--- Fetching Genres (TR) ---", flush=True)
    movie_genres = requests.get(f"{BASE_URL}/genre/movie/list", params={"api_key": API_KEY, "language": "tr-TR"}).json()['genres']
    tv_genres = requests.get(f"{BASE_URL}/genre/tv/list", params={"api_key": API_KEY, "language": "tr-TR"}).json()['genres']
    
    all_genres = {g['id']: g['name'] for g in movie_genres + tv_genres}
    df_genres = pd.DataFrame(list(all_genres.items()), columns=['id', 'name'])
    df_genres.to_csv("genres.csv", index=False)
    print(f"Saved {len(df_genres)} genres", flush=True)
    
    print("\nDone! All data fetched in Turkish.", flush=True)

if __name__ == "__main__":
    main()
