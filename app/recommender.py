import os
import sqlite3
import pandas as pd
import numpy as np
import faiss
import pickle
from sentence_transformers import SentenceTransformer, util
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

# Determine default LLM based on API keys
# Priority: Gemini > Groq > OpenAI
DEFAULT_LLM_MODEL = "groq/llama-3.1-8b-instant" # Default fallback
if os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"):
    DEFAULT_LLM_MODEL = "gemini/gemini-1.5-flash"
elif os.getenv("GROQ_API_KEY"):
    DEFAULT_LLM_MODEL = "groq/llama-3.1-8b-instant"
elif os.getenv("OPENAI_API_KEY"):
    DEFAULT_LLM_MODEL = "gpt-4o-mini"

def clean_isbn(isbn):
    """Clean and validate ISBN for API calls."""
    if not isbn or isinstance(isbn, float) and pd.isna(isbn):
        return None
    
    isbn_str = str(isbn)
    
    # Handle scientific notation 
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

    def explain_recommendations(self, query: str, final_books: List[Dict[str, Any]], model: str = "groq/llama-3.3-70b-versatile") -> List[Dict[str, Any]]:
        """Step 3: Generate personalized summaries/explanations."""
        if not final_books:
            return []

        for book in final_books:
            prompt = f"""
            User Query: "{query}"
            Book Title: {book['title']}
            Description: {book['description']}
            
            Briefly explain in 2-3 sentences why this book is a perfect match for the user's query and why it's worth picking up.
            Be persuasive but honest.
            """
            try:
                response = completion(
                    model=model,
                    messages=[{"role": "user", "content": prompt}]
                )
                book['explanation'] = response.choices[0].message.content.strip()
            except Exception as e:
                # Log the error so we can see what's failing
                print(f"LLM explanation failed for '{book['title']}': {type(e).__name__}: {str(e)}")
                # Fallback to showing the FULL description if LLM fails
                book['explanation'] = book.get('description', 'No description available.')
        
        return final_books

    def generate_match_scores(self, query: str, final_books: List[Dict[str, Any]], model: str = DEFAULT_LLM_MODEL) -> List[Dict[str, Any]]:
        """Generate match scores (0-100) using Cosine Similarity."""
        if not final_books:
            return []

        try:
            # Encode user query
            query_embedding = self.model.encode(query, convert_to_tensor=True)
            
            # Encode book descriptions/titles
            book_texts = [f"{b['title']} {b.get('description', '')}" for b in final_books]
            book_embeddings = self.model.encode(book_texts, convert_to_tensor=True)
            
            # Calculate cosine similarities
            cosine_scores = util.cos_sim(query_embedding, book_embeddings)[0]
            
            # Assign scores
            for i, book in enumerate(final_books):
                # Scale from [-1, 1] to [0, 100] approximately, considering most matches will be positive
                raw_score = cosine_scores[i].item()
                # Normalize typical range 0.2-0.8 to 40-95 roughly
                score = int(max(0, min(100, raw_score * 100))) 
                
                score = min(99, int(score * 1.2) + 20)
                
                book['match_score'] = score
                
        except Exception as e:
            print(f"Cosine similarity scoring failed: {e}")
            # Fallback
            for i, book in enumerate(final_books):
                 book['match_score'] = max(0, 95 - (i * 5))
        
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
                        ol_url = f"https://covers.openlibrary.org/b/isbn/{clean_isbn_val}-M.jpg?default=false"
                        response = requests.head(ol_url, timeout=3)
                        if response.status_code == 200:
                            cover_url = ol_url
                    except Exception as e:
                        print(f"Open Library cover fetch failed for {clean_isbn_val}: {e}")
            
            # Fallback: Search by title and author if ISBN failed
            if not cover_url and book.get('title'):
                # 1. Google Books Search
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
                
                # 2. Open Library Search (Last Resort)
                if not cover_url:
                    try:
                        search_url = "https://openlibrary.org/search.json"
                        params = {'title': book['title'], 'limit': 1}
                        if book.get('author'):
                            params['author'] = book['author'].split(',')[0]
                        
                        resp = requests.get(search_url, params=params, timeout=5)
                        if resp.status_code == 200:
                            data = resp.json()
                            if data.get('docs'):
                                cover_i = data['docs'][0].get('cover_i')
                                if cover_i:
                                    cover_url = f"https://covers.openlibrary.org/b/id/{cover_i}-M.jpg"
                    except Exception as e:
                        print(f"OL Search cover fetch failed: {e}")
                                
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