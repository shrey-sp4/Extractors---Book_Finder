# LLM Usage Log
This log tracks technical interactions with the LLM to solve specific challenges throughout the BookFinder pipeline lifecycle.

---

### Phase 1: Ingestion (The Collector)
* **Log 1: Parsing Nested JSON from OpenLibrary API**
   * **Prompt:** "I'm using the requests library to get book data from OpenLibrary. The ISBNs are inside a nested list like doc['isbn'][0]. How can I safely extract the first ISBN without the loop crashing when a book doesn't have an ISBN key?"
   * **Solution:** Use the .get() method with a fallback to an empty list to prevent KeyError.
   ```python  
   isbn = book_data.get('isbn', [None])[0]
  ```
   
* **Log 2: Concatenating API and CSV DataFrames**
   * **Prompt:** "I have one DataFrame from a CSV and another from an API. They have different columns. How do I combine them into one master DataFrame using Pandas so I can start the cleaning phase?"
   * **Solution:** Suggested using pd.concat() with axis=0 and ensuring the column names are aligned beforehand.   
---

### Phase 2: Transformation (The Refiner)
* **Log 3: Filtering "Dirty" Descriptions**
   * **Prompt:** "In my transformation step, I'm seeing books where the description is just the string 'Description not available'. I need to treat these as nulls so I can drop them. What's the best way to do this in Pandas?"
   * **Solution:** Use .replace() to convert the specific string to None or np.nan, followed by .dropna().
     ```python
      df['description'] = df['description'].replace('Description not available', None)
      df = df.dropna(subset=['description'])
     ```
     
* **Log 4: Fixing Text Encoding and HTML Tags**
   * **Prompt:** "My book blurbs have HTML tags like '<p>' and symbols like '&amp;'. Can you help me write a function to clean the text so it's ready for an embedding model?"
   * **Solution:** Provided a script using re.sub() for tags and html.unescape() for character references.

---

### Phase 3: Storage (The Library)
* **Log 5: Implementing SQLite Upsert Logic**
   * **Prompt:** "I'm storing my cleaned books in a SQLite table. If I run my ingestion script twice, I get a 'Unique Constraint' error on the ISBN. How can I make SQL just ignore the duplicates?"
   * **Solution:** Suggested using the INSERT OR IGNORE syntax in the SQL execution string.
    ```python
    cursor.execute("INSERT OR IGNORE INTO books (isbn, title, description) VALUES (?, ?, ?)", ...)
    ```

* **Log 6: FastAPI Row to Dictionary Conversion**
   * **Prompt:** "I'm building my /books endpoint with FastAPI and sqlite3. The database returns tuples, but I need to return JSON objects with keys like 'title' and 'isbn'. How do I fix this?"
   * **Solution:** Suggested setting conn.row_factory = sqlite3.Row so that query results can be converted to dictionaries easily..
    ```Python
   conn.row_factory = sqlite3.Row
   cursor = conn.cursor()
   rows = cursor.fetchall()
   return [dict(row) for row in rows]
    ```
---

### Phase 4: Serving (The Gateway)
* **log 7: Uvicorn Server Setup**
   * **Prompt:** "How do I run my FastAPI app so it reloads automatically when I change the code?"
   * **Solution:** Recommended running the server via the command line using uvicorn main:app --reload.
