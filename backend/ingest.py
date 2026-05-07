import os
import json
import time
import chromadb
import google.generativeai as genai
from dotenv import load_dotenv

# SETUP: Load .env and configure Gemini
load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    print("Error: GEMINI_API_KEY not found in environment variables.")
    exit(1)

genai.configure(api_key=api_key)

# Create a ChromaDB PersistentClient stored at path ./chroma_db
chroma_client = chromadb.PersistentClient(path="./chroma_db")

# Create or get collection with cosine metric
collection = chroma_client.get_or_create_collection(
    name="doitchatbot",
    metadata={"hnsw:space": "cosine"}
)

def get_chunks(text, chunk_size=400, overlap=80):
    """Splits text into chunks of `chunk_size` words with `overlap` word overlap."""
    words = text.split()
    chunks = []
    i = 0
    while i < len(words):
        chunk_words = words[i:i + chunk_size]
        chunk_text = " ".join(chunk_words)
        
        # Skip any chunk shorter than 60 characters
        if len(chunk_text) >= 60:
            chunks.append(chunk_text)
            
        i += (chunk_size - overlap)
    return chunks

def get_embedding(text):
    """Uses Gemini model to embed text, truncating to 8000 characters with retry logic."""
    # Truncate text to 8000 characters before embedding
    truncated_text = text[:8000]
    
    try:
        result = genai.embed_content(
            model="models/gemini-embedding-2",
            content=truncated_text
        )
        return result['embedding']
    except Exception as e:
        # If it fails, wait 2 seconds and retry once
        time.sleep(2)
        try:
            result = genai.embed_content(
                model="models/gemini-embedding-2",
                content=truncated_text
            )
            return result['embedding']
        except Exception as e_retry:
            print(f"Error embedding text after retry: {e_retry}")
            return None

def main():
    pages_file = "pages.json"
    if not os.path.exists(pages_file):
        # Fall back to parent directory in case it was run from the root
        if os.path.exists("../pages.json"):
            pages_file = "../pages.json"
        else:
            print(f"Error: {pages_file} not found. Run the crawler first.")
            return

    with open(pages_file, 'r', encoding='utf-8') as f:
        pages = json.load(f)

    total_pages = len(pages)
    total_chunks_stored = 0

    for page_index, page in enumerate(pages):
        url = page.get("url", "")
        title = page.get("title", "")
        # Check both 'content' and 'text' keys as crawler.py uses 'text'
        content = page.get("content", page.get("text", ""))
        crawled_at = page.get("crawled_at", "")
        
        # Split each page's content into chunks
        chunks = get_chunks(content)
        
        print(f"[{page_index + 1}/{total_pages}] {title} — {len(chunks)} chunks")
        
        for chunk_index, chunk_text in enumerate(chunks):
            # Create unique chunk ID
            chunk_id = f"page{page_index}_chunk{chunk_index}"
            
            # Check if chunk already exists in ChromaDB
            existing = collection.get(ids=[chunk_id])
            if existing and existing.get("ids"):
                continue
                
            # Get Gemini embedding
            embedding = get_embedding(chunk_text)
            if not embedding:
                # If it fails again, skip that chunk and log it
                print(f"  -> Skipping chunk {chunk_id} due to embedding failure.")
                continue
                
            # Ensure metadata values are valid types (strings, ints, floats)
            metadata = {
                "url": str(url),
                "title": str(title),
                "crawled_at": str(crawled_at)
            }
            
            # Store in ChromaDB
            collection.add(
                ids=[chunk_id],
                embeddings=[embedding],
                documents=[chunk_text],
                metadatas=[metadata]
            )
            
            total_chunks_stored += 1

    # Print final summary
    print(f"\nFinal summary: {total_chunks_stored} total chunks stored")

if __name__ == "__main__":
    main()
