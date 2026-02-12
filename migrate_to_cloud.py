import os
import sqlalchemy
from sqlalchemy import text
import pandas as pd
from dotenv import load_dotenv

# Load local environment
load_dotenv()

LOCAL_DB_URL = f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"

def get_remote_url():
    print("\n🚀 Bulut Veritabanı Taşıma Aracı (Cloud Migration)")
    print("--------------------------------------------------")
    print("Verilerinizi ücretsiz bir bulut veritabanına (örn. Neon.tech) taşımak için")
    print("önce oradan aldığınız Bağlantı URL'sine ihtiyacımız var.")
    print("\nFormat şuna benzer: postgresql://neondb_owner:password@ep-xyz.Region.aws.neon.tech/neondb?sslmode=require")
    
    url = input("\nLütfen Bulut Veritabanı URL'sini yapıştırın: ").strip()
    return url if url.startswith("postgres") else None

def migrate(remote_url):
    print("\n1. Yerel veritabanına bağlanılıyor...")
    local_engine = sqlalchemy.create_engine(LOCAL_DB_URL)
    
    print("2. Uzak veritabanına bağlanılıyor...")
    remote_engine = sqlalchemy.create_engine(remote_url)
    
    print("3. Uzak sunucuda 'vector' eklentisi açılıyor...")
    try:
        with remote_engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.commit()
    except Exception as e:
        print(f"⚠️ Vector eklentisi zaten var veya yetki yok: {e}")

    tables = ["genres", "movies", "series", "movie_genres", "series_genres"]
    
    for table in tables:
        print(f"4. Tablo taşınıyor: {table}...")
        try:
            df = pd.read_sql(f"SELECT * FROM {table}", local_engine)
            if df.empty:
                print(f"   ⚠️ {table} boş, geçiliyor.")
                continue
                
            print(f"   📥 {len(df)} satır okunuyor...")
            
            # Write to remote
            df.to_sql(table, remote_engine, if_exists='replace', index=False, method='multi', chunksize=1000)
            print(f"   📤 {table} başarıyla yüklendi!")
            
            # Simple PK logic (pandas doesn't add it)
            if 'id' in df.columns:
                try:
                    with remote_engine.connect() as conn:
                        conn.execute(text(f"ALTER TABLE {table} ADD PRIMARY KEY (id)"))
                        conn.commit()
                except: pass
                        
        except Exception as e:
            print(f"   ❌ Hata ({table}): {e}")
            
    print("\n✅ Taşıma işlemi tamamlandı!")
    print("Şimdi bu uzak veritabanı URL'sini Streamlit Cloud'da 'Secrets' kısmına ekleyebilirsiniz.")

if __name__ == "__main__":
    url = get_remote_url()
    if url:
        migrate(url)
