from __future__ import annotations

import math
import re
from collections import Counter
from pathlib import Path
from typing import Any

from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from pydantic import Field, PrivateAttr


def _default_knowledge_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "knowledge"


def _terms(text: str) -> list[str]:
    normalized = re.sub(r"\s+", "", text.lower())
    latin = re.findall(r"[a-z][a-z0-9_.+-]{1,}|\d+(?:\.\d+)?", normalized)
    chinese_runs = re.findall(r"[\u4e00-\u9fff]+", normalized)
    chinese: list[str] = []
    for run in chinese_runs:
        chinese.extend(run[index : index + 2] for index in range(max(len(run) - 1, 1)))
        if len(run) <= 6:
            chinese.append(run)
    return latin + chinese


class LocalKnowledgeRetriever(BaseRetriever):
    """Small, auditable LangChain retriever for the bundled Chinese knowledge base."""

    knowledge_dir: Path = Field(default_factory=_default_knowledge_dir)
    top_k: int = 5
    min_score: float = 0.04
    _documents: list[Document] = PrivateAttr(default_factory=list)
    _document_terms: list[Counter[str]] = PrivateAttr(default_factory=list)

    def model_post_init(self, __context: Any) -> None:
        self._documents = self._load_documents()
        self._document_terms = [Counter(_terms(doc.page_content)) for doc in self._documents]

    def _load_documents(self) -> list[Document]:
        documents: list[Document] = []
        for path in sorted(self.knowledge_dir.glob("*.md")):
            text = path.read_text(encoding="utf-8")
            title_match = re.search(r"^#\s+(.+)$", text, flags=re.M)
            title = title_match.group(1).strip() if title_match else path.stem
            updated_match = re.search(r"^更新日期：\s*(.+)$", text, flags=re.M)
            updated_at = updated_match.group(1).strip() if updated_match else "未标注"
            sections = re.split(r"(?=^##\s+)", text, flags=re.M)
            for index, section in enumerate(sections):
                content = section.strip()
                if not content or not content.startswith("## "):
                    continue
                heading = content.splitlines()[0].removeprefix("## ").strip()
                documents.append(
                    Document(
                        page_content=content,
                        metadata={
                            "id": f"{path.stem}-{index}",
                            "title": title,
                            "section": heading,
                            "source": f"knowledge/{path.name}",
                            "updated_at": updated_at,
                        },
                    )
                )
        return documents

    def _get_relevant_documents(
        self,
        query: str,
        *,
        run_manager: CallbackManagerForRetrieverRun,
    ) -> list[Document]:
        del run_manager
        query_terms = Counter(_terms(query))
        if not query_terms:
            return []
        ranked: list[tuple[float, Document]] = []
        for document, document_terms in zip(
            self._documents, self._document_terms, strict=True
        ):
            overlap = sum(
                min(count, document_terms.get(term, 0))
                for term, count in query_terms.items()
            )
            score = overlap / math.sqrt(
                max(sum(query_terms.values()) * sum(document_terms.values()), 1)
            )
            title_terms = set(_terms(str(document.metadata.get("section", ""))))
            score += 0.2 * len(set(query_terms) & title_terms) / max(len(query_terms), 1)
            if score >= self.min_score:
                copy = Document(
                    page_content=document.page_content,
                    metadata={**document.metadata, "score": round(score, 4)},
                )
                ranked.append((score, copy))
        ranked.sort(key=lambda item: item[0], reverse=True)
        return [document for _score, document in ranked[: self.top_k]]

    async def search(self, query: str) -> dict[str, Any]:
        documents = await self.ainvoke(query)
        hits = [
            {
                "citation": f"[知识库{index}]",
                "content": document.page_content,
                **document.metadata,
            }
            for index, document in enumerate(documents, start=1)
        ]
        return {
            "ok": bool(hits),
            "query": query,
            "source": "本地知识库（LangChain Retriever）",
            "hits": hits,
            "guardrail": (
                "只能依据命中文档回答，并使用对应的[知识库N]标记；未命中时明确说明。"
                if hits
                else "知识库无相关命中，不得声称答案来自知识库。"
            ),
        }
