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
* **Log 2: Handling API KeyErrors**
   * **Prompt:** "When I loop through the 'docs' from the API response, my code crashes because some books are missing the 'author_name' field. How do I skip these without stopping the whole loop?"
   * **Solution:** Use the .get() method to handle missing keys safely.
---

### Phase 2: Transformation (The Refiner)
* **Log 3: Handling "Dirty Data" and Null Values**
    * **Prompt:** "In my transformation step, I have books with 'Description not available'. How do I treat these as nulls in Pandas so they don't interfere with future semantic search?"
    * **Solution:** Use a replacement strategy to convert placeholder strings into actual null values for easy filtering.

* **Log 4: Stripping HTML Tags**
   * **Prompt:** "The book blurbs are full of <p>, &amp; tags. Can you give me a solution that cleans all HTML but keeps the text?"
   * **Solution:** Use a regex pattern to find anything between brackets and replace it with an empty string.

---

### Phase 3: Storage (The Library)
* **Log 5: Resolving Circular Imports in SQLAlchemy**
    * **Prompt:** “I’m getting an `ImportError` because my book models and schemas are importing each other. How do I fix this properly?”
    * **Solution:** Used string forward references in the relationships to decouple the dependency graph.
    ```python
    # Relationship with forward reference
    author = relationship("Author", back_populates="books")
    ```

* **Log 6: Managing Database Connections in FastAPI**
   * **Prompt:** "I noticed my database is getting too many open connections and slowing down. How do I make sure every session is closed automatically after a request is finished?"
   * **Solution:** Use a generator with an async with block to ensure the session is always closed in the finally block.
    ```Python
   
   # Session management in database.py
   async def get_db():
       async with AsyncSessionLocal() as session:
           try:
               yield session
           finally:
               await session.close()
    ```
---

### Phase 4: Serving (The Gateway)
* **Log 7: Debugging 422 Unprocessable Entity Errors**
    * **Prompt:** “I keep getting 422 errors when POSTing to my /books endpoint, even though the JSON looks correct. What’s wrong?”
    * **Solution:** Diagnosed that the endpoint expected a List but received a single object. Updated the logic to handle both inputs.

* **Log 8: Configuring CORS for Local Development**
    * **Prompt:** “My frontend on localhost:3000 can’t call my backend on localhost:8000 due to CORS errors. I added the middleware but it's still failing.”
    * **Solution:** Corrected the registration order and specified explicit origins for security.
    ```python
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_methods=["*"],
    )
    ```
