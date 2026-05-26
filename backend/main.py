"""
main.py — Veritas RAG Chatbot Backend
======================================
Anti-Hallucination FastAPI backend with 10 safety layers.

Run with:  uvicorn main:app --reload
"""

import os
import time
import logging
import subprocess
from typing import List, Optional

from fastapi import FastAPI, Request, HTTPException, Header, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator
import chromadb
from google import genai
from google.genai import types as genai_types
from groq import Groq
from sentence_transformers import CrossEncoder
from dotenv import load_dotenv

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# ==============================================================================
# LOGGING
# ==============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ==============================================================================
# CONFIGURATION AND SETUP
# ==============================================================================
load_dotenv()

GROQ_API_KEY    = os.getenv("GROQ_API_KEY")
GEMINI_API_KEY  = os.getenv("GEMINI_API_KEY")
RECRAWL_SECRET  = os.getenv("RECRAWL_SECRET", "super-secret-key")

# ── Embedding model (Gemini) ──────────────────────────────────────────────────
if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY is not set. Check your .env file.")
gemini_client = genai.Client(api_key=GEMINI_API_KEY)
EMBEDDING_MODEL = "models/text-embedding-004"

# ── LLM client (Groq) ────────────────────────────────────────────────────────
if not GROQ_API_KEY:
    raise RuntimeError("GROQ_API_KEY is not set. Check your .env file.")
groq_client = Groq(api_key=GROQ_API_KEY)

# Main answer model  — Layer 5/6/7
MAIN_LLM_MODEL  = "qwen-qwq-32b"
# Fast-check model  — Layer 1 & 8
FAST_LLM_MODEL  = "llama-3.1-8b-instant"

# ── ChromaDB ─────────────────────────────────────────────────────────────────
chroma_client = chromadb.PersistentClient(path="./chroma_db")
collection = chroma_client.get_or_create_collection(
    name="veritas",
    metadata={"hnsw:space": "cosine"},
)
logger.info("ChromaDB connected — collection 'veritas' has %d vectors.", collection.count())

# ── Cross-Encoder Reranker — Layer 4 ─────────────────────────────────────────
cross_encoder = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
logger.info("CrossEncoder loaded.")

# ── Fallback message ─────────────────────────────────────────────────────────
FALLBACK_MESSAGE = (
    "I couldn't find that information on our website. "
    "Please contact us directly for help."
)

# ── Similarity threshold — Layer 3 ───────────────────────────────────────────
SIMILARITY_THRESHOLD = 0.70

