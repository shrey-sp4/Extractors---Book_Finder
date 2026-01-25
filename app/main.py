from fastapi import FastAPI, HTTPException, Query
import sqlite3
import os
from typing import List, Optional
from pydantic import BaseModel
from .utils import run_book_pipeline

app = FastAPI(title="Book Serving API", description="API to fetch books with automated ingestion and transformation.")

# Adjusting DB_PATH to be robust relative to the app directory
DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '../data/books.db'))

class SyncRequest(BaseModel):
    isbn: str
    title: Optional[str] = None
    author: Optional[str] = None
    year: Optional[str] = None
    edition: Optional[str] = None
    publisher: Optional[str] = None

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@app.get("/books")
def get_books(q: Optional[str] = Query(None, description="Search query for titles or authors"), limit: int = 50):
    """
    List books or search by title/author with multi-word support.
    """
    if not os.path.exists(DB_PATH):
        raise HTTPException(status_code=500, detail="Database not found")
    
    conn = get_db_connection()
    try:
        base_query = "SELECT title, author, year, edition, publisher, isbn, description FROM books"
        params = []
        
        if q:
            # Handling multi-word search by matching each word against title or author
            words = q.strip().split()
            where_clauses = []
            for word in words:
                # Using LOWER() ensures case-insensitivity for all character types
                where_clauses.append("(LOWER(title) LIKE LOWER(?) OR LOWER(author) LIKE LOWER(?))")
                params.extend([f"%{word}%", f"%{word}%"])
            base_query += " WHERE " + " AND ".join(where_clauses)
        
        base_query += " LIMIT ?"
        params.append(limit)
        
        books = conn.execute(base_query, params).fetchall()
    finally:
        conn.close()
    
    return [dict(row) for row in books]

@app.get("/books/{isbn}")
def get_book_by_isbn(isbn: str):
    """
    Get details of a specific book by its ISBN.
    """
    if not os.path.exists(DB_PATH):
        raise HTTPException(status_code=500, detail="Database not found")
    
    conn = get_db_connection()
    try:
        query = "SELECT title, author, year, edition, publisher, isbn, description FROM books WHERE isbn = ?"
        book = conn.execute(query, (isbn,)).fetchone()
    finally:
        conn.close()
    
    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")
    
    return dict(book)

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
        # Check if exists
        cursor = conn.cursor()
        cursor.execute("SELECT isbn FROM books WHERE isbn = ?", (final_isbn,))
        exists = cursor.fetchone()
        
        if exists:
            # Update
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
            # Insert
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

@app.get("/")
def root():
    return {"message": "Welcome to the Book API. Go to /docs for the interactive API documentation."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
