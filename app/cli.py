import argparse
import requests
import sys
import subprocess
import time
from .pipeline import run_full_pipeline, run_ingestion, run_transformation, run_storage, get_database_stats
from .pipeline import run_full_pipeline, run_ingestion, run_transformation, run_storage, get_database_stats

API_BASE_URL = "http://127.0.0.1:8000"

def get_args():
    parser = argparse.ArgumentParser(description="Book Finder CLI Helper")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Search command
    search_parser = subparsers.add_parser("search", help="Search for books by title or author")
    search_parser.add_argument("query", help="Search query")

    # Details command
    details_parser = subparsers.add_parser("details", help="Get details for a specific ISBN")
    details_parser.add_argument("isbn", help="Book ISBN")

    # Sync command
    sync_parser = subparsers.add_parser("sync", help="Ingest a new book by ISBN")
    sync_parser.add_argument("isbn", help="Book ISBN")
    sync_parser.add_argument("--title", help="Optional title hint")
    sync_parser.add_argument("--author", help="Optional author hint")

    # Serve command
    subparsers.add_parser("serve", help="Start the FastAPI server")

    # Setup command
    setup_parser = subparsers.add_parser("setup", help="Run the bulk data pipeline (Ingest -> Transform -> Store)")
    setup_parser.add_argument("--stage", choices=["all", "ingest", "transform", "store"], default="all", help="Specific stage to run")
    setup_parser.add_argument("--limit", type=int, help="Limit number of books to process (for testing)")

    # Stats command
    subparsers.add_parser("stats", help="Show dynamic database statistics")

    # Index command
    subparsers.add_parser("index", help="Build the vector search index for the recommender")

    # Guide command
    subparsers.add_parser("guide", help="Show a quick start guide")

    return parser.parse_args()

def search_books(query):
    try:
        response = requests.get(f"{API_BASE_URL}/books", params={"q": query})
        response.raise_for_status()
        books = response.json()
        if not books:
            print(f"No books found for '{query}'.")
            return
        
        print(f"\nFound {len(books)} books:")
        print("-" * 50)
        for b in books:
            print(f"Title:  {b.get('title')}")
            print(f"Author: {b.get('author')}")
            print(f"ISBN:   {b.get('isbn')}")
            print("-" * 50)
    except requests.exceptions.ConnectionError:
        print("Error: Could not connect to the API. Is the server running? Use 'python app/cli.py serve' to start it.")

def get_details(isbn):
    try:
        response = requests.get(f"{API_BASE_URL}/books/{isbn}")
        if response.status_code == 404:
            print(f"Book with ISBN {isbn} not found in database.")
            return
        response.raise_for_status()
        b = response.json()
        
        print("\nBook Details")
        print(f"Title:       {b.get('title')}")
        print(f"Author:      {b.get('author')}")
        print(f"Year:        {b.get('year')}")
        print(f"Publisher:   {b.get('publisher')}")
        print(f"Description: {b.get('description')[:200]}..." if b.get('description') else "No description")
        print("-" * 20)
    except requests.exceptions.ConnectionError:
        print("Error: Could not connect to the API.")

def sync_book(isbn, title=None, author=None):
    try:
        print(f"Triggering sync for ISBN {isbn}.")
        payload = {"isbn": isbn}
        if title: payload["title"] = title
        if author: payload["author"] = author
        
        response = requests.post(f"{API_BASE_URL}/sync", json=payload)
        response.raise_for_status()
        data = response.json()
        print(f"Success! {data['message']}")
        print(f"Fetched Title: {data['data'].get('title')}")
    except requests.exceptions.ConnectionError:
        print("Error: Could not connect to the API.")

def start_server():
    print("Starting FastAPI server with uvicorn.")
    try:
        # We use subprocess to run uvicorn
        subprocess.run(["uvicorn", "app.main:app", "--reload"])
    except KeyboardInterrupt:
        print("\nStopping server.")

def run_setup(stage, limit):
    if stage == "all":
        run_full_pipeline(limit=limit)
    elif stage == "ingest":
        run_ingestion(limit=limit)
    elif stage == "transform":
        run_transformation()
    elif stage == "store":
        run_storage()

def show_guide():
    guide_text = """
Welcome to the Book Finder CLI Helper!

HOW TO USE?

1. Start the server:
   python app/cli.py serve

2. Search for a book:
   python app/cli.py search "Harry Potter"

3. Add/Sync a new book (it will fetch details from the web):
   python app/cli.py sync 9780747532743

4. View details for an ISBN:
   python app/cli.py details 9780747532743

Note: The API server must be running for search, details, and sync to work.
"""
    print(guide_text)

def main():
    args = get_args()
    if args.command == "search":
        search_books(args.query)
    elif args.command == "details":
        get_details(args.isbn)
    elif args.command == "sync":
        sync_book(args.isbn, args.title, args.author)
    elif args.command == "serve":
        start_server()
    elif args.command == "setup":
        run_setup(args.stage, args.limit)
    elif args.command == "stats":
        get_database_stats()
    elif args.command == "index":
        from .recommender import get_recommender
        get_recommender().build_index()
    elif args.command == "guide":
        show_guide()
    else:
        show_guide()

if __name__ == "__main__":
    main()