# LLM Usage Log
This log tracks technical interactions with the LLM to solve challenges and optimize the BookFinder data pipeline.

---

### Phase 1: Ingestion (The Collector)
* **Log 1: Data Ingestion and Column Mapping**
    * [cite_start]**Prompt:** "I'm building a collector to read data from a CSV and the OpenLibrary API. One uses 'book_title' and the other uses 'title'. How should I handle this inconsistency in Pandas before storing the data in SQLite?" [cite: 10, 11]
    * [cite_start]**Solution:** Use a mapping dictionary with the `.rename()` method to standardize the schema. [cite: 7]
    ```python
    column_mapping = {'book_title': 'title', 'ISBN_13': 'isbn13'}
    df_csv = df_csv.rename(columns=column_mapping)
    ```

* **Log 2: Pandas Performance Optimization**
    * **Prompt:** “I’m trying to merge two DataFrames with 1M+ rows each, and it’s taking long or is crashing my RAM. Give me a faster way to do a left join on ISBNs.”
    * [cite_start]**Solution:** Set the joining column as the index to speed up the lookup. [cite: 7]
    ```python
    df1.set_index('isbn13', inplace=True)
    df2.set_index('isbn13', inplace=True)
    combined_df = df1.join(df2, how='left')
    ```

---

### Phase 2: Transformation (The Refiner)
* **Log 3: Data Transformation and Cleaning**
    * [cite_start]**Prompt:** "I am cleaning book descriptions for a semantic search project. Many entries contain HTML tags and encoding errors. Can you provide a Python function to strip these?" [cite: 13, 14]
    * [cite_start]**Solution:** Use `re` and `html` libraries for text normalization. [cite: 7]
    ```python
    import re
    import html

    def clean_text(raw_html):
        cleanr = re.compile('<.*?>')
        cleantext = re.sub(cleanr, '', html.unescape(raw_html))
        return cleantext if "Description not available" not in cleantext else None
    ```

---

### Phase 3: Storage (The Library)
* **Log 4: Circular Dependency Resolution**
    * [cite_start]**Prompt:** “I’m getting a ImportError: cannot import name 'Book' from partially initialized module 'models.book' when trying to run my FastAPI app. How do I fix this?” [cite: 21]
    * [cite_start]**Solution:** Use string forward references in SQLAlchemy relationships to decouple the models. [cite: 36, 38]
    ```python
    # In models/author.py
    books = relationship("Book", back_populates="author")
    ```

* **Log 5: Async SQLAlchemy Session Management**
    * [cite_start]**Prompt:** “My FastAPI app is leaking database connections. How do I ensure sessions close correctly?” [cite: 42]
    * [cite_start]**Solution:** Use an `async with` block within a generator function. [cite: 43, 44]
    ```python
    async def get_db():
        async with AsyncSessionLocal() as session:
            try:
                yield session
            finally:
                await session.close()
    ```

---

### Phase 4: Serving (The Gateway)
* **Log 6: Debugging FastAPI 422 Errors**
    * [cite_start]**Prompt:** “I keep getting 422 errors when POSTing to my /books endpoint. The log says body -> 0 -> isbn13 is missing.” [cite: 50, 51]
    * [cite_start]**Solution:** Ensure the Pydantic schema matches the incoming JSON structure (List vs Object). [cite: 52, 53]
    ```python
    @app.post("/books/")
    async def create_books(books: List[BookCreate]): # Expecting a list
        return await service.bulk_insert(books)
    ```

* **Log 7: FastAPI CORS Middleware Configuration**
    * [cite_start]**Prompt:** “My frontend on localhost:3000 can’t call my backend on localhost:8000 due to CORS errors.” [cite: 55, 56]
    * [cite_start]**Solution:** Correctly configure `CORSMiddleware` with explicit origins. [cite: 57, 58]
    ```python
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_methods=["*"],
    )
    ```
