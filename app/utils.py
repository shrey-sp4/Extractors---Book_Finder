import requests
import re
import ftfy
from bs4 import BeautifulSoup
import pandas as pd

session = requests.Session()

def normalize_isbn(isbn):
    if isbn is None or (isinstance(isbn, float) and pd.isna(isbn)):
        return None
    isbn = str(isbn)
    # Removing non-alphanumeric characters
    clean = re.sub(r'[^a-zA-Z0-9]', '', isbn)
    return clean

def reconstruct_openalex_abstract(inverted_index):
    if not inverted_index:
        return None
    word_index = []
    for word, positions in inverted_index.items():
        for pos in positions:
            word_index.append((pos, word))
    word_index.sort()
    return ' '.join([word for _, word in word_index])

def fetch_openlibrary(isbn):
    if not isbn:
        return None
    url = f"https://openlibrary.org/api/books?bibkeys=ISBN:{isbn}&format=json&jscmd=data"
    try:
        response = session.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            key = f"ISBN:{isbn}"
            if key in data:
                return data[key]
    except Exception:
        pass
    return None

def fetch_google_books(isbn):
    if not isbn:
        return None
    url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}"
    try:
        response = session.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if 'items' in data:
                item = data['items'][0]
                info = item.get('volumeInfo', {})
                return info.get('description')
    except Exception:
        pass
    return None

def fetch_google_books_search(title, author):
    if not title:
        return None
    query = title
    if author:
        clean_author = str(author).split(',')[0].split(';')[0].strip()
        query += f" {clean_author}"
    url = "https://www.googleapis.com/books/v1/volumes"
    params = {'q': query, 'maxResults': 1}
    try:
        response = session.get(url, params=params, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if 'items' in data:
                item = data['items'][0]
                info = item.get('volumeInfo', {})
                return info.get('description')
    except Exception:
        pass
    return None

def fetch_openalex(isbn):
    if not isbn:
        return None
    url = f"https://api.openalex.org/works?filter=ids.isbn:{isbn}"
    try:
        response = session.get(url, timeout=3)
        if response.status_code == 200:
            data = response.json()
            results = data.get('results', [])
            if results:
                work = results[0]
                abstract = reconstruct_openalex_abstract(work.get('abstract_inverted_index'))
                if abstract:
                    return f"Abstract: {abstract}"
                concepts = work.get('concepts', [])
                if concepts:
                    concepts.sort(key=lambda x: x.get('score', 0), reverse=True)
                    keywords = [c['display_name'] for c in concepts[:10]]
                    return f"Keywords: {', '.join(keywords)}"
    except Exception:
        pass
    return None

def clean_description(text):
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return None
    text = ftfy.fix_text(str(text))
    soup = BeautifulSoup(text, 'html.parser')
    text = soup.get_text()
    text = ' '.join(text.split())
    if len(text) < 5 or "description not available" in text.lower():
        return None
    return text

def run_book_pipeline(isbn, title=None, author=None):
    """
    Runs the full ingestion and transformation pipeline for a single book.
    """
    clean_isbn = normalize_isbn(isbn)
    desc = None
    
    # 1. Google Books (ISBN)
    if clean_isbn:
        desc = fetch_google_books(clean_isbn)
    
    # 2. OpenLibrary (ISBN)
    if not desc and clean_isbn:
        ol_data = fetch_openlibrary(clean_isbn)
        if ol_data and isinstance(ol_data, dict):
             val = ol_data.get('description')
             if isinstance(val, dict):
                 desc = val.get('value')
             else:
                 desc = val
                 
    # 3. OpenAlex (ISBN)
    if not desc and clean_isbn:
        desc = fetch_openalex(clean_isbn)

    # 4. Search Fallback (Title + Author)
    if not desc and title:
        desc = fetch_google_books_search(title, author)
        
    cleaned_desc = clean_description(desc)
    return {
        "isbn": clean_isbn,
        "description": cleaned_desc
    }
