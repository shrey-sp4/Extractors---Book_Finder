# LLM Usage Log

This document logs interactions with the LLM during the development of the Book Finder.

---

## 1. Concurrent API Fetching for Book Enrichment

**User Prompt:**
Help me speed up my book-ingestion pipeline by running API calls concurrently instead of one book at a time.

**LLM Response:**
For I/O-bound work like HTTP requests, `ThreadPoolExecutor` allows multiple API calls to be in flight simultaneously. Below is the exact concurrency pattern used in the project.

```python
MAX_WORKERS = 30 

with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
    future_to_idx = {
        executor.submit(process_book, idx, row): idx 
        for idx, row in df.iterrows()
    }
    
    completed_count = 0
    for future in concurrent.futures.as_completed(future_to_idx):
        idx, desc = future.result()
        if desc:
            df.loc[idx, 'description'] = desc
        
        completed_count += 1
        if completed_count % 500 == 0:
            print(f"Processed {completed_count}/{len(df)} books...")
```

This allows up to 30 books to be processed concurrently, significantly reducing total runtime for large datasets.

---

## 2. Fetching Scholarly Abstracts from OpenAlex

**User Prompt:**
Help me write a function to fetch abstracts or keywords for a book using its ISBN from the OpenAlex API, openalex.org.

**LLM Response:**
The function queries OpenAlex using an ISBN filter. If an abstract is available, it is reconstructed from the inverted index; otherwise, high-scoring concepts are used as fallback keywords.

```python
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

```
---

## 3. Reconstructing Abstract Text from OpenAlex Inverted Index

**User Prompt:**
Help me write a utility function to reconstruct a readable abstract string from OpenAlex’s `abstract_inverted_index` format.

**LLM Response:**
OpenAlex stores abstracts as a mapping from words to their positional indices. The function below reverses this structure by sorting words based on position and rejoining them into a coherent sentence.

```python
def reconstruct_openalex_abstract(inverted_index):
    if not inverted_index:
        return None
    word_index = []
    for word, positions in inverted_index.items():
        for pos in positions:
            word_index.append((pos, word))
    word_index.sort()
    return ' '.join([word for _, word in word_index])
```

This reconstruction step is necessary before abstracts can be stored, displayed, or embedded for downstream NLP tasks.

---

## 4. Fetching Book Descriptions from Google Books Using Title and Author

**User Prompt:**
Help me write a fallback function that fetches book descriptions from Google Books when ISBN-based lookup fails.

**LLM Response:**
This function performs a broad search using the book title and (optionally) the first listed author, returning the top match description.

```python
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
```

This acts as a robust fallback during ingestion when structured identifiers are missing.

---

## 5. Text Cleaning: Encoding Fixes and HTML Removal

**User Prompt:**
Give me a safe preprocessing block to clean API-returned book descriptions before storing them.

**LLM Response:**
The recommended preprocessing pipeline fixes encoding corruption (mojibake) and removes HTML markup while preserving readable text.

```python
import ftfy
from bs4 import BeautifulSoup

def clean_text(text):
    text = ftfy.fix_text(str(text))
    soup = BeautifulSoup(text, 'html.parser')
    return soup.get_text()
```

`ftfy` repairs Unicode and character encoding issues, while BeautifulSoup strips HTML tags. This order ensures that entities and smart punctuation are handled correctly.

---

## 6. Running a FastAPI Application with Uvicorn

**User Prompt:**
Help me write the entry-point code to run my FastAPI Book API locally.

**LLM Response:**
The following code defines a root endpoint and starts the FastAPI app using Uvicorn. This matches the project setup exactly.

```python
@app.get("/")
def root():
    return {"message": "Welcome to the Book API. Go to /docs for the interactive API documentation."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
```

This ensures the server only starts when the file is executed directly.

---

## 7. Writing a Client Script to Test the Book API

**User Prompt:**
Help me write a small Python script to verify whether my FastAPI server is running and to fetch a limited number of recent books.

**LLM Response:**
A simple `requests`-based script can be used to check API availability and handle cases where the server is not running yet.

```python
import requests

try:
    response = requests.get("http://127.0.0.1:8000/books/recent?limit=5")
    if response.status_code == 200:
        print(response.json())
    else:
        print("API not reachable or error:", response.status_code)
except Exception as e:
    print("API likely not running yet. Run the uvicorn command properly.")
```

This is useful as a lightweight smoke test during local development before integrating the API into downstream systems.

---

## 8. Implementing a `/sync` Endpoint for Ingestion → Transformation → Storage

**User Prompt:**
Help me implement a FastAPI POST endpoint that accepts book details, runs it through an ingestion and transformation pipeline, and then performs an update or insert into the SQLite database.

**LLM Response:**
The `/sync` endpoint below coordinates three stages: pipeline execution, existence checking, and conditional insert/update using SQL `COALESCE` for partial updates.

```python
@app.post("/sync")
def sync_data(request: SyncRequest):
    """
    Enters a record for a new book and passes it through the full
    pipeline (Ingestion -> Transformation -> Storage).
    """
    if not os.path.exists(DB_PATH):
        raise HTTPException(status_code=500, detail="Database not found")

    # 1. Running Pipeline (Ingestion + Transformation)
    pipeline_result = run_book_pipeline(
        isbn=request.isbn,
        title=request.title,
        author=request.author
    )
    
    final_isbn = pipeline_result["isbn"] or request.isbn
    description = pipeline_result["description"]
    
    # 2. Storage
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT isbn FROM books WHERE isbn = ?", (final_isbn,))
        exists = cursor.fetchone()
        
        if exists:
            query = """
                UPDATE books
                SET title = COALESCE(?, title),
                    author = COALESCE(?, author),
                    year = COALESCE(?, year),
                    edition = COALESCE(?, edition),
                    publisher = COALESCE(?, publisher),
                    description = COALESCE(?, description)
                WHERE isbn = ?
            """
            conn.execute(query, (
                request.title, request.author, request.year,
                request.edition, request.publisher, description, final_isbn
            ))
        else:
            query = """
                INSERT INTO books (title, author, year, edition, publisher, isbn, description)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """
            conn.execute(query, (
                request.title, request.author, request.year,
                request.edition, request.publisher, final_isbn, description
            ))
        
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        conn.close()
    
    return {
        "status": "success",
        "message": f"Book {final_isbn} processed through pipeline and saved.",
        "data": {
            "isbn": final_isbn,
            "description_found": description is not None
        }
    }
```

This endpoint acts as the primary integration point between external data sources and persistent storage.
