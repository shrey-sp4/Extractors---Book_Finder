import os
import sqlite3
import pandas as pd
import numpy as np
import faiss
import pickle
from sentence_transformers import SentenceTransformer
from litellm import completion
from typing import List, Dict, Any
from dotenv import load_dotenv

load_dotenv()

# Configuration
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, 'data', 'books.db')
INDEX_PATH = os.path.join(BASE_DIR, 'data', 'books_index.faiss')
METADATA_PATH = os.path.join(BASE_DIR, 'data', 'books_metadata.pkl')
API_URL = "http://127.0.0.1:8000/books"  # FastAPI endpoint

DEFAULT_MODEL = "all-MiniLM-L6-v2"

def clean_isbn(isbn):
    """Clean and validate ISBN for API calls."""
    if not isbn or isinstance(isbn, float) and pd.isna(isbn):
        return None
    
    isbn_str = str(isbn)
    
    # Handle scientific notation (e.g., 9.78354E+12)
    if 'E' in isbn_str or 'e' in isbn_str:
        try:
            isbn_str = f"{float(isbn_str):.0f}"
        except:
            return None
    
    # Remove non-numeric characters
    isbn_clean = ''.join(c for c in isbn_str if c.isdigit())
    
    # Validate length (ISBN-10 or ISBN-13)
    if len(isbn_clean) not in [10, 13]:
        return None
    
    # Checking if it's actually a number
    if not isbn_clean.isdigit():
        return None
    
    return isbn_clean

def format_isbn_display(isbn):
    """Format ISBN for display to users."""
    if not isbn or isinstance(isbn, float) and pd.isna(isbn):
        return "N/A"
    
    isbn_str = str(isbn)
    
    # Handle scientific notation
    if 'E' in isbn_str or 'e' in isbn_str:
        try:
            isbn_str = f"{float(isbn_str):.0f}"
        except:
            return isbn_str
    
    return isbn_str 

