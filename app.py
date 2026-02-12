import streamlit as st
import pandas as pd
import sqlalchemy
import os
import re
import json
import numpy as np
from dotenv import load_dotenv

load_dotenv()

DB_URL = f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"

st.set_page_config(page_title="Film & Dizi Keşfet", page_icon="🎬", layout="wide")

@st.cache_resource
def get_engine():
    return sqlalchemy.create_engine(DB_URL)


# =============================================
# AI QUERY UNDERSTANDING WITH GEMINI
# =============================================

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

def get_gemini_model():
    """Initialize Gemini model. Try multiple models for resilience."""
    if not GEMINI_API_KEY:
        return None
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        # Try models in order of preference based on what's available
        # Prioritize 2.0/2.5 flash as 1.5 seems unavailable to this key
        for model_name in ["gemini-2.0-flash", "gemini-2.5-flash", "gemini-2.0-flash-lite", "gemini-1.5-flash"]:
            try:
                model = genai.GenerativeModel(model_name)
                # Test generation to ensure it works
                model.generate_content("test")
                return model
            except:
                continue
        return None
    except Exception:
        return None


@st.cache_resource
def get_local_model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")


@st.cache_data(ttl=300)
def ai_parse_query(query_text):
    """
    Use Gemini to understand the user's search query in Turkish.
    Returns structured search parameters.
    """
    model = get_gemini_model()
    if not model:
        return fallback_parse(query_text)
    
    # Get available genres from DB
    engine = get_engine()
    with engine.connect() as conn:
        genres_df = pd.read_sql(sqlalchemy.text("SELECT name FROM genres ORDER BY name"), conn)
    available_genres = genres_df['name'].tolist()
    
    prompt = f"""Sen bir film ve dizi arama asistanısın. Kullanıcının Türkçe arama sorgusunu analiz et ve yapılandırılmış JSON çıktı ver.

Veritabanındaki mevcut türler: {', '.join(available_genres)}

Kullanıcı sorgusu: "{query_text}"

Aşağıdaki JSON formatında yanıt ver (sadece JSON, başka metin yazma):
{{
    "intent": "search|recommend|browse",
    "title_search": "aranan film/dizi adı varsa (örn: Harry Potter, Yüzüklerin Efendisi)",
    "similar_to": "X gibi/benzeri deniyorsa X'in adı",
    "genres": ["algılanan türler listesi - sadece mevcut türlerden seç"],
    "actors": ["oyuncu adları varsa"],
    "directors": ["yönetmen adları varsa"],
    "keywords": ["anahtar kelimeler - film/dizi adı, oyuncu, yönetmen HARİÇ anlamsal anahtar kelimeler"],
    "mood": "genel ruh hali/atmosfer (korkunç, komik, duygusal, heyecanlı, epik, karanlık, absürt, vb.)",
    "min_year": null,
    "max_year": null,
    "corrected_query": "sorgunun yazım hatası düzeltilmiş hali (örn: 'hary poter' -> 'Harry Potter', yoksa null)",
    "description": "kullanıcının ne istediğinin kısa Türkçe açıklaması"
}}

Kurallar:
- "X gibi film" = intent "recommend", similar_to = X
- Sadece film/dizi adı yazılmışsa (mesela "harry potter") = intent "search", title_search = "harry potter"
- "komik filmler", "korku dizileri" = intent "browse", genres doldur
- Oyuncu veya yönetmen adı algılarsan actors/directors'a ekle
- title_search ile similar_to'yu karıştırma: eğer "X gibi/benzeri" kalıbı varsa similar_to kullan, yoksa title_search kullan
- keywords'e sadece ANLAM taşıyan kelimeleri koy (uzay, savaş, zombi, aşk, intikam, vs.)
- Türler sadece şu listeden olabilir: {', '.join(available_genres)}
- null yerine boş string veya boş liste kullan"""
    
    try:
        import google.generativeai as genai
        response = model.generate_content(
            prompt,
            request_options={"timeout": 15}
        )
        text = response.text.strip()
        # Clean markdown code block if present
        text = re.sub(r'^```json\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
        parsed = json.loads(text)
        return parsed
    except Exception as e:
        # Silently fall back to keyword parser
        st.toast(f"⚡ AI zaman aşımı, yerel ayrıştırıcı kullanılıyor", icon="⚠️")
        return fallback_parse(query_text)


def fallback_parse(query_text):
    """Smart fallback parser when Gemini is not available. Detects 'X gibi' pattern, genres, etc."""
    KEYWORD_GENRE_MAP = {
        "korku": "Korku", "korkutucu": "Korku", "korkunç": "Korku", "korkmalık": "Korku",
        "ürkütücü": "Korku", "dehşet": "Korku", "zombi": "Korku", "vampir": "Korku",
        "gerilim": "Gerilim", "gerilimli": "Gerilim", "heyecanlı": "Gerilim", "thriller": "Gerilim",
        "komedi": "Komedi", "komik": "Komedi", "eğlenceli": "Komedi", "güldüren": "Komedi",
        "aksiyon": "Aksiyon", "aksiyonlu": "Aksiyon", "dövüş": "Aksiyon", "savaş": "Savaş",
        "romantik": "Romantik", "aşk": "Romantik", "romance": "Romantik",
        "dram": "Dram", "dramatik": "Dram", "duygusal": "Dram", "ağlatan": "Dram",
        "bilim kurgu": "Bilim-Kurgu", "bilimkurgu": "Bilim-Kurgu", "uzay": "Bilim-Kurgu",
        "sci-fi": "Bilim-Kurgu", "scifi": "Bilim-Kurgu",
        "fantastik": "Fantastik", "fantezi": "Fantastik", "büyü": "Fantastik",
        "sihir": "Fantastik", "fantasy": "Fantastik", "büyücü": "Fantastik",
        "animasyon": "Animasyon", "çizgi film": "Animasyon", "anime": "Animasyon",
        "belgesel": "Belgesel", "aile": "Aile", "çocuk": "Aile",
        "suç": "Suç", "dedektif": "Suç", "polis": "Suç", "mafya": "Suç",
        "tarih": "Tarih", "tarihi": "Tarih", "müzik": "Müzik", "müzikal": "Müzik",
        "gizem": "Gizem", "gizemli": "Gizem", "macera": "Macera", "maceralı": "Macera",
        "western": "Vahşi Batı", "kovboy": "Vahşi Batı",
    }
    STOP_WORDS = {"bir","bu","şu","ve","ile","için","de","da","mi","mı",
                  "mu","mü","ne","nasıl","çok","en","var","yok","ben","sen",
                  "film","dizi","izle","öner","öneri","bana","güzel","iyi",
                  "tür","arıyorum","istiyorum","izlenmeli","tavsiye","önerin",
                  "beğen","beğendim","seviyorum","izleyecek","isterim","olsun",
                  "gibi", "benzeri", "tarzında", "tarzı"}
    
    q = query_text.lower().strip()
    
    # ---- Detect "X gibi / X benzeri / X tarzında" pattern ----
    intent = "search"
    similar_to = ""
    title_search = ""
    
    gibi_patterns = ["gibi", "benzeri", "tarzında", "tarzı", "benzer"]
    for pattern in gibi_patterns:
        if pattern in q:
            parts = q.split(pattern, 1)
            before = parts[0].strip()
            # The text before 'gibi' is the reference title
            if before and len(before) > 2:
                similar_to = before
                intent = "recommend"
                # Analyze only the text AFTER 'gibi' for genres/keywords
                q = parts[1].strip() if len(parts) > 1 else ""
            break
    
    # ---- Detect genres from remaining text ----
    genres = []
    for kw, genre in KEYWORD_GENRE_MAP.items():
        if kw in q:
            genres.append(genre)
    genres = list(set(genres))
    
    # ---- Extract keywords (not stop words, not genre keywords) ----
    words = re.findall(r'\w+', q)
    genre_kws = set(KEYWORD_GENRE_MAP.keys())
    keywords = [w for w in words if w not in STOP_WORDS and w not in genre_kws and len(w) > 2]
    
    # If no "gibi" pattern found, treat the whole query as title search
    if intent == "search":
        # Clean the query from stop words and genre keywords for title search
        all_words = re.findall(r'\w+', query_text.lower().strip())
        clean_words = [w for w in all_words if w not in STOP_WORDS and w not in genre_kws and len(w) > 2]
        title_search = " ".join(clean_words) if clean_words else ""
    


    
    # Build description
    if intent == "recommend":
        desc = f"'{similar_to}' benzeri"
        if genres:
            desc += f" {', '.join(genres)} türünde"
        desc += " içerikler aranıyor"
    else:
        desc = f"Arama: {query_text}"
    
    return {
        "intent": intent,
        "title_search": title_search,
        "similar_to": similar_to,
        "genres": genres,
        "actors": [],
        "directors": [],
        "keywords": keywords,
        "mood": "",
        "min_year": None,
        "max_year": None,
        "corrected_query": None,
        "description": desc
    }


# =============================================
# SEMANTIC SEARCH SYSTEM
# =============================================

SIMILARITY_THRESHOLD = 0.25  # Minimum cosine similarity for results
USE_SEMANTIC_SEARCH = True  # Feature flag

@st.cache_data(ttl=600)
def embed_text(text: str):
    """Generate embedding key using local model."""
    try:
        model = get_local_model()
        embedding = model.encode(text).tolist()
        return embedding
    except Exception as e:
        st.error(f"Embedding hatası: {e}")
        return None

    
def get_reference_embedding(similar_to: str, engine):
    """Get embedding of reference title for 'X gibi' queries."""
    
    # Try movies first
    m_query = sqlalchemy.text("""
        SELECT embedding FROM movies 
        WHERE title ILIKE :pattern
        AND embedding IS NOT NULL
        LIMIT 1
    """)
    
    # Try series
    s_query = sqlalchemy.text("""
        SELECT embedding FROM series 
        WHERE name ILIKE :pattern
        AND embedding IS NOT NULL
        LIMIT 1
    """)
    
    try:
        with engine.connect() as conn:
            # Check Movies
            pattern = f"%{similar_to}%"
            # st.toast(f"Searching movies for: {pattern}")
            df_m = pd.read_sql(m_query, conn, params={"pattern": pattern})
            
            if not df_m.empty:
                # st.toast(f"Found movie: {df_m.iloc[0]['title']}")
                if df_m.iloc[0]['embedding'] is not None:
                     return df_m.iloc[0]['embedding']
            else:
                 pass # st.toast("No movie found")

            # Check Series if movie not found
            df_s = pd.read_sql(s_query, conn, params={"pattern": pattern})
            if not df_s.empty and df_s.iloc[0]['embedding'] is not None:
                return df_s.iloc[0]['embedding']
                
    except Exception as e:
        # Log error but don't crash, let semantic search fallback to keyword
        st.error(f"Error fetching reference embedding: {e}")
        pass
    
    return None

def semantic_search(media_type, ai_result, selected_genres, min_rating, year_range, selected_platforms, engine):
    """Hybrid semantic search with vector similarity + re-ranking."""
    
    intent = ai_result.get("intent") or "search"
    similar_to = (ai_result.get("similar_to") or "").strip()
    title_search = (ai_result.get("title_search") or "").strip()
    ai_genres = ai_result.get("genres") or []
    keywords = ai_result.get("keywords") or []
    mood = ai_result.get("mood") or ""
    
    # Step 1: Generate query embedding
    query_embedding = None
    
    if intent == "recommend" and similar_to:
        # Use reference item's embedding
        query_embedding = get_reference_embedding(similar_to, engine)
        if query_embedding is None:
            st.warning(f"'{similar_to}' bulunamadı veya embedding yok, genel arama yapılıyor...")
    
    if query_embedding is None:
        # Generate embedding from query + soft signals
        query_text = " ".join([
           ai_result.get("title_search") or "",
            " ".join(ai_genres or []),
            " ".join(keywords or []),
            mood or ""
        ]).strip()
        
        if not query_text:
            query_text = "film dizi"  # fallback
        
        query_embedding = embed_text(query_text)
    
    if query_embedding is None:
        st.error("Embedding oluşturulamadı, lütfen tekrar deneyin.")
        return pd.DataFrame()
    
    # Convert to PostgreSQL vector format
    if isinstance(query_embedding, str):
        embedding_str = query_embedding
    else:
        embedding_str = "[" + ",".join(map(str, query_embedding)) + "]"
    
    # Step 2: Build hard filters
    def build_where_clauses(table_prefix):
        wheres = []
        wheres.append(f"{table_prefix}.embedding IS NOT NULL")
        wheres.append(f"{table_prefix}.vote_average >= {min_rating}")
        
        yr_min = ai_result.get("min_year") or year_range[0]
        yr_max = ai_result.get("max_year") or year_range[1]
        date_col = "release_date" if table_prefix == "m" else "first_air_date"
        wheres.append(f"EXTRACT(YEAR FROM {table_prefix}.{date_col}) BETWEEN {yr_min} AND {yr_max}")
        
        # Exclude reference title in recommend mode
        if intent == "recommend" and similar_to:
            safe_similar = similar_to.lower().replace("'", "''")
            title_col = "title" if table_prefix == "m" else "name"
            wheres.append(f"LOWER({table_prefix}.{title_col}) NOT ILIKE '%{safe_similar}%'")
        
        # For search intent: require search terms to appear somewhere in the content
        if intent == "search":
            title_col = "title" if table_prefix == "m" else "name"
            search_terms = []
            if title_search:
                search_terms.append(title_search.lower().replace("'", "''"))
            search_terms.extend([k.lower().replace("'", "''") for k in (keywords or []) if len(k) > 2])
            
            if search_terms:
                text_conditions = []
                for term in search_terms:
                    text_conditions.append(
                        f"(LOWER({table_prefix}.{title_col}) ILIKE '%{term}%' "
                        f"OR LOWER(COALESCE({table_prefix}.overview,'')) ILIKE '%{term}%' "
                        f"OR LOWER(COALESCE({table_prefix}.cast_names,'')) ILIKE '%{term}%' "
                        f"OR LOWER(COALESCE({table_prefix}.director,'')) ILIKE '%{term}%' "
                        f"OR LOWER(COALESCE({table_prefix}.semantic_text,'')) ILIKE '%{term}%')"
                    )
                # At least ONE search term must match somewhere
                wheres.append(f"({' OR '.join(text_conditions)})")
        
        return wheres
    
    # Step 3: Vector similarity query
    results = []
    
    # Merge AI-parsed genres with dropdown selection
    effective_genres = list(set((selected_genres or []) + (ai_genres or [])))
    
    if media_type in ["Tümü", "Film"]:
        wheres = build_where_clauses("m")
        
        # Genre filter (AI-parsed + dropdown)
        genre_join = ""
        if effective_genres:
            genre_join = " JOIN movie_genres mg ON m.id = mg.movie_id JOIN genres g ON mg.genre_id = g.id"
            g_str = "', '".join(effective_genres)
            wheres.append(f"g.name IN ('{g_str}')")
        
        query_m = f"""
            SELECT m.id, m.title, m.vote_average,
                   m.release_date::text as date, m.overview, m.poster_path,
                   m.popularity, m.cast_names, m.director, 'FİLM' as type,
                   1 - (m.embedding <=> CAST('{embedding_str}' AS vector)) as similarity
            FROM movies m{genre_join}
            WHERE {' AND '.join(wheres)}
            ORDER BY similarity DESC
            LIMIT 100
        """
        
        try:
            with engine.connect() as conn:
                df_m = pd.read_sql(sqlalchemy.text(query_m), conn)
            results.append(df_m)
        except Exception as e:
            st.error(f"Film sorgusu hatası: {e}")
    
    if media_type in ["Tümü", "Dizi"]:
        wheres = build_where_clauses("s")
        
        genre_join = ""
        if effective_genres:
            genre_join = " JOIN series_genres sg ON s.id = sg.series_id JOIN genres g ON sg.genre_id = g.id"
            g_str = "', '".join(effective_genres)
            wheres.append(f"g.name IN ('{g_str}')")
        
        query_s = f"""
            SELECT s.id, s.name as title, s.vote_average,
                   s.first_air_date::text as date, s.overview, s.poster_path,
                   s.popularity, s.cast_names, s.director, 'DİZİ' as type,
                   1 - (s.embedding <=> CAST('{embedding_str}' AS vector)) as similarity
            FROM series s{genre_join}
            WHERE {' AND '.join(wheres)}
            ORDER BY similarity DESC
            LIMIT 100
        """
        
        try:
            with engine.connect() as conn:
                df_s = pd.read_sql(sqlalchemy.text(query_s), conn)
            results.append(df_s)
        except Exception as e:
            st.error(f"Dizi sorgusu hatası: {e}")
    
    if not results:
        return pd.DataFrame()
    
    candidates = pd.concat(results, ignore_index=True)
    
    # Step 4: Re-rank
    def calc_final_score(row):
        similarity = row['similarity']
        normalized_rating = row['vote_average'] / 10.0
        normalized_pop = min(row['popularity'] / 1000.0, 1.0)
        
        score = (
            0.75 * similarity +
            0.20 * normalized_rating +
            0.05 * normalized_pop
        )
        
        return score
    
    candidates['final_score'] = candidates.apply(calc_final_score, axis=1)
    candidates = candidates[candidates['similarity'] >= SIMILARITY_THRESHOLD]
    candidates = candidates.sort_values('final_score', ascending=False).head(50)
    candidates = candidates.drop_duplicates(subset=['id', 'type'])
    
    return candidates


# =============================================
# SMART QUERY BUILDER (Legacy - kept for fallback)
# =============================================

def norm_sql(field):
    return f"LOWER(REPLACE(REPLACE(REPLACE(REPLACE({field}, '-', ''), ' ', ''), ':', ''), '.', ''))"


def build_smart_query(media_type, ai_result, selected_genres_dropdown, min_rating, year_range, selected_platforms, engine):
    """
    Build SQL query based on AI-parsed search intent.
    """
    intent = ai_result.get("intent", "search")
    title_search = ai_result.get("title_search", "").strip()
    similar_to = ai_result.get("similar_to", "").strip()
    ai_genres = ai_result.get("genres", [])
    actors = ai_result.get("actors", [])
    directors = ai_result.get("directors", [])
    keywords = ai_result.get("keywords", [])
    mood = ai_result.get("mood", "")
    
    # If "recommend similar", first find the reference title's genres
    reference_genres = []
    if similar_to and intent == "recommend":
        ref_q = f"""
            SELECT g.name FROM movies m 
            JOIN movie_genres mg ON m.id = mg.movie_id 
            JOIN genres g ON mg.genre_id = g.id
            WHERE LOWER(m.title) ILIKE '%%{similar_to.lower().replace("'","''")}%%'
            UNION
            SELECT g.name FROM series s
            JOIN series_genres sg ON s.id = sg.series_id
            JOIN genres g ON sg.genre_id = g.id
            WHERE LOWER(s.name) ILIKE '%%{similar_to.lower().replace("'","''")}%%'
        """
        try:
            ref_df = pd.read_sql(ref_q, engine)
            reference_genres = ref_df['name'].tolist()
        except:
            pass
    
    # Combine all genre sources
    all_soft_genres = set(ai_genres) | set(reference_genres)
    hard_genres = set(selected_genres_dropdown)  # Only dropdown is hard filter
    
    # Escape strings
    def esc(s): return s.replace("'", "''").lower() if s else ""
    
    safe_title = esc(title_search)
    safe_similar = esc(similar_to)
    norm_title_search = re.sub(r'[\s\-:,\.]+', '', safe_title)
    norm_similar_search = re.sub(r'[\s\-:,\.]+', '', safe_similar)
    safe_actors = [esc(a) for a in actors if a]
    safe_directors = [esc(d) for d in directors if d]
    safe_keywords = [esc(k) for k in keywords if k]
    
    parts = []
    
    # --------- MOVIES ---------
    if media_type in ["Tümü", "Film"]:
        norm_f = norm_sql("m.title")
        
        # --- RELEVANCE (additive scoring) ---
        rel = []
        
        # In recommend mode, genre matching is PRIMARY, not popularity
        # In search mode, title matching is PRIMARY
        
        # Title search (direct name search) - only for search intent
        if norm_title_search and intent != "recommend":
            rel.append(f"CASE WHEN {norm_f} ILIKE '%%{norm_title_search}%%' THEN 300 ELSE 0 END")
        if safe_title and intent != "recommend":
            rel.append(f"CASE WHEN LOWER(m.title) ILIKE '%%{safe_title}%%' THEN 250 ELSE 0 END")
        
        # Genre match - CRITICAL for recommend mode
        if all_soft_genres:
            g_str = "', '".join(all_soft_genres)
            genre_score = 1000 if intent == "recommend" else 100
            rel.append(f"CASE WHEN EXISTS (SELECT 1 FROM movie_genres mg2 JOIN genres g2 ON mg2.genre_id = g2.id WHERE mg2.movie_id = m.id AND g2.name IN ('{g_str}')) THEN {genre_score} ELSE 0 END")
        
        # Actor match
        for a in safe_actors:
            rel.append(f"CASE WHEN LOWER(COALESCE(m.cast_names,'')) ILIKE '%%{a}%%' THEN 150 ELSE 0 END")
        
        # Director match
        for d in safe_directors:
            rel.append(f"CASE WHEN LOWER(COALESCE(m.director,'')) ILIKE '%%{d}%%' THEN 150 ELSE 0 END")
        
        # Keyword match in overview/keywords/tagline
        for k in safe_keywords:
            rel.append(f"CASE WHEN LOWER(COALESCE(m.overview,'')) ILIKE '%%{k}%%' OR LOWER(COALESCE(m.keywords,'')) ILIKE '%%{k}%%' OR LOWER(COALESCE(m.tagline,'')) ILIKE '%%{k}%%' THEN 40 ELSE 0 END")
        
        # In recommend mode, if no relevance criteria, use vote average (quality), not popularity
        # In search mode, use popularity as fallback
        if intent == "recommend":
            relevance = " + ".join(rel) if rel else "(m.vote_average * 100)"
        else:
            relevance = " + ".join(rel) if rel else "m.popularity"
        
        m_q = f"""
            SELECT DISTINCT m.id, m.title, m.vote_average,
                   m.release_date::text as date, m.overview, m.poster_path,
                   m.popularity, 'FİLM' as type,
                   m.cast_names, m.director, m.runtime, m.tagline,
                   m.production_companies, m.keywords as db_keywords,
                   m.platforms,
                   ({relevance}) as relevance
            FROM movies m
        """
        
        # Hard genre filter (dropdown only)
        if hard_genres:
            hg_str = "', '".join(hard_genres)
            m_q += f" JOIN movie_genres mg ON m.id = mg.movie_id JOIN genres g ON mg.genre_id = g.id"
        
        wheres = []
        
        if hard_genres:
            hg_str = "', '".join(hard_genres)
            wheres.append(f"g.name IN ('{hg_str}')")
        
        # --- SEARCH CONDITIONS (OR logic) ---
        search_conds = []
        
        if norm_title_search:
            search_conds.append(f"{norm_f} ILIKE '%%{norm_title_search}%%'")
        if safe_title:
            search_conds.append(f"LOWER(m.title) ILIKE '%%{safe_title}%%'")
        
        for a in safe_actors:
            search_conds.append(f"LOWER(COALESCE(m.cast_names,'')) ILIKE '%%{a}%%'")
        for d in safe_directors:
            search_conds.append(f"LOWER(COALESCE(m.director,'')) ILIKE '%%{d}%%'")
        for k in safe_keywords:
            search_conds.append(f"LOWER(COALESCE(m.overview,'')) ILIKE '%%{k}%%'")
            search_conds.append(f"LOWER(COALESCE(m.keywords,'')) ILIKE '%%{k}%%'")
            search_conds.append(f"LOWER(COALESCE(m.tagline,'')) ILIKE '%%{k}%%'")
        
        # Genre as soft search condition
        if all_soft_genres:
            g_str = "', '".join(all_soft_genres)
            search_conds.append(f"EXISTS (SELECT 1 FROM movie_genres mg3 JOIN genres g3 ON mg3.genre_id = g3.id WHERE mg3.movie_id = m.id AND g3.name IN ('{g_str}'))")
        
        if search_conds:
            wheres.append(f"({' OR '.join(search_conds)})")
        
        wheres.append(f"m.vote_average >= {min_rating}")
        yr_min = ai_result.get("min_year") or year_range[0]
        yr_max = ai_result.get("max_year") or year_range[1]
        wheres.append(f"EXTRACT(YEAR FROM m.release_date) BETWEEN {yr_min} AND {yr_max}")
        
        if selected_platforms:
            plat_conds = [f"LOWER(COALESCE(m.platforms,'')) ILIKE '%%{p.lower()}%%'" for p in selected_platforms]
            wheres.append(f"({' OR '.join(plat_conds)})")
        
        # For "recommend" intent, exclude the reference movie itself
        if similar_to and intent == "recommend" and norm_similar_search:
            wheres.append(f"{norm_f} NOT ILIKE '%%{norm_similar_search}%%'")
        
        if wheres:
            m_q += " WHERE " + " AND ".join(wheres)
        
        parts.append(m_q)
    
    # --------- SERIES ---------
    if media_type in ["Tümü", "Dizi"]:
        norm_n = norm_sql("s.name")
        
        
        rel = []
        # Title search - only for search intent
        if norm_title_search and intent != "recommend":
            rel.append(f"CASE WHEN {norm_n} ILIKE '%%{norm_title_search}%%' THEN 300 ELSE 0 END")
        if safe_title and intent != "recommend":
            rel.append(f"CASE WHEN LOWER(s.name) ILIKE '%%{safe_title}%%' THEN 250 ELSE 0 END")
        # Genre match - CRITICAL for recommend mode
        if all_soft_genres:
            g_str = "', '".join(all_soft_genres)
            genre_score = 1000 if intent == "recommend" else 100
            rel.append(f"CASE WHEN EXISTS (SELECT 1 FROM series_genres sg2 JOIN genres g2 ON sg2.genre_id = g2.id WHERE sg2.series_id = s.id AND g2.name IN ('{g_str}')) THEN {genre_score} ELSE 0 END")
        for a in safe_actors:
            rel.append(f"CASE WHEN LOWER(COALESCE(s.cast_names,'')) ILIKE '%%{a}%%' THEN 150 ELSE 0 END")
        for d in safe_directors:
            rel.append(f"CASE WHEN LOWER(COALESCE(s.creator,'')) ILIKE '%%{d}%%' THEN 150 ELSE 0 END")
        for k in safe_keywords:
            rel.append(f"CASE WHEN LOWER(COALESCE(s.overview,'')) ILIKE '%%{k}%%' OR LOWER(COALESCE(s.keywords,'')) ILIKE '%%{k}%%' THEN 40 ELSE 0 END")
        
        if intent == "recommend":
            relevance = " + ".join(rel) if rel else "(s.vote_average * 100)"
        else:
            relevance = " + ".join(rel) if rel else "s.popularity"
        
        s_q = f"""
            SELECT DISTINCT s.id, s.name as title, s.vote_average,
                   s.first_air_date::text as date, s.overview, s.poster_path,
                   s.popularity, 'DİZİ' as type,
                   s.cast_names, s.creator as director, s.episode_run_time as runtime,
                   COALESCE(s.number_of_seasons::text || ' Sezon', '') as tagline,
                   s.networks as production_companies, s.keywords as db_keywords,
                   s.platforms,
                   ({relevance}) as relevance
            FROM series s
        """
        
        if hard_genres:
            hg_str = "', '".join(hard_genres)
            s_q += f" JOIN series_genres sg ON s.id = sg.series_id JOIN genres g ON sg.genre_id = g.id"
        
        wheres = []
        if hard_genres:
            hg_str = "', '".join(hard_genres)
            wheres.append(f"g.name IN ('{hg_str}')")
        
        search_conds = []
        if norm_title_search:
            search_conds.append(f"{norm_n} ILIKE '%%{norm_title_search}%%'")
        if safe_title:
            search_conds.append(f"LOWER(s.name) ILIKE '%%{safe_title}%%'")
        for a in safe_actors:
            search_conds.append(f"LOWER(COALESCE(s.cast_names,'')) ILIKE '%%{a}%%'")
        for d in safe_directors:
            search_conds.append(f"LOWER(COALESCE(s.creator,'')) ILIKE '%%{d}%%'")
        for k in safe_keywords:
            search_conds.append(f"LOWER(COALESCE(s.overview,'')) ILIKE '%%{k}%%'")
            search_conds.append(f"LOWER(COALESCE(s.keywords,'')) ILIKE '%%{k}%%'")
        if all_soft_genres:
            g_str = "', '".join(all_soft_genres)
            search_conds.append(f"EXISTS (SELECT 1 FROM series_genres sg3 JOIN genres g3 ON sg3.genre_id = g3.id WHERE sg3.series_id = s.id AND g3.name IN ('{g_str}'))")
        
        if search_conds:
            wheres.append(f"({' OR '.join(search_conds)})")
        
        wheres.append(f"s.vote_average >= {min_rating}")
        yr_min = ai_result.get("min_year") or year_range[0]
        yr_max = ai_result.get("max_year") or year_range[1]
        wheres.append(f"EXTRACT(YEAR FROM s.first_air_date) BETWEEN {yr_min} AND {yr_max}")
        
        if selected_platforms:
            plat_conds = [f"LOWER(COALESCE(s.platforms,'')) ILIKE '%%{p.lower()}%%'" for p in selected_platforms]
            wheres.append(f"({' OR '.join(plat_conds)})")
        
        if similar_to and intent == "recommend" and norm_similar_search:
            wheres.append(f"{norm_n} NOT ILIKE '%%{norm_similar_search}%%'")
        
        if wheres:
            s_q += " WHERE " + " AND ".join(wheres)
        
        parts.append(s_q)
    
    final = " UNION ALL ".join(parts)
    final += " ORDER BY relevance DESC, popularity DESC LIMIT 50"
    return final


# =============================================
# HELPER: EMBEDDING PROGRESS
# =============================================

def get_embedding_progress(engine):
    try:
        with engine.connect() as conn:
            m_total = conn.execute(sqlalchemy.text("SELECT COUNT(*) FROM movies")).scalar() or 1
            m_embedded = conn.execute(sqlalchemy.text("SELECT COUNT(*) FROM movies WHERE embedding IS NOT NULL")).scalar() or 0
            # Series check (optional, if series table exists)
            try:
                s_total = conn.execute(sqlalchemy.text("SELECT COUNT(*) FROM series")).scalar() or 1
                s_embedded = conn.execute(sqlalchemy.text("SELECT COUNT(*) FROM series WHERE embedding IS NOT NULL")).scalar() or 0
            except:
                s_total, s_embedded = 1, 0
            return m_embedded, m_total, s_embedded, s_total
    except Exception as e:
        return 0, 1, 0, 1

# =============================================
# MAIN APP
# =============================================

def main():
    st.markdown("""
    <style>
    div[data-testid="stHorizontalBlock"] > div { padding: 0 5px; }
    </style>
    """, unsafe_allow_html=True)

    st.title("🎬 Film & Dizi Keşfet")
    st.caption("Bir sonraki favori filminizi veya dizinizi bulun")

    # AI status indicator
    if GEMINI_API_KEY:
        st.caption("🧠 AI Arama Aktif (Gemini)")
    else:
        st.caption("⚠️ AI arama pasif — `.env` dosyasına `GEMINI_API_KEY` ekleyin")

    media_type = st.radio("İçerik Türü", ["Tümü", "Film", "Dizi"], horizontal=True, label_visibility="collapsed")

    col_f1, col_f2, col_f3, col_f4 = st.columns(4)

    engine = get_engine()
    with engine.connect() as conn:
        genres_df = pd.read_sql(sqlalchemy.text("SELECT * FROM genres ORDER BY name"), conn)
    genre_list = genres_df['name'].tolist()


    PLATFORM_OPTIONS = ["Netflix", "Amazon Prime Video", "Disney Plus", "HBO Max", "Apple TV Plus", "BluTV", "Gain", "Exxen", "MUBI", "beIN CONNECT"]

    with col_f1:
        selected_genres = st.multiselect("Tür", genre_list, placeholder="Tür Seçin")
    with col_f2:
        selected_platforms = st.multiselect("Platform", PLATFORM_OPTIONS, placeholder="Platform Seçin")
    with col_f3:
        year_range = st.slider("Yıl Aralığı", 1900, 2026, (1990, 2026))
    with col_f4:
        min_rating = st.slider("Minimum Puan", 0, 10, 5)

    col_search, col_btn = st.columns([6, 1])
    with col_search:
        search_query = st.text_input(
            "Arama",
            placeholder="Ne izlemek istiyorsun? Örn: 'korkunç gerilim', 'Inception gibi film öner', 'Nolan filmleri'...",
            label_visibility="collapsed"
        )
    with col_btn:
        st.button("Ara", type="primary", use_container_width=True)

    st.divider()

    # --- AI ANALYSIS ---
    ai_result = None
    if search_query:
        with st.spinner("🧠 Sorgu analiz ediliyor..."):
            ai_result = ai_parse_query(search_query)
        
        if ai_result:
            desc = ai_result.get("description", "")
            intent = ai_result.get("intent", "search")
            corrected = ai_result.get("corrected_query")
            
            if corrected and corrected.lower() != search_query.lower().strip():
                st.toast(f"💡 Bunu mu demek istediniz: **{corrected}**?", icon="✨")
                # Optional: You could auto-search for the corrected query here if desired
            
            info_parts = []
            if intent == "recommend":
                similar = ai_result.get("similar_to", "")
                info_parts.append(f"🎯 **Öneri modu**: *{similar}* benzeri içerikler aranıyor")
            elif intent == "browse":
                info_parts.append("📂 **Keşfet modu**: Türe göre sonuçlar")
            else:
                title = ai_result.get("title_search", "")
                if title:
                    info_parts.append(f"🔍 **Arama**: *{title}*")
            
            if ai_result.get("genres"):
                info_parts.append(f"🎭 Türler: **{', '.join(ai_result['genres'])}**")
            if ai_result.get("actors"):
                info_parts.append(f"👤 Oyuncular: **{', '.join(ai_result['actors'])}**")
            if ai_result.get("directors"):
                info_parts.append(f"🎬 Yönetmenler: **{', '.join(ai_result['directors'])}**")
            if ai_result.get("keywords"):
                info_parts.append(f"🔑 Anahtar: **{', '.join(ai_result['keywords'])}**")
            if ai_result.get("mood"):
                info_parts.append(f"🎨 Atmosfer: **{ai_result['mood']}**")
            if desc:
                info_parts.append(f"� *{desc}*")
            
            st.info(" | ".join(info_parts) if info_parts else f"🔍 {search_query}")
    
    # --- BUILD & EXECUTE QUERY ---
    if ai_result:
        df = semantic_search(media_type, ai_result, selected_genres, min_rating, year_range, selected_platforms, engine)
        
        # --- FALLBACK MECHANISM ---
        # If semantic search returns empty (likely due to missing embeddings), try classic keyword search
        if df.empty and ai_result.get("intent") == "search":
            try:
                fallback_sql = build_smart_query(media_type, ai_result, selected_genres, min_rating, year_range, selected_platforms, engine)
                df_fallback = pd.read_sql(fallback_sql, engine)
                if not df_fallback.empty:
                    df = df_fallback
                    st.warning("⚠️ Akıllı arama sonuç vermedi (henüz tüm içerikler analiz edilmedi), klasik kelime bazlı sonuçlar gösteriliyor.")
            except Exception as e:
                # Debug only
                # st.error(f"Fallback error: {e}")
                pass
    else:
        # No search query — show popular content
        ai_result = {"intent": "browse", "title_search": "", "similar_to": "", "genres": [], 
                     "actors": [], "directors": [], "keywords": [], "mood": "", 
                     "min_year": None, "max_year": None, "description": ""}
        df = semantic_search(media_type, ai_result, selected_genres, min_rating, year_range, selected_platforms, engine)

    try:
        if df.empty:
            st.info("Aramanıza uygun sonuç bulunamadı. Farklı kelimeler veya daha düşük puan filtresi deneyin.")
        else:
            st.write(f"**{len(df)} sonuç bulundu**")

        for _, row in df.iterrows():
            with st.container():
                c1, c2 = st.columns([1, 5])

                with c1:
                    img_url = f"https://image.tmdb.org/t/p/w200{row['poster_path']}" if row['poster_path'] else "https://via.placeholder.com/150x225?text=Resim+Yok"
                    st.image(img_url, use_column_width=True)

                with c2:
                    badge_color = "#3b82f6" if row['type'] == 'FİLM' else "#eab308"
                    year_str = row['date'][:4] if row['date'] else 'Bilinmiyor'
                    runtime_str = f" • {row['runtime']} dk" if row.get('runtime') and pd.notna(row['runtime']) else ""

                    st.markdown(f"""
                    <div style="display: flex; justify-content: space-between; align-items: start;">
                        <div>
                            <h3 style="margin: 0; padding: 0;">{row['title']}</h3>
                            <div style="color: #FACC15; font-weight: bold; margin-top: 4px;">
                                ⭐ {row['vote_average']}
                                <span style="color: #888; font-weight: normal;">
                                    • Yıl: {year_str}{runtime_str}
                                </span>
                            </div>
                        </div>
                        <span style="background-color: {badge_color}; color: white; padding: 4px 12px; border-radius: 6px; font-size: 12px; font-weight: bold;">
                            {row['type']}
                        </span>
                    </div>
                    """, unsafe_allow_html=True)

                    meta_parts = []
                    if row.get('director') and pd.notna(row['director']) and row['director']:
                        label = "Yönetmen" if row['type'] == 'FİLM' else "Yapımcı"
                        meta_parts.append(f"🎬 {label}: {row['director']}")
                    if row.get('cast_names') and pd.notna(row['cast_names']) and row['cast_names']:
                        meta_parts.append(f"👥 Oyuncular: {row['cast_names']}")
                    if row.get('tagline') and pd.notna(row['tagline']) and row['tagline']:
                        if row['type'] == 'DİZİ':
                            meta_parts.append(f"📺 {row['tagline']}")
                    if row.get('production_companies') and pd.notna(row['production_companies']) and row['production_companies']:
                        label = "Yapım" if row['type'] == 'FİLM' else "Ağ"
                        meta_parts.append(f"🏢 {label}: {row['production_companies']}")
                    if row.get('platforms') and pd.notna(row['platforms']) and row['platforms']:
                        meta_parts.append(f"📺 İzlenebilir: {row['platforms']}")

                    if meta_parts:
                        st.markdown(f"""
                        <div style="margin-top: 6px; color: #AAA; font-size: 13px; line-height: 1.8;">
                            {'<br>'.join(meta_parts)}
                        </div>
                        """, unsafe_allow_html=True)

                    overview = row['overview'] if row['overview'] else "Açıklama mevcut değil."
                    if len(overview) > 300:
                        overview = overview[:300] + "..."

                    st.markdown(f"""
                    <div style="margin-top: 8px; color: #CCC; line-height: 1.5;">
                        {overview}
                    </div>
                    """, unsafe_allow_html=True)

                st.divider()

    except Exception as e:
        st.error(f"Hata: {e}")

if __name__ == "__main__":
    main()
