# 🎬 Film & Dizi Keşfet

Türkçe film ve dizi öneri uygulaması. Semantik arama, yapay zeka destekli sorgu anlama ve kişiselleştirilmiş öneriler sunar.

## ✨ Özellikler

- **Semantik Arama** — "uzayda geçen bilim kurgu" gibi doğal dil sorgularıyla arama
- **Akıllı Öneriler** — "Harry Potter gibi fantastik film" gibi benzer içerik bulma
- **Oyuncu/Yönetmen Arama** — "Tarantino" veya "DiCaprio" ile kişi bazlı arama
- **Tür & Puan Filtreleme** — Dropdown ve slider ile sonuçları daraltma
- **Çok Dilli Embedding** — Türkçe içerikler için optimize edilmiş `paraphrase-multilingual-MiniLM-L12-v2` modeli
- **Gemini AI Entegrasyonu** — Sorgu anlama ve yazım düzeltme (opsiyonel)
- **7363+ Film & Dizi** — TMDB API'den çekilmiş zengin Türkçe veri seti

## 🛠️ Teknolojiler

| Teknoloji | Kullanım |
|---|---|
| **Streamlit** | Web arayüzü |
| **PostgreSQL + pgvector** | Veritabanı & vektör benzerlik araması |
| **Sentence Transformers** | Lokal embedding üretimi |
| **Google Gemini** | Sorgu anlama (opsiyonel) |
| **TMDB API** | Film/dizi verisi |

## 📋 Kurulum

### Gereksinimler
- Python 3.9+
- PostgreSQL 15+ (pgvector eklentisiyle)
- Docker (opsiyonel, veritabanı için)

### 1. Projeyi klonlayın
```bash
git clone https://github.com/YOUR_USERNAME/film-dizi-kesfet.git
cd film-dizi-kesfet
```

### 2. Bağımlılıkları yükleyin
```bash
pip install -r requirements.txt
```

### 3. Ortam değişkenlerini ayarlayın
```bash
cp .env.example .env
# .env dosyasını düzenleyip API anahtarlarınızı ekleyin
```

**Gerekli API anahtarları:**
- `TMDB_API_KEY` — [TMDB](https://www.themoviedb.org/settings/api) adresinden alın
- `GEMINI_API_KEY` — [Google AI Studio](https://aistudio.google.com/apikey) adresinden alın (opsiyonel)

### 4. Veritabanını kurun

**Docker ile (önerilen):**
```bash
docker run -d --name pgvector -p 5432:5432 \
  -e POSTGRES_PASSWORD=postgres \
  ankane/pgvector
```

**Manuel:**
PostgreSQL kurulumunuzda `pgvector` eklentisini etkinleştirin.

### 5. Tabloları oluşturun ve veri aktarın
```bash
python create_db.py
python fetch_data_tr.py      # TMDB'den film/dizi çek
python import_data.py         # CSV → PostgreSQL
python fetch_credits.py       # Oyuncu/yönetmen bilgisi çek
```

### 6. Embedding'leri üretin
```bash
python generate_embeddings_local.py
```
> ℹ️ İlk çalıştırmada model indirilir (~500MB). 7363 içerik için ~15 dakika sürer.

### 7. Uygulamayı başlatın
```bash
streamlit run app.py
```

## 🔍 Arama Örnekleri

| Sorgu | Sonuç |
|---|---|
| `tarantino` | Tüm Quentin Tarantino filmleri |
| `harry potter gibi fantastik film` | HP'ye benzer Fantastik filmler |
| `uzayda geçen bilim kurgu` | Sci-fi filmleri (2001, Alien, Yerçekimi...) |
| `gece gece korkmalık film` | Korku filmleri |
| `romantik komedi` | Rom-com filmleri |

## 📁 Proje Yapısı

```
├── app.py                        # Ana Streamlit uygulaması
├── create_db.py                  # Veritabanı tablo oluşturma
├── import_data.py                # CSV → DB veri aktarımı
├── fetch_data_tr.py              # TMDB'den Türkçe veri çekme
├── fetch_credits.py              # Oyuncu/yönetmen bilgisi çekme
├── generate_embeddings_local.py  # Lokal embedding üretimi
├── genres.csv                    # Tür listesi
├── requirements.txt              # Python bağımlılıkları
├── .env.example                  # Örnek ortam değişkenleri
└── .gitignore                    # Git filtreleme kuralları
```

## 📄 Lisans

MIT
