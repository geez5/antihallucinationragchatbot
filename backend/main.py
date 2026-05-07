import os
import time
import subprocess
from typing import List, Optional
from fastapi import FastAPI, Request, HTTPException, Header, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator
import chromadb
import google.generativeai as genai
from groq import Groq
from sentence_transformers import CrossEncoder
from dotenv import load_dotenv

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# ==============================================================================
# CONFIGURATION AND SETUP
# ==============================================================================
load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
RECRAWL_SECRET = os.getenv("RECRAWL_SECRET", "super-secret-key")

# Setup Groq and Gemini clients
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

# Setup ChromaDB
chroma_client = chromadb.PersistentClient(path="./chroma_db")
collection = chroma_client.get_or_create_collection(
    name="doitchatbot",  # updated per your request
    metadata={"hnsw:space": "cosine"}
)

# Setup Reranker (Cross-Encoder)
cross_encoder = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")

# Setup FastAPI App and Rate Limiter
limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="doitchatbot Backend")

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS (Allow all for now)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

FALLBACK_MESSAGE = "I couldn't find that information on our website. Please contact us directly for help."

# ==============================================================================
# PYDANTIC MODELS
# ==============================================================================
class Message(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    question: str
    chat_history: List[Message] = []

    @field_validator("question")
    @classmethod
    def validate_question(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Question cannot be empty")
        if len(v) > 500:
            raise ValueError("Question cannot exceed 500 characters")
        return v

class ChatResponse(BaseModel):
    answer: str
    sources: List[str]
    source_titles: List[str]

class FeedbackRequest(BaseModel):
    session_id: str
    rating: int
    question: str
    answer: str

# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================
def get_embedding(text: str) -> List[float]:
    # Truncate text just in case before generating embedding
    result = genai.embed_content(
        model="models/gemini-embedding-2",
        content=text[:8000]
    )
    return result['embedding']

def check_intent(question: str) -> bool:
    """Layer 1 - Intent Classifier: Checks if question relates to business."""
    prompt = (
        f"Is the following question related to business, products, services, website details, or customer support? "
        f"Question: '{question}'. Answer strictly YES or NO."
    )
    if not groq_client:
        return True # fail open if no key
        
    try:
        response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=10
        )
        text = response.choices[0].message.content.strip().upper()
        return "YES" in text
    except Exception:
        return True # Fallback if API fails

def verify_safe_response(context: str, answer: str) -> bool:
    """Layer 8 - Guardrail self-check: Prevents hallucinations."""
    if not groq_client:
        return True

    prompt = (
        f"Context:\n{context}\n\n"
        f"Answer:\n{answer}\n\n"
        "Analyze the Answer against the Context. Does the Answer contain any specific factual claims, names, or details "
        "that are NOT explicitly supported by the Context? "
        "If it invents information, answer strictly HALLUCINATION. If it is safely grounded in the Context, answer strictly SAFE."
    )
    try:
        response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=10
        )
        text = response.choices[0].message.content.strip().upper()
        return "HALLUCINATION" not in text
    except Exception:
        return False # Fail safe on error

