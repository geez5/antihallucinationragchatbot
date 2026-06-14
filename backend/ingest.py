"""
ingest.py — Veritas RAG Chatbot Ingestion Pipeline
====================================================
Reads pages.json, chunks each page's content, embeds with Gemini
text-embedding-004, and stores in ChromaDB collection "veritas".

Run with:
    python ingest.py
"""

import os
import json
import time
import chromadb
from google import genai
from dotenv import load_dotenv

# ==============================================================================
# SETUP
# ==============================================================================
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    print("ERROR: GEMINI_API_KEY not found in .env file.")
    exit(1)

# New google-genai SDK client
gemini_client = genai.Client(api_key=GEMINI_API_KEY)
EMBEDDING_MODEL = "models/gemini-embedding-001"

# ChromaDB — stored at ./chroma_db relative to this script
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CHROMA_PATH = os.path.join(BASE_DIR, "chroma_db")

chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)
collection = chroma_client.get_or_create_collection(
    name="veritas",
    metadata={"hnsw:space": "cosine"},
)

print(f"ChromaDB connected at: {CHROMA_PATH}")
print(f"Collection 'veritas' currently has {collection.count()} vectors.\n")

# ==============================================================================
# CHUNKING
# ==============================================================================
def get_chunks(text: str, chunk_size: int = 400, overlap: int = 80) -> list[str]:
    """
    Splits text into chunks of `chunk_size` words with `overlap` word overlap.
    Skips chunks shorter than 60 characters.
    """
    words = text.split()
    chunks = []
    i = 0
    while i < len(words):
        chunk_words = words[i : i + chunk_size]
        chunk_text = " ".join(chunk_words)
        if len(chunk_text) >= 60:
            chunks.append(chunk_text)
        i += chunk_size - overlap
    return chunks


# ==============================================================================
# EMBEDDING
# ==============================================================================
def get_embedding(text: str) -> list[float] | None:
    """
    Embeds text using Gemini text-embedding-004.
    Truncates to 8 000 characters, retries once on failure.
    Returns the embedding list, or None if both attempts fail.
    """
    truncated = text[:8000]

    def _call_api() -> list[float]:
        result = gemini_client.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=truncated,
        )
        return result.embeddings[0].values

    # First attempt
    try:
        return _call_api()
    except Exception as e:
        print(f"    [WARNING] Embedding failed ({e}). Retrying in 2 s...")
        time.sleep(2)

    # Single retry
    try:
        return _call_api()
    except Exception as e:
        print(f"    [ERROR]   Embedding failed again ({e}). Skipping chunk.")
        return None


# ==============================================================================
# MAIN INGESTION LOOP
# ==============================================================================
def main():
    # Locate pages.json — check this script's dir first, then project root
    pages_file = os.path.join(BASE_DIR, "pages.json")
    if not os.path.exists(pages_file):
        project_root = os.path.dirname(BASE_DIR)
        pages_file = os.path.join(project_root, "pages.json")
        if not os.path.exists(pages_file):
            print("ERROR: pages.json not found. Run the crawler first.")
            return

    print(f"Loading pages from: {pages_file}")
    with open(pages_file, "r", encoding="utf-8") as f:
        pages = json.load(f)

    total_pages = len(pages)
    total_chunks_stored = 0
    total_chunks_skipped_existing = 0
    total_chunks_skipped_error = 0

    print(f"Found {total_pages} pages to process.\n")
    print("=" * 60)

    for page_index, page in enumerate(pages):
        url        = str(page.get("url",        ""))
        title      = str(page.get("title",      "Untitled"))
        content    = page.get("content", page.get("text", ""))
        crawled_at = str(page.get("crawled_at", ""))

        if not content or not content.strip():
            print(f"[{page_index + 1}/{total_pages}] SKIP (no content): {title}")
            continue

        chunks = get_chunks(content)
        print(f"[{page_index + 1}/{total_pages}] {title} — {len(chunks)} chunk(s)")

        for chunk_index, chunk_text in enumerate(chunks):
            chunk_id = f"page{page_index}_chunk{chunk_index}"

            # ── Dedup check: skip if already in ChromaDB ─────────────────────
            existing = collection.get(ids=[chunk_id])
            if existing and existing.get("ids"):
                total_chunks_skipped_existing += 1
                continue

            # ── Embed ─────────────────────────────────────────────────────────
            embedding = get_embedding(chunk_text)
            if embedding is None:
                total_chunks_skipped_error += 1
                print(f"    -> Skipping {chunk_id} (embedding error).")
                continue

            # ── Store in ChromaDB ─────────────────────────────────────────────
            collection.add(
                ids=[chunk_id],
                embeddings=[embedding],
                documents=[chunk_text],
                metadatas=[{
                    "url":        url,
                    "title":      title,
                    "crawled_at": crawled_at,
                }],
            )
            total_chunks_stored += 1

    # ── Final summary ─────────────────────────────────────────────────────────
    print("=" * 60)
    print(f"\nIngestion complete!")
    print(f"  Pages processed  : {total_pages}")
    print(f"  Chunks stored    : {total_chunks_stored}")
    print(f"  Chunks skipped   : {total_chunks_skipped_existing} (already existed)")
    print(f"  Chunks errored   : {total_chunks_skipped_error} (embedding failure)")
    print(f"  Total in DB now  : {collection.count()}")


if __name__ == "__main__":
    main()
