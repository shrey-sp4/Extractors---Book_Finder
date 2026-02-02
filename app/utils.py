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
                return {
                    "title": info.get('title'),
                    "author": ", ".join(info.get('authors', [])) if info.get('authors') else None,
                    "year": info.get('publishedDate'),
                    "publisher": info.get('publisher'),
                    "description": info.get('description'),
                    "isbn": isbn
                }
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
                # Try to find ISBN from industryIdentifiers
                isbn = None
                for identifier in info.get('industryIdentifiers', []):
                    if identifier.get('type') in ['ISBN_13', 'ISBN_10']:
                        isbn = identifier.get('identifier')
                        break
                return {
                    "title": info.get('title'),
                    "author": ", ".join(info.get('authors', [])) if info.get('authors') else None,
                    "year": info.get('publishedDate'),
                    "publisher": info.get('publisher'),
                    "description": info.get('description'),
                    "isbn": isbn
                }
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

def parse_year(date_str):
    if not date_str:
        return None
    # Extract 4-digit year using regex
    match = re.search(r'\b(1\d{3}|20\d{2})\b', str(date_str))
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            pass
    return None

def run_book_pipeline(isbn, title=None, author=None):
    """
    Runs the full ingestion and transformation pipeline for a single book.
    """
    clean_isbn = normalize_isbn(isbn)
    book_data = {
        "title": title,
        "author": author,
        "year": None,
        "edition": None,
        "publisher": None,
        "description": None,
        "isbn": clean_isbn
    }
    
    source_data = None
    
    # 1. Google Books (ISBN)
    if clean_isbn:
        source_data = fetch_google_books(clean_isbn)
    
    # 2. OpenLibrary (ISBN)
    if not source_data and clean_isbn:
        ol_data = fetch_openlibrary(clean_isbn)
        if ol_data and isinstance(ol_data, dict):
             source_data = {
                 "title": ol_data.get('title'),
                 "author": ", ".join([a.get('name') for a in ol_data.get('authors', [])]) if ol_data.get('authors') else None,
                 "year": ol_data.get('publish_date'),
                 "publisher": ", ".join(ol_data.get('publishers', [])) if ol_data.get('publishers') else None,
                 "isbn": clean_isbn
             }
             val = ol_data.get('description')
             if isinstance(val, dict):
                 source_data["description"] = val.get('value')
             else:
                 source_data["description"] = val
                 
    # 3. OpenAlex (ISBN) - Only for description fallback
    if (not source_data or not source_data.get("description")) and clean_isbn:
        alex_desc = fetch_openalex(clean_isbn)
        if alex_desc:
            if not source_data:
                source_data = {"description": alex_desc, "isbn": clean_isbn}
            else:
                source_data["description"] = alex_desc

    # 4. Search Fallback (Title + Author)
    if not source_data and title:
        source_data = fetch_google_books_search(title, author)
        
    if source_data:
        # Update book_data with fetched values if they are not already set
        book_data["title"] = book_data["title"] or source_data.get("title")
        book_data["author"] = book_data["author"] or source_data.get("author")
        book_data["year"] = parse_year(source_data.get("year"))
        book_data["publisher"] = book_data["publisher"] or source_data.get("publisher")
        book_data["description"] = clean_description(source_data.get("description"))
        if not book_data["isbn"]:
            book_data["isbn"] = normalize_isbn(source_data.get("isbn"))

    return book_data