def run_recrawl_task():
    """Background task to run crawler and ingestion scripts."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(base_dir)
    crawler_script = os.path.join(project_root, "crawler.py")
    ingest_script = os.path.join(base_dir, "ingest.py")
    
    print("Starting recrawl task...")
    try:
        if os.path.exists(crawler_script):
            subprocess.run(["python", crawler_script], cwd=project_root, check=True)
            print("Crawler finished.")
        else:
            print("crawler.py not found.")

        if os.path.exists(ingest_script):
            subprocess.run(["python", ingest_script], cwd=base_dir, check=True)
            print("Ingestion finished.")
        else:
            print("ingest.py not found.")
    except Exception as e:
        print(f"Error during recrawl task: {e}")

# ==============================================================================
# API ENDPOINTS
# ==============================================================================
@app.get("/")
def home():
    return {"message": "Backend is running 🚀"}

@app.get("/health")
async def health_check():
    """Returns system status and vector DB count."""
    try:
        count = collection.count()
        return {"status": "ok", "db_count": count}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/feedback")
async def receive_feedback(feedback: FeedbackRequest):
    """Logs user feedback."""
    print(f"[FEEDBACK] Session: {feedback.session_id} | Rating: {feedback.rating} | Q: {feedback.question}")
    return {"status": "received"}

@app.post("/re-crawl")
async def trigger_recrawl(background_tasks: BackgroundTasks, x_api_key: Optional[str] = Header(None)):
    """Triggers crawler and ingest scripts as a background task."""
    if not x_api_key or x_api_key != RECRAWL_SECRET:
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    background_tasks.add_task(run_recrawl_task)
    return {"status": "started"}

@app.post("/seed")
async def seed_test_data():
    """Injects test data so the database isn't empty."""
    try:
        text = "Our company is a leading technology firm. We build advanced AI chatbot solutions using RAG technology for enterprise clients."
        embedding = get_embedding(text)
        collection.add(
            ids=["test_doc_1"],
            embeddings=[embedding],
            documents=[text],
            metadatas=[{"url": "https://example.com/about", "title": "About Our Company"}]
        )
        return {"status": "seeded"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/chat", response_model=ChatResponse)
@limiter.limit("20/minute")
async def chat(request: Request, body: ChatRequest):
    question = body.question
    
    # LAYER 1: Intent classifier
    if not check_intent(question):
        return ChatResponse(
            answer="I can only answer questions about our website and services.", 
            sources=[], 
            source_titles=[]
        )
        
    # LAYER 2: Hybrid retrieval (Query ChromaDB with Gemini embeddings)
    try:
        embedding = get_embedding(question)
        results = collection.query(
            query_embeddings=[embedding],
            n_results=10
        )
    except Exception as e:
        return ChatResponse(answer=f"Exception in Embedding: {str(e)}", sources=[], source_titles=[])

    if not results or not results['distances'] or not results['distances'][0]:
        return ChatResponse(answer=FALLBACK_MESSAGE, sources=[], source_titles=[])

    # LAYER 3: Similarity threshold (> 0.70)
    filtered_docs = []
    filtered_metas = []
    for doc, meta, dist in zip(results['documents'][0], results['metadatas'][0], results['distances'][0]):
        # Chroma cosine distance: sim = 1 - distance
        similarity = 1.0 - dist
        if similarity >= 0.70:
            filtered_docs.append(doc)
            filtered_metas.append(meta)

    if not filtered_docs:
        return ChatResponse(answer=FALLBACK_MESSAGE, sources=[], source_titles=[])

    # LAYER 4: Cross-encoder reranking
    pairs = [[question, doc] for doc in filtered_docs]
    scores = cross_encoder.predict(pairs)
    
    scored_docs = list(zip(scores, filtered_docs, filtered_metas))
    scored_docs.sort(key=lambda x: x[0], reverse=True)
    top_3 = scored_docs[:3]
    
    # Prepare context
    context = "\n\n---\n\n".join([doc for _, doc, _ in top_3])

    # LAYER 6: Strict system prompt
    system_prompt = (
        "You are a helpful business assistant called doitchatbot. "
        "ONLY use the provided context to answer the user's question. "
        "NEVER use your own knowledge. NEVER infer information not explicitly stated. "
        "If the answer is not in the context, reply exactly with: "
        f"{FALLBACK_MESSAGE}"
    )

    messages = [{"role": "system", "content": system_prompt}]
    
    # Keep last 8 messages of history
    for msg in body.chat_history[-8:]:
        messages.append({"role": msg.role, "content": msg.content})
        
    messages.append({"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"})

    # LAYER 5 & 7: Temperature=0, max_tokens=512
    try:
        response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=messages,
            temperature=0,
            max_tokens=512
        )
        answer = response.choices[0].message.content.strip()
    except Exception as e:
        return ChatResponse(answer=f"Exception in LLM: {str(e)}", sources=[], source_titles=[])

    # Check if LLM gracefully fell back
    if answer == FALLBACK_MESSAGE:
        return ChatResponse(answer=answer, sources=[], source_titles=[])

    # LAYER 8: Guardrail self-check
    is_safe = verify_safe_response(context, answer)
    if not is_safe:
        answer = FALLBACK_MESSAGE

    # LAYER 9: Source citation
    sources = []
    source_titles = []
    if answer != FALLBACK_MESSAGE:
        for _, _, meta in top_3:
            url = meta.get("url", "")
            title = meta.get("title", "")
            if url and url not in sources:
                sources.append(url)
                source_titles.append(title)
                
    return ChatResponse(answer=answer, sources=sources, source_titles=source_titles)
