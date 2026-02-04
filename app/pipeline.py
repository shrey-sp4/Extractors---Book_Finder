import os
import pandas as pd
import sqlite3
import concurrent.futures
import requests
from .utils import (
    normalize_isbn, 
    fetch_google_books, 
    fetch_openlibrary, 
    fetch_openalex, 
    fetch_google_books_search,
    clean_description,
    parse_year
)

# Configuration
DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../data'))
RAW_DATA_PATH = os.path.join(DATA_DIR, 'books_data.csv')
ENRICHED_DATA_PATH = os.path.join(DATA_DIR, 'books_raw_enriched.csv')
CLEANED_DATA_PATH = os.path.join(DATA_DIR, 'books_cleaned.csv')
DB_PATH = os.path.join(DATA_DIR, 'books.db')

def run_ingestion(limit=None):
    """
    Step 1: Ingestion & Enrichment.
    """
    print("Stage 1: Ingestion")
    if not os.path.exists(RAW_DATA_PATH):
        print(f"Error: Raw data file not found at {RAW_DATA_PATH}")
        return False

    try:
        df = pd.read_csv(RAW_DATA_PATH, encoding='utf-8')
    except UnicodeDecodeError:
        df = pd.read_csv(RAW_DATA_PATH, encoding='latin-1')

    if limit:
        df = df.head(limit)
    
    print(f"Loaded {len(df)} rows. Starting enrichment...")

    # Drop unnecessary columns if they exist
    unnamed_cols = [c for c in df.columns if "Unnamed" in c]
    if unnamed_cols:
        df = df.drop(unnamed_cols, axis=1)

    # Normalize ISBNs
    if 'ISBN' in df.columns:
        df['clean_isbn'] = df['ISBN'].apply(normalize_isbn)
    
    df['description'] = None

    def process_book_row(idx, row):
        isbn = row.get('clean_isbn')
        title = row.get('Title')
        author = row.get('Author/Editor')
        
        desc = None
        # 1. Google Books (ISBN)
        if isbn:
            data = fetch_google_books(isbn)
            if data: desc = data.get('description')
        
        # 2. OpenLibrary (ISBN)
        if not desc and isbn:
            ol_data = fetch_openlibrary(isbn)
            if ol_data and isinstance(ol_data, dict):
                val = ol_data.get('description')
                desc = val.get('value') if isinstance(val, dict) else val
        
        # 3. OpenAlex (ISBN)
        if not desc and isbn:
            desc = fetch_openalex(isbn)

        # 4. Search Fallback (Title + Author)
        if not desc and title:
            data = fetch_google_books_search(title, author)
            if data: desc = data.get('description')
            
        return idx, desc

    MAX_WORKERS = 30
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_idx = {
            executor.submit(process_book_row, idx, row): idx 
            for idx, row in df.iterrows()
        }
        
        completed_count = 0
        for future in concurrent.futures.as_completed(future_to_idx):
            idx, desc = future.result()
            if desc:
                df.at[idx, 'description'] = desc
            
            completed_count += 1
            if completed_count % 500 == 0:
                print(f"Processed {completed_count}/{len(df)} books...")

    df.to_csv(ENRICHED_DATA_PATH, index=False)
    print(f"Enriched data saved to {ENRICHED_DATA_PATH}")
    return True

def run_transformation():
    """
    Step 2: Transformation & Cleaning.
    """
    print("Stage 2: Transformation")
    if not os.path.exists(ENRICHED_DATA_PATH):
        print(f"Error: Enriched data not found at {ENRICHED_DATA_PATH}. Run ingestion first.")
        return False

    df = pd.read_csv(ENRICHED_DATA_PATH)
    print(f"Loaded {len(df)} rows for cleaning.")

    # Clean description
    df['clean_description'] = df['description'].apply(clean_description)

    # Filter and Deduplicate
    initial_len = len(df)
    df_clean = df.dropna(subset=['clean_description'])
    df_clean = df_clean.drop_duplicates(subset=['clean_isbn'])

    print(f"Rows before: {initial_len}, after filtering and deduplication: {len(df_clean)}")
    df_clean.to_csv(CLEANED_DATA_PATH, index=False)
    print(f"Cleaned data saved to {CLEANED_DATA_PATH}")
    return True

