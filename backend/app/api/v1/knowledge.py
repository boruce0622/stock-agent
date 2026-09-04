from fastapi import APIRouter, Query

from app.rag.knowledge_retriever import LocalKnowledgeRetriever

router = APIRouter(prefix="/api/v1/knowledge", tags=["Knowledge RAG"])
retriever = LocalKnowledgeRetriever()


@router.get("/search")
async def search_knowledge(q: str = Query(min_length=2, max_length=200)):
    """Expose retrieval hits so RAG grounding can be inspected independently."""
    return await retriever.search(q)
