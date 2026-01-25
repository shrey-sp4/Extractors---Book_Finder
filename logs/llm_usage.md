# LLM Usage Log

This log tracks technical interactions with the LLM to solve certain challenges.

---

### Log 1: Circular Dependency Resolution
**Prompt:**  
"I'm getting a `ImportError: cannot import name 'Book' from partially initialized module 'models.book'` when trying to run my FastAPI app. It seems like `models.book` and `schemas.book` are importing each other. How do I fix this properly without making the code a mess?"

**Solution:**  
Identified a classic circular dependency where the SQLAlchemy model and Pydantic schema were tightly coupled. Recommended:
1. Using string forward references in SQLAlchemy relationships: `relationship("Author", back_populates="books")`.
2. Moving shared logic or shared base classes to a neutral `base.py` or using `TYPE_CHECKING` blocks for type hints.
3. Decoupling the dependency graph by ensuring schemas only import what they absolutely need for validation.

---

### Log 2: FastAPI Async SQLAlchemy Session Management
**Prompt:**  
"My FastAPI app is leaking database connections when using `asyncpg`. I'm using `Depends(get_db)` but it seems like sessions aren't closing. Here is my current generator..."

**Solution:**  
Refined the dependency injection pattern to ensure the session is always closed, even on exceptions, using an `async with` block within the generator:
```python
async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
```

---

### Log 3: Pandas Performance Optimization for Large Datasets
**Prompt:**  
"I'm trying to merge two DataFrames with 1M+ rows each, and it's taking forever or crashing my RAM. Is there a faster way to do a left join on ISBNs?"

**Solution:**  
Proposed several optimization strategies:
1. Ensuring the join key (`isbn13`) is the index for both DataFrames before calling `.join()`.
2. Casting the ISBN column to a more efficient type (e.g., categorical or integer if valid) to reduce memory footprint.
3. Using `pd.merge(how='left', on='isbn13', copy=False)` to minimize memory duplication.
4. If scaling further, suggested using `dask` or processing in chunks.

---

### Log 4: Debugging FastAPI 422 Unprocessable Entity
**Prompt:**  
"I keep getting 422 errors when POSTing to my `/books` endpoint. The error log says `body -> 0 -> isbn13` is missing, but I'm definitely sending it in the JSON. What's wrong?"

**Solution:**  
Diagnosed that the endpoint was expecting a `List[BookCreate]` but the client was sending a single object. Showed how to either wrap the object in a list on the client side or update the Pydantic model to handle single object inputs correctly. Also suggested adding a custom exception handler for `RequestValidationError` to return more descriptive error messages to the client.

---

### Log 5: FastAPI CORS Middleware Configuration
**Prompt:**  
"My frontend on `localhost:3000` can't call my backend on `localhost:8000`. I get a CORS error. I tried adding the middleware but it's still not working."

**Solution:**  
Corrected the order of middleware registration (FastAPI processes them in reverse order of addition) and specified explicit origins instead of using `allow_origins=["*"]` when credentials are required. 
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```