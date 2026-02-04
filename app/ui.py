import streamlit as st
import os
import time
from recommender import get_recommender, format_isbn_display
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(page_title="Book Finder", page_icon="📚", layout="wide")

import streamlit as st
import os
import time
from recommender import get_recommender, format_isbn_display
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(page_title="Book Finder", page_icon="📚", layout="wide")

@st.cache_resource
def get_cached_recommender():
    return get_recommender()

@st.cache_data(show_spinner=False)
def get_recommendations(query, api_key):
    recommender = get_cached_recommender()
    
    # Step 1: Retrieval
    candidates = recommender.semantic_search(query)
    
    # Step 2: Reranking
    if api_key:
        final_books = recommender.rerank_with_llm(query, candidates)
        # Step 3: Explanation
        final_books = recommender.explain_recommendations(query, final_books)
        # Step 4: Match Scores
        final_books = recommender.generate_match_scores(query, final_books)
    else:
        final_books = candidates[:5]
    
    # Step 5: Fetch Book Covers
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
        padding: 2rem;
        margin-bottom: 1.5rem;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    }
    
    .book-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
    }
    
    /* Match Score Styling */
    .match-label {
        font-weight: 600;
        color: #0F172A;
        font-size: 0.9rem;
        background: #F1F5F9;
        padding: 0.25rem 0.75rem;
        border-radius: 6px;
        display: inline-block;
        margin-bottom: 0.5rem;
    }
    
    .high-match { color: #059669; background: #ECFDF5; }
    .med-match { color: #D97706; background: #FFFBEB; }
    
    /* Image Styling */
    .book-cover {
        border-radius: 6px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    }
    
    /* Typography */
    .book-title {
        font-family: 'Merriweather', serif;
        font-size: 1.5rem;
        margin-bottom: 0.25rem;
        color: #0F172A;
    }
    
    .book-meta {
        color: #64748B;
        font-size: 0.85rem;
        margin-bottom: 1rem;
    }
    
    .book-explanation {
        background-color: #F8FAFC;
        border-left: 4px solid #475569;
        padding: 1rem;
        margin-top: 1rem;
        font-size: 0.95rem;
        line-height: 1.6;
        color: #334155;
        border-radius: 0 8px 8px 0;
    }
    
    /* Hide default elements */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    
    /* Removed white bars by modifying st.divider appearance */
    hr {
        border-top: 1px solid #E2E8F0 !important;
        opacity: 0.3;
        margin: 1.5rem 0 !important;
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
if not api_key:
    st.info("💡 Pro Tip: Set an LLM API key in your environment to enable personalized reranking and explanations.")

query = st.text_input("", placeholder="Search by theme, mood, or niche topic (e.g., 'existential sci-fi about memory')", label_visibility="collapsed")

if query:
    recommender = get_cached_recommender()
    
    if recommender.index is None:
        st.error("Engine failure: Discovery index not available. Please initialize the database.")
    else:
        with st.status("🔍 Curating your collection...", expanded=False) as status:
            final_books = get_recommendations(query, api_key)
            status.update(label="✨ Collection Curated", state="complete")

        st.write("") # Spacer

        for book in final_books:
            st.markdown('<div class="book-card">', unsafe_allow_html=True)
            
            col1, col2 = st.columns([1, 4])
            
            with col1:
                cover_url = book.get('cover_url', 'https://via.placeholder.com/150x220.png?text=No+Cover')
                st.image(cover_url, use_container_width=True)
            
            with col2:
                # Top row: Match Score
                if 'match_score' in book:
                    score = int(book['match_score'])
                    match_class = "high-match" if score >= 85 else ("med-match" if score >= 70 else "")
                    st.markdown(f'<div class="match-label {match_class}">{score}% Match</div>', unsafe_allow_html=True)
                
                # Title & Meta
                st.markdown(f'<div class="book-title">{book["title"]}</div>', unsafe_allow_html=True)
                
                formatted_isbn = format_isbn_display(book.get('isbn'))
                author = book.get('author', 'Unknown Author')
                st.markdown(f'<div class="book-meta">By {author} | ISBN: {formatted_isbn}</div>', unsafe_allow_html=True)
                
                # Explanation/Description
                if 'explanation' in book:
                    st.markdown(f'<div class="book-explanation">{book["explanation"]}</div>', unsafe_allow_html=True)
                else:
                    desc = book.get('description', 'No description available.')
                    st.markdown(f'<div class="book-explanation">{desc[:400]}...</div>', unsafe_allow_html=True)
                
                # Additional Meta details if they look clean
                year = book.get('year')
                publisher = book.get('publisher', '')
                if year or publisher:
                    extra_meta = f"{int(year) if year else ''} • {publisher.strip(',') if publisher else ''}"
                    st.caption(extra_meta.strip(' • '))

            st.markdown('</div>', unsafe_allow_html=True)