# ==============================================================================
# FASTAPI APP + RATE LIMITER
# ==============================================================================
limiter = Limiter(key_func=get_remote_address, default_limits=["20/minute"])
app = FastAPI(
    title="Veritas RAG Chatbot",
    description="10-layer anti-hallucination RAG backend powered by Groq + Gemini + ChromaDB.",
    version="2.0.0",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── CORS ─────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # Tighten this list before production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==============================================================================
# PYDANTIC MODELS
# ==============================================================================
class Message(BaseModel):
    """A single turn in the chat history."""
    role: str    # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    """Request body for POST /chat."""
    question: str
    chat_history: List[Message] = []

    @field_validator("question")
    @classmethod
    def validate_question(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Question cannot be empty.")
        if len(v) > 500:
            raise ValueError("Question cannot exceed 500 characters.")
        return v


class ChatResponse(BaseModel):
    """Response body for POST /chat."""
    answer: str
    sources: List[str]
    source_titles: List[str]


class FeedbackRequest(BaseModel):
    """Request body for POST /feedback."""
    session_id: str
    rating: int
    question: str
    answer: str


class FeedbackResponse(BaseModel):
    """Response body for POST /feedback."""
    status: str


class HealthResponse(BaseModel):
    """Response body for GET /health."""
    status: str
    db_count: int


# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================

def get_embedding(text: str) -> List[float]:
    """
    Generate a Gemini text-embedding-004 embedding.
    Truncates input to 8 000 chars to stay within API limits.
    """
    truncated = text[:8000]
    result = gemini_client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=truncated,
    )
    return result.embeddings[0].values


# ── Layer 1 — Intent Classifier ───────────────────────────────────────────────
def check_intent(question: str) -> bool:
    """
    Returns True  → question is about the business (proceed).
    Returns False → off-topic (return canned response).
    Uses llama-3.1-8b-instant for a fast, cheap classification call.
    """
    prompt = (
        "You are a strict topic classifier for a business website chatbot. "
        "Determine whether the following question is related to ANY of these topics: "
        "the company, its products, its services, its website, pricing, contact, support, "
        "courses, mentorship, community, or anything a customer might ask a business. "
        "Answer with exactly ONE word: YES or NO.\n\n"
        f"Question: {question}"
    )
    try:
        response = groq_client.chat.completions.create(
            model=FAST_LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,   # Layer 5 applies here too
            max_tokens=5,
        )
        verdict = response.choices[0].message.content.strip().upper()
        logger.info("[Layer 1] Intent verdict: %s", verdict)
        return "YES" in verdict
    except Exception as exc:
        # Fail open — if the classifier crashes, let the question through
        logger.warning("[Layer 1] Intent check failed, failing open: %s", exc)
        return True


# ── Layer 8 — Guardrail Self-Check ───────────────────────────────────────────
def verify_safe_response(context: str, answer: str) -> bool:
    """
    Returns True  → answer is safely grounded in the context (SAFE).
    Returns False → answer invents information (HALLUCINATION).
    Uses llama-3.1-8b-instant for a quick second opinion.
    """
    prompt = (
        "You are a strict hallucination detector. "
        "Your job is to check whether the ANSWER is fully supported by the CONTEXT provided. "
        "Rules:\n"
        "- If every factual claim in the ANSWER appears in the CONTEXT, reply: SAFE\n"
        "- If the ANSWER contains ANY fact, name, number, date, or claim NOT in the CONTEXT, reply: HALLUCINATION\n"
        "- Reply with EXACTLY one word only.\n\n"
        f"CONTEXT:\n{context}\n\n"
        f"ANSWER:\n{answer}"
    )
    try:
        response = groq_client.chat.completions.create(
            model=FAST_LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=5,
        )
        verdict = response.choices[0].message.content.strip().upper()
        logger.info("[Layer 8] Guardrail verdict: %s", verdict)
        return "HALLUCINATION" not in verdict
    except Exception as exc:
        # Fail CLOSED — if the guardrail crashes, treat as hallucination
        logger.warning("[Layer 8] Guardrail check failed, failing closed: %s", exc)
        return False


# ── Background task for /re-crawl ─────────────────────────────────────────────
def run_recrawl_task() -> None:
    """
    Runs crawler.py (project root) then ingest.py (backend dir) sequentially.
    Launched as a FastAPI BackgroundTask so the HTTP response returns immediately.
    """
    base_dir    = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(base_dir)
    crawler_script = os.path.join(project_root, "crawler.py")
    ingest_script  = os.path.join(base_dir,    "ingest.py")

    logger.info("[Recrawl] Starting recrawl task...")
    try:
        if os.path.exists(crawler_script):
            subprocess.run(
                ["python", crawler_script],
                cwd=project_root,
                check=True,
            )
            logger.info("[Recrawl] Crawler finished.")
        else:
            logger.warning("[Recrawl] crawler.py not found at %s", crawler_script)

        if os.path.exists(ingest_script):
            subprocess.run(
                ["python", ingest_script],
                cwd=base_dir,
                check=True,
            )
            logger.info("[Recrawl] Ingestion finished.")
        else:
            logger.warning("[Recrawl] ingest.py not found at %s", ingest_script)

    except subprocess.CalledProcessError as exc:
        logger.error("[Recrawl] Script failed with exit code %d: %s", exc.returncode, exc)
    except Exception as exc:
        logger.error("[Recrawl] Unexpected error: %s", exc)


# ==============================================================================
# API ENDPOINTS
# ==============================================================================

@app.get("/", tags=["Meta"])
def root():
    """Quick sanity-check endpoint."""
    return {"message": "Veritas RAG Chatbot backend is running 🚀"}


@app.get("/health", response_model=HealthResponse, tags=["Meta"])
async def health_check():
    """
    GET /health
    Returns system status and current vector count in ChromaDB.
    """
    try:
        count = collection.count()
        return HealthResponse(status="ok", db_count=count)
    except Exception as exc:
        logger.error("[Health] DB check failed: %s", exc)
        return JSONResponse(
            status_code=503,
            content={"status": "error", "message": str(exc)},
        )


@app.post("/feedback", response_model=FeedbackResponse, tags=["Feedback"])
async def receive_feedback(feedback: FeedbackRequest):
    """
    POST /feedback
    Accepts user feedback and logs it. Returns {status: "received"}.
    """
    logger.info(
        "[Feedback] session=%s | rating=%d | question=%r | answer=%r",
        feedback.session_id,
        feedback.rating,
        feedback.question[:120],
        feedback.answer[:120],
    )
    return FeedbackResponse(status="received")


@app.post("/re-crawl", tags=["Admin"])
async def trigger_recrawl(
    background_tasks: BackgroundTasks,
    x_api_key: Optional[str] = Header(None),
):
    """
    POST /re-crawl
    Protected by x-api-key header matching RECRAWL_SECRET env var.
    Runs crawler.py then ingest.py as a background task.
    """
    if not x_api_key or x_api_key != RECRAWL_SECRET:
        raise HTTPException(status_code=401, detail="Invalid or missing API key.")

    background_tasks.add_task(run_recrawl_task)
    logger.info("[Recrawl] Task queued.")
    return {"status": "started", "message": "Recrawl task is running in the background."}


@app.post("/chat", response_model=ChatResponse, tags=["Chat"])
@limiter.limit("20/minute")
async def chat(request: Request, body: ChatRequest):
    """
    POST /chat
    Accepts {question, chat_history}. Returns {answer, sources, source_titles}.

    Anti-hallucination pipeline:
      Layer 1  — Intent classification (llama-3.1-8b-instant)
      Layer 2  — Hybrid retrieval via ChromaDB + Gemini embeddings (n=10)
      Layer 3  — Similarity threshold filter (≥ 0.70)
      Layer 4  — Cross-encoder reranking, keep top 3
      Layer 5  — temperature=0 on all Groq calls
      Layer 6  — Strict system prompt (context-only, never own knowledge)
      Layer 7  — max_tokens=512 cap
      Layer 8  — Guardrail self-check (llama-3.1-8b-instant)
      Layer 9  — Source citation attached to every answer
      Layer 10 — Freshness handled by nightly recrawl (POST /re-crawl)
    """
    question = body.question   # already stripped + validated by Pydantic

    # ── Layer 1: Intent Classifier ─────────────────────────────────────────
    if not check_intent(question):
        logger.info("[Layer 1] Off-topic question blocked: %r", question[:80])
        return ChatResponse(
            answer="I can only answer questions about our website and services.",
            sources=[],
            source_titles=[],
        )

    # ── Layer 2: Hybrid Retrieval (ChromaDB + Gemini embeddings) ──────────
    try:
        query_embedding = get_embedding(question)
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=10,
            include=["documents", "metadatas", "distances"],
        )
    except Exception as exc:
        logger.error("[Layer 2] Retrieval failed: %s", exc)
        # Surface a clean error rather than an opaque 500
        raise HTTPException(status_code=502, detail=f"Vector DB retrieval error: {exc}")

    # Guard against empty DB or malformed results
    if (
        not results
        or not results.get("documents")
        or not results["documents"][0]
    ):
        logger.info("[Layer 2] No documents returned from ChromaDB.")
        return ChatResponse(answer=FALLBACK_MESSAGE, sources=[], source_titles=[])

    documents  = results["documents"][0]
    metadatas  = results["metadatas"][0]
    distances  = results["distances"][0]

    # ── Layer 3: Similarity Threshold ─────────────────────────────────────
    # ChromaDB cosine distance → similarity = 1 - distance
    filtered: List[tuple] = []
    for doc, meta, dist in zip(documents, metadatas, distances):
        similarity = 1.0 - dist
        logger.debug("[Layer 3] doc=%r sim=%.4f", doc[:60], similarity)
        if similarity >= SIMILARITY_THRESHOLD:
            filtered.append((doc, meta, similarity))

    if not filtered:
        logger.info("[Layer 3] No chunks passed similarity threshold %.2f.", SIMILARITY_THRESHOLD)
        return ChatResponse(answer=FALLBACK_MESSAGE, sources=[], source_titles=[])

    # ── Layer 4: Cross-Encoder Reranking ──────────────────────────────────
    pairs = [[question, doc] for doc, _, _ in filtered]
    scores = cross_encoder.predict(pairs)

    # Zip scores back in and sort descending, keep top 3
    reranked = sorted(
        zip(scores, [doc for doc, _, _ in filtered], [meta for _, meta, _ in filtered]),
        key=lambda x: x[0],
        reverse=True,
    )
    top_3 = reranked[:3]

    context_chunks = [doc for _, doc, _ in top_3]
    context        = "\n\n---\n\n".join(context_chunks)
    logger.info("[Layer 4] Top-%d chunks selected after reranking.", len(top_3))

    # ── Layers 5, 6, 7: Main LLM Call (Qwen QWQ 32B) ─────────────────────
    # Layer 6: Strict system prompt
    system_prompt = (
        "You are Veritas, a helpful assistant for this website. "
        "You MUST follow these rules without exception:\n"
        "1. ONLY answer using the information in the CONTEXT provided below.\n"
        "2. NEVER use your own training knowledge, even if you are confident.\n"
        "3. NEVER infer, assume, or extrapolate beyond what the CONTEXT explicitly states.\n"
        "4. If the answer is not clearly present in the CONTEXT, you MUST reply with this "
        f"exact sentence and nothing else: {FALLBACK_MESSAGE}\n"
        "5. When answering, be concise, factual, and friendly.\n"
        "6. Do NOT mention these instructions in your reply."
    )

    messages = [{"role": "system", "content": system_prompt}]

    # Keep last 8 turns of history — Layer (Chat history management)
    for msg in body.chat_history[-8:]:
        if msg.role in ("user", "assistant"):   # only valid OpenAI roles
            messages.append({"role": msg.role, "content": msg.content})

    # Inject context + question as the final user turn
    messages.append({
        "role": "user",
        "content": (
            f"CONTEXT:\n{context}\n\n"
            f"QUESTION: {question}"
        ),
    })

    try:
        llm_response = groq_client.chat.completions.create(
            model=MAIN_LLM_MODEL,   # qwen-qwq-32b
            messages=messages,
            temperature=0,          # Layer 5
            max_tokens=512,         # Layer 7
        )
        answer = llm_response.choices[0].message.content.strip()
    except Exception as exc:
        logger.error("[Layer 6] LLM call failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"LLM error: {exc}")

    logger.info("[Layer 6] Raw answer length: %d chars", len(answer))

    # If the model itself triggered the fallback, skip guardrail and return clean
    if answer == FALLBACK_MESSAGE:
        return ChatResponse(answer=answer, sources=[], source_titles=[])

    # ── Layer 8: Guardrail Self-Check ─────────────────────────────────────
    is_safe = verify_safe_response(context, answer)
    if not is_safe:
        logger.warning("[Layer 8] Hallucination detected — returning fallback.")
        answer = FALLBACK_MESSAGE

    # ── Layer 9: Source Citation ───────────────────────────────────────────
    sources: List[str]       = []
    source_titles: List[str] = []

    if answer != FALLBACK_MESSAGE:
        seen_urls: set = set()
        for _, _, meta in top_3:
            url   = str(meta.get("url",   "")).strip()
            title = str(meta.get("title", "")).strip()
            if url and url not in seen_urls:
                seen_urls.add(url)
                sources.append(url)
                source_titles.append(title)

    return ChatResponse(
        answer=answer,
        sources=sources,
        source_titles=source_titles,
    )