class RecommenderEngine:
    def __init__(self, model_name: str = DEFAULT_MODEL):
        print(f"Loading embedding model ({model_name})...")
        # Set trust_remote_code=True for HuggingFace models in some environments
        self.model = SentenceTransformer(model_name)
        self.index = None
        self.metadata = None
        self.load_index()
        
        # Proactively build index if it doesn't exist (helpful for first-time cloud deploy)
        if self.index is None and os.path.exists(DB_PATH):
            print("Index not found but database exists. Building index...")
            self.build_index()

    def build_index(self):
        """Fetches books (from API or DB), generates embeddings, and saves FAISS index."""
        print(f"Fetching books...")
        df = pd.DataFrame()
        
        # Try API first
        try:
            import requests
            response = requests.get(API_URL, params={"limit": 100000}, timeout=5)
            if response.status_code == 200:
                books = response.json()
                df = pd.DataFrame(books)
                print("Data fetched successfully from API.")
        except Exception:
            print("API unavailable. Attempting direct database access...")
            
        # Fallback to direct DB access
        if df.empty:
            if os.path.exists(DB_PATH):
                try:
                    conn = sqlite3.connect(DB_PATH)
                    df = pd.read_sql_query("SELECT * FROM books", conn)
                    conn.close()
                    print(f"Data fetched successfully from local database: {DB_PATH}")
                except Exception as e:
                    print(f"Error reading from database: {e}")
            else:
                print(f"Database not found at {DB_PATH}")
                return

        if df.empty:
            print("No books found to index.")
            return

        # Keep only records with descriptions
        df = df[df['description'].notna()]
        
        print(f"Total books to index: {len(df)}")
        
        # Combine title and description for better semantic context
        corpus = (df['title'] + " " + df['description']).tolist()
        
        print("Generating embeddings (this may take a while)...")
        embeddings = self.model.encode(corpus, show_progress_bar=True)
        
        # Initialize FAISS index
        dimension = embeddings.shape[1]
        self.index = faiss.IndexFlatL2(dimension)
        self.index.add(np.array(embeddings).astype('float32'))
        
        # Save index and metadata
        faiss.write_index(self.index, INDEX_PATH)
        self.metadata = df.to_dict('records')
        with open(METADATA_PATH, 'wb') as f:
            pickle.dump(self.metadata, f)
            
        print(f"Successfully indexed {len(df)} books and saved to {INDEX_PATH}")

    def load_index(self):
        """Loads the FAISS index and metadata from disk."""
        if os.path.exists(INDEX_PATH) and os.path.exists(METADATA_PATH):
            self.index = faiss.read_index(INDEX_PATH)
            with open(METADATA_PATH, 'rb') as f:
                self.metadata = pickle.load(f)
            print("Index and metadata loaded successfully.")
        else:
            print("Index not found. Please run build_index() first.")

    def semantic_search(self, query: str, top_k: int = 20) -> List[Dict[str, Any]]:
        """Step 1: Fast Retrieval using vector similarity."""
        if self.index is None:
            return []
        
        query_vec = self.model.encode([query]).astype('float32')
        distances, indices = self.index.search(query_vec, top_k)
        
        results = []
        for i in range(len(indices[0])):
            idx = indices[0][i]
            if idx < len(self.metadata):
                item = self.metadata[idx].copy()
                item['score'] = float(distances[0][i])
                results.append(item)
        
        return results

    def rerank_with_llm(self, query: str, candidates: List[Dict[str, Any]], model: str = "groq/llama-3.3-70b-versatile") -> List[Dict[str, Any]]:
        """Step 2: LLM-as-judge reranking."""
        if not candidates:
            return []

        # Prepare context for the LLM
        candidate_text = ""
        for i, c in enumerate(candidates):
            candidate_text += f"[{i}] Title: {c['title']}\nDescription: {c['description'][:300]}...\n\n"

        prompt = f"""
        You are an expert librarian and book critic. A user is looking for a book with this requirement: "{query}"
        
        Below are 20 potential candidates retrieved via semantic search. 
        Rank the TOP 5 most relevant books that are truly "worth picking up" for this specific request.
        
        Return only a JSON list of indices in order of relevance, like this: [3, 0, 15, 2, 7]
        
        Candidates:
        {candidate_text}
        """

        try:
            response = completion(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                response_format={ "type": "json_object" }
            )
            import json
            content = response.choices[0].message.content
            # Try to find a list in the response
            if "[" in content and "]" in content:
                # Basic extraction if the LLM didn't return pure JSON
                start = content.find("[")
                end = content.find("]") + 1
                indices = json.loads(content[start:end])
                
                reranked = []
                for idx in indices:
                    if idx < len(candidates):
                        reranked.append(candidates[idx])
                return reranked[:5]
        except Exception as e:
            print(f"Reranking failed: {type(e).__name__}: {str(e)}")
            return candidates[:5] # Fallback to retrieval order

    def get_curated_recommendations(self, query: str, candidates: List[Dict[str, Any]], model: str = "groq/llama-3.3-70b-versatile") -> List[Dict[str, Any]]:
        """Unified method to rank, explain, and score recommendations in ONE LLM call."""
        if not candidates:
            return []

        # Prepare context
        candidate_text = ""
        for i, c in enumerate(candidates):
            candidate_text += f"[{i}] Title: {c['title']}\nDescription: {c.get('description', '')[:250]}...\n\n"

        prompt = f"""
        User Requirement: "{query}"
        
        Task: Out of these 20 candidates, pick the TOP 5 most relevant books.
        For EACH of the top 5, you MUST provide:
        1. Its index from the original list.
        2. A 2-sentence explanation of why it fits the user's specific request.
        3. A match score (0-100).
        
        Return ONLY a JSON object exactly like this:
        {{
          "recommendations": [
            {{ "index": 3, "explanation": "...", "match_score": 95 }},
            ...
          ]
        }}
        
        Candidates:
        {candidate_text}
        """

        try:
            response = completion(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"}
            )
            import json
            result = json.loads(response.choices[0].message.content)
            
            final_books = []
            if 'recommendations' in result:
                for rec in result['recommendations']:
                    idx = rec.get('index')
                    if idx is not None and idx < len(candidates):
                        book = candidates[idx].copy()
                        book['explanation'] = rec.get('explanation', book.get('description', '')[:300])
                        book['match_score'] = rec.get('match_score', 0)
                        final_books.append(book)
                return final_books[:5]
        except Exception as e:
            print(f"Curation failed: {e}")
            # Fallback to simple top 5
            return candidates[:5]

    def generate_match_scores(self, query: str, final_books: List[Dict[str, Any]], model: str = "groq/llama-3.3-70b-versatile") -> List[Dict[str, Any]]:
        """Generate match scores (0-100) for each recommended book."""
        if not final_books:
            return []

        # Prepare book list for scoring
        books_text = ""
        for i, book in enumerate(final_books):
            books_text += f"[{i}] Title: {book['title']}\nAuthor: {book.get('author', 'Unknown')}\nDescription: {book['description'][:200]}...\n\n"

        prompt = f"""
        User Query: "{query}"
        
        Below are {len(final_books)} recommended books. For each book, provide a match score from 0-100 indicating how likely the user is to enjoy this book based on their query.
        
        Consider:
        - Relevance to the query
        - Quality and appeal of the book
        - How well it matches the user's interests
        
        Return ONLY a JSON object with this exact format:
        {{"scores": [{{"index": 0, "score": 95}}, {{"index": 1, "score": 88}}, ...]}}
        
        Books:
        {books_text}
        """

        try:
            response = completion(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"}
            )
            import json
            content = response.choices[0].message.content
            result = json.loads(content)
            
            # Apply scores to books
            if 'scores' in result:
                for score_data in result['scores']:
                    idx = score_data.get('index')
                    score = score_data.get('score', 0)
                    if idx is not None and idx < len(final_books):
                        final_books[idx]['match_score'] = min(100, max(0, score))  # Clamp to 0-100
            
        except Exception as e:
            print(f"Match score generation failed: {type(e).__name__}: {str(e)}")
            # Fallback: use inverse of semantic search distance as score
            for i, book in enumerate(final_books):
                # Higher rank = higher score (simple fallback)
                book['match_score'] = max(0, 100 - (i * 15))
        
        return final_books

    def fetch_book_covers(self, books: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Fetch book cover image URLs from Google Books and Open Library APIs."""
        import requests
        
        for book in books:
            isbn = book.get('isbn')
            cover_url = None
            
            # Clean and validate ISBN
            clean_isbn_val = clean_isbn(isbn)
            
            if clean_isbn_val:
                # Try Google Books API with cleaned ISBN
                try:
                    url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{clean_isbn_val}"
                    response = requests.get(url, timeout=5)
                    if response.status_code == 200:
                        data = response.json()
                        if 'items' in data and len(data['items']) > 0:
                            image_links = data['items'][0].get('volumeInfo', {}).get('imageLinks', {})
                            cover_url = image_links.get('thumbnail') or image_links.get('smallThumbnail')
                except Exception as e:
                    print(f"Google Books cover fetch failed for {clean_isbn_val}: {e}")
                
                # Fallback to Open Library
                if not cover_url:
                    try:
                        ol_url = f"https://covers.openlibrary.org/b/isbn/{clean_isbn_val}-M.jpg"
                        response = requests.head(ol_url, timeout=3)
                        if response.status_code == 200:
                            cover_url = ol_url
                    except Exception as e:
                        print(f"Open Library cover fetch failed for {clean_isbn_val}: {e}")
            
            # Fallback: Search by title and author if ISBN failed
            if not cover_url and book.get('title'):
                try:
                    query = book['title']
                    if book.get('author'):
                        query += f" {book['author'].split(',')[0]}"
                    url = f"https://www.googleapis.com/books/v1/volumes?q={query}&maxResults=1"
                    response = requests.get(url, timeout=5)
                    if response.status_code == 200:
                        data = response.json()
                        if 'items' in data and len(data['items']) > 0:
                            image_links = data['items'][0].get('volumeInfo', {}).get('imageLinks', {})
                            cover_url = image_links.get('thumbnail') or image_links.get('smallThumbnail')
                except Exception as e:
                    print(f"Title search cover fetch failed for '{book.get('title')}': {e}")
            
            # Set cover URL or fallback to placeholder
            book['cover_url'] = cover_url if cover_url else "https://via.placeholder.com/150x220.png?text=No+Cover"
        
        return books


# Singleton instance
_engine = None

def get_recommender():
    global _engine
    if _engine is None:
        _engine = RecommenderEngine()
    return _engine