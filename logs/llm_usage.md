# LLM Usage Log
This log tracks technical interactions with the LLM to solve specific challenges throughout the BookFinder pipeline lifecycle.

---

### Phase 1: Ingestion (The Collector)
* **Log 1: Performance Optimization for Large Merges**
    * **Prompt:** “I’m trying to merge two DataFrames (CSV and API data) with many rows, and it’s taking forever or crashing my RAM. Is there a faster way to do a left join on ISBNs?”
    * **Solution:** Use indexes for joining and cast the ISBN column to a more efficient type to reduce the memory footprint.
    ```python
    # Optimization suggested by LLM
    df1.set_index('isbn13', inplace=True)
    df2.set_index('isbn13', inplace=True)
    combined_df = df1.join(df2, how='left')
    ```

---

### Phase 2: Transformation (The Refiner)
* **Log 2: Handling "Dirty Data" and Null Values**
    * **Prompt:** "In my transformation step, I have books with 'Description not available'. How do I treat these as nulls in Pandas so they don't interfere with future semantic search?"
    * **Solution:** Use a replacement strategy to convert placeholder strings into actual null values for easy filtering.

---

### Phase 3: Storage (The Library)
* **Log 3: Resolving Circular Imports in SQLAlchemy**
    * **Prompt:** “I’m getting an `ImportError` because my book models and schemas are importing each other. How do I fix this properly?”
    * **Solution:** Used string forward references in the relationships to decouple the dependency graph.
    ```python
    # Relationship with forward reference
    author = relationship("Author", back_populates="books")
    ```

* **Log 4: Async Session Management**
    * **Prompt:** “My FastAPI app is leaking database connections. How do I ensure sessions close correctly after every request?”
    * **Solution:** Implemented an `async with` block within a generator function to ensure the session always closes, even on errors.

---

### Phase 4: Serving (The Gateway)
* **Log 5: Debugging 422 Unprocessable Entity Errors**
    * **Prompt:** “I keep getting 422 errors when POSTing to my /books endpoint, even though the JSON looks correct. What’s wrong?”
    * **Solution:** Diagnosed that the endpoint expected a List but received a single object. Updated the logic to handle both inputs.

* **Log 6: Configuring CORS for Local Development**
    * **Prompt:** “My frontend on localhost:3000 can’t call my backend on localhost:8000 due to CORS errors. I added the middleware but it's still failing.”
    * **Solution:** Corrected the registration order and specified explicit origins for security.
    ```python
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_methods=["*"],
    )
    ```
