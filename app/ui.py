import streamlit as st
import os
import time
from recommender import get_recommender, format_isbn_display
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(page_title="Book Finder", page_icon="📚", layout="wide")

@st.cache_resource(show_spinner=False)
def get_cached_recommender():
    return get_recommender()

@st.cache_data(show_spinner=False)
def get_recommendations(query, api_key):
    recommender = get_cached_recommender()
    
    # Step 1: Retrieval (FAST)
    candidates = recommender.semantic_search(query)
    
    # Step 2: Curated Curation (Rank + Explain + Score)
    if api_key:
        final_books = recommender.get_curated_recommendations(query, candidates)
    else:
        final_books = candidates[:5]
    
    # Step 3: Fetch Book Covers
    final_books = recommender.fetch_book_covers(final_books)
    return final_books

# Custom CSS for Premium Library UI
st.markdown("""
<style>
    /* Import Google Fonts */
    @import url('https://fonts.googleapis.com/css2?family=Merriweather:wght@700&family=Inter:wght@400;500;600&display=swap');
    
    /* Global Styles */
    .stApp {
        background-color: #F8FAFC;
        color: #1E293B;
        font-family: 'Inter', sans-serif;
    }
    
    /* Header Container */
    .header-container {
        padding: 3rem 1rem;
        background-color: #1E293B;
        color: white;
        text-align: center;
        margin: -4.5rem -5rem 2rem -5rem;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    }
    
    h1 {
        font-family: 'Merriweather', serif;
        font-weight: 700;
        font-size: 3rem !important;
        margin-bottom: 0.5rem !important;
        color: white !important;
    }
    
    .subtitle {
        color: #94A3B8;
        font-size: 1.1rem;
        max-width: 600px;
        margin: 0 auto;
    }
    
    /* Book Card Component */
    .book-card {
        background: white;
        border: 1px solid #E2E8F0;
        border-radius: 12px;
        padding: 1.5rem;
        margin-bottom: 1.5rem;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
        display: flex;
        gap: 1.5rem;
        align-items: flex-start;
    }
    
    .book-card img {
        width: 140px;
        border-radius: 6px;
        box-shadow: 1px 1px 5px rgba(0,0,0,0.1);
    }
    
    .book-info {
        flex: 1;
    }
    
    .match-label {
        font-weight: 600;
        color: #0F172A;
        font-size: 0.8rem;
        background: #F1F5F9;
        padding: 0.2rem 0.6rem;
        border-radius: 4px;
        display: inline-block;
        margin-bottom: 0.4rem;
    }
    
    .high-match { color: #059669; background: #ECFDF5; }
    
    .book-title {
        font-family: 'Merriweather', serif;
        font-size: 1.3rem;
        margin-bottom: 0.2rem;
        color: #0F172A;
    }
    
    .book-author {
        color: #64748B;
        font-size: 0.85rem;
        margin-bottom: 0.75rem;
    }
    
    .book-explanation {
        background-color: #F8FAFC;
        border-left: 3px solid #1E293B;
        padding: 0.75rem 1rem;
        margin-top: 0.5rem;
        font-size: 0.9rem;
        line-height: 1.5;
        color: #334155;
        border-radius: 0 4px 4px 0;
    }
    
    /* Hide default elements */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    
    /* Remove gaps between Streamlit vertical blocks to stop white bars */
    [data-testid="stVerticalBlock"] > div {
        padding-top: 0rem !important;
        padding-bottom: 0rem !important;
    }
</style>
""", unsafe_allow_html=True)

st.markdown("""
    <div class="header-container">
        <h1>Book Finder</h1>
        <p class="subtitle">A curated literary discovery engine powered by semantic intelligence</p>
    </div>
""", unsafe_allow_html=True)

# API Key check
api_key = os.getenv("GROQ_API_KEY") or os.getenv("OPENAI_API_KEY")

query = st.text_input("", placeholder="Search by theme, mood, or niche topic (e.g., 'existential sci-fi about memory')", label_visibility="collapsed")

if query:
    recommender = get_cached_recommender()
    
    if recommender.index is None:
        st.error("Engine failure: Discovery index not available.")
    else:
        with st.status("🔍 Curating your collection...", expanded=False) as status:
            final_books = get_recommendations(query, api_key)
            status.update(label="✨ Collection Curated", state="complete")

        st.write("") # Spacer

        for book in final_books:
            match_score_html = ""
            if 'match_score' in book:
                score = int(book['match_score'])
                match_class = "high-match" if score >= 85 else ""
                match_score_html = f'<div class="match-label {match_class}">{score}% Match</div>'

            formatted_isbn = format_isbn_display(book.get('isbn'))
            author = book.get('author', 'Unknown Author')
            explanation = book.get('explanation', book.get('description', '')[:300] + "...")
            cover_url = book.get('cover_url', 'https://via.placeholder.com/150x220.png?text=No+Cover')

            card_html = f"""
            <div class="book-card">
                <img src="{cover_url}" />
                <div class="book-info">
                    {match_score_html}
                    <div class="book-title">{book['title']}</div>
                    <div class="book-author">By {author} | ISBN: {formatted_isbn}</div>
                    <div class="book-explanation">{explanation}</div>
                </div>
            </div>
            """
            st.markdown(card_html, unsafe_allow_html=True)