def run_storage():
    """
    Step 3: Storage.
    """
    print("Stage 3: Storage")
    if not os.path.exists(CLEANED_DATA_PATH):
        print(f"Error: Cleaned data not found at {CLEANED_DATA_PATH}. Run transformation first.")
        return False

    df = pd.read_csv(CLEANED_DATA_PATH)
    if df.empty:
        print("Warning: Cleaned data is empty. Skipping storage to prevent wiping existing database.")
        return False
        
    print(f"Loaded {len(df)} rows for database insertion.")

    conn = sqlite3.connect(DB_PATH)
    
    # Map columns to DB schema
    data_to_insert = pd.DataFrame()
    data_to_insert['title'] = df['Title'] if 'Title' in df.columns else None
    data_to_insert['author'] = df['Author/Editor'] if 'Author/Editor' in df.columns else None
    data_to_insert['year'] = df['Year'].apply(parse_year) if 'Year' in df.columns else None
    data_to_insert['edition'] = df['Ed./Vol.'] if 'Ed./Vol.' in df.columns else None
    data_to_insert['publisher'] = df['Place & Publisher'] if 'Place & Publisher' in df.columns else None
    data_to_insert['isbn'] = df['clean_isbn']
    data_to_insert['description'] = df['clean_description']

    try:
        data_to_insert.to_sql('books', conn, if_exists='replace', index=False)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_isbn ON books(isbn);")
        print(f"Successfully inserted {len(data_to_insert)} rows into {DB_PATH}")
    except Exception as e:
        print(f"Error inserting into database: {e}")
        return False
    finally:
        conn.close()
    
    return True

def run_full_pipeline(limit=None):
    """Runs all stages in sequence."""
    success = run_ingestion(limit=limit)
    if success:
        success = run_transformation()
    if success:
        success = run_storage()
    
    if success:
        print("\nPipeline Completed Successfully")
    else:
        print("\nPipeline Failed")

def get_database_stats():
    """Queries the database for current statistics and prints them."""
    if not os.path.exists(DB_PATH):
        print(f"Error: Database not found at {DB_PATH}. Run 'setup' first.")
        return

    conn = sqlite3.connect(DB_PATH)
    try:
        # 1. General Overview
        total_books = pd.read_sql_query("SELECT COUNT(*) FROM books", conn).iloc[0,0]
        unique_publishers = pd.read_sql_query("SELECT COUNT(DISTINCT publisher) FROM books", conn).iloc[0,0]
        year_stats = pd.read_sql_query("SELECT MIN(year) as min_year, MAX(year) as max_year, AVG(year) as avg_year FROM books WHERE year IS NOT NULL", conn)

        # 2. Description Metrics
        desc_stats = pd.read_sql_query("""
            SELECT 
                MAX(LENGTH(description)) as max_len, 
                MIN(LENGTH(description)) as min_len, 
                AVG(LENGTH(description)) as avg_len 
            FROM books 
            WHERE description IS NOT NULL
        """, conn)

        # 3. Top Authors
        top_authors = pd.read_sql_query("""
            SELECT author, COUNT(*) as count 
            FROM books 
            WHERE author IS NOT NULL 
            GROUP BY author 
            ORDER BY count DESC 
            LIMIT 5
        """, conn)

        print("\nCurrent Database Statistics")
        print(f"Total Books:       {total_books}")
        print(f"Unique Publishers: {unique_publishers}")
        if not year_stats.empty and year_stats['min_year'][0] is not None:
            print(f"Year Range:        {int(year_stats['min_year'][0])} - {int(year_stats['max_year'][0])} (Avg: {int(year_stats['avg_year'][0])})")
        
        print("\nDescription Metrics")
        if not desc_stats.empty and desc_stats['max_len'][0] is not None:
            print(f"Longest:           {int(desc_stats['max_len'][0])} characters")
            print(f"Shortest:          {int(desc_stats['min_len'][0])} characters")
            print(f"Average:           {int(desc_stats['avg_len'][0])} characters")
        else:
            print("No descriptions found.")

        print("\nTop Authors")
        if not top_authors.empty:
            print(top_authors.to_string(index=False))
        else:
            print("No author data found.")
        print("\n")

    except Exception as e:
        print(f"Error reading database: {e}")
    finally:
        conn.close()
