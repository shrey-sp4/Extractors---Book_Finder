# Book Finder

A complete pipeline to ingest, transform, store, and serve book data with automated enrichment.

## Project Structure
- `app/`: FastAPI application and modular pipeline logic (`utils.py`).
- `data/`: SQLite database (`books.db`) and CSV data files.
- `notebooks/`: Sequential Jupyter notebooks for bulk processing.
- `logs/`: Project logs and history.

## Data Schema
The system stores data in a SQLite database (`data/books.db`) with the following structure for the `books` table:

| Column | Type | Description |
| :--- | :--- | :--- |
| `title` | TEXT | The title of the book. |
| `author` | TEXT | The author or editor. |
| `year` | SMALLINT | Publication year. |
| `edition` | TEXT | Edition or volume information. |
| `publisher` | TEXT | Publisher and place of publication. |
| `isbn` | TEXT (UNIQUE) | Cleaned ISBN-10 or ISBN-13 (Primary Key equivalent). |
| `description`| TEXT | Enriched and cleaned book description. |

## Data Pipeline
The project supports two modes of data processing:

### 1. Bulk Ingestion (Notebooks)
Used for processing large datasets (e.g., the initial 36k books). Run these in order:
1. `01_ingestion.ipynb`: Fetches raw data and initial descriptions.
2. `02_transformation.ipynb`: Cleans text and normalizes ISBNs.
3. `03_storage.ipynb`: Creates the database and loads the cleaned data.

### 2. Single-item Synchronization (API)
Used for adding or updating individual books with automated enrichment.
- **Trigger**: Send a `POST` request to `/sync` with the book's ISBN.
- **Process**: The system automatically runs the full pipeline (Ingestion -> Transformation -> Storage) for that specific record.

## Data Statistics
- **Initial Records**: 36,358 (Raw dataset)
- **Cleaned Records**: 10,921 (After deduplication and description ingestion)

## Setup & Execution
1. **Install Dependencies**:
   ```bash
   pip install pandas fastapi uvicorn beautifulsoup4 requests ftfy
   ```
2. **Start the API**:
   ```bash
   uvicorn app.main:app --reload
   ```
3. **API Documentation**: Access `http://127.0.0.1:8000/docs` to test endpoints like `/books`, `/books/{isbn}`, and `/sync`.
