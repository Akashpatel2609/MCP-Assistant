"""
rag_engine.py — Advanced Production-grade RAG Engine
- Qdrant Vector DB (In-memory storage)
- NVIDIA NIM Embeddings API
- Recursive text chunking
- Dense semantic retrieval + BM25 keyword matching (hybrid)
- Cross-Encoder reranker using sentence-transformers
"""

import os
from pathlib import Path
from typing import List, Dict, Any
from dotenv import load_dotenv

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from openai import AsyncOpenAI

from langchain_text_splitters import RecursiveCharacterTextSplitter
from rank_bm25 import BM25Okapi
from sentence_transformers import CrossEncoder

# Document Parsers
from pypdf import PdfReader
from docx import Document

load_dotenv()

class RAGEngine:
    def __init__(self):
        # Initialize in-memory Qdrant Client for quick and lightweight local execution (production interface)
        self.qdrant = QdrantClient(":memory:")
        self.collection_name = "nexus_rag"
        
        # Configure NVIDIA Embeddings (OpenAI compatible API)
        self.nvidia_api_key = os.getenv("NVIDIA_API_KEY")
        self.client = AsyncOpenAI(
            base_url="https://integrate.api.nvidia.com/v1",
            api_key=self.nvidia_api_key
        )
        # Using state-of-the-art retrieval embedding model from NVIDIA NIM
        self.embedding_model = "nvidia/nv-embedqa-e5-v5"
        
        # Local Cross-Encoder for high-accuracy reranking (Re-scores top-20 candidates down to top-5)
        # This small model (approx. 40MB) fits in CPU RAM instantly and operates extremely fast.
        self.reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
        
        # In-memory store for Hybrid BM25 keyword searching alongside vector searching
        self.chunks: List[str] = []
        self.metadatas: List[Dict[str, Any]] = []
        self.bm25: BM25Okapi = None

        self._setup_collection()

    def _setup_collection(self):
        # Create the collection to hold 1024-dimension embeddings (standard for nv-embedqa-e5-v5)
        self.qdrant.create_collection(
            collection_name=self.collection_name,
            vectors_config=VectorParams(size=1024, distance=Distance.COSINE),
        )

    async def _get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Fetch dense embeddings from the NVIDIA NIM API."""
        try:
            response = await self.client.embeddings.create(
                input=texts,
                model=self.embedding_model,
                extra_body={"input_type": "query"}
            )
            return [data.embedding for data in response.data]
        except Exception as e:
            print(f"Error fetching embeddings from NVIDIA NIM: {e}")
            # Mock vectors (fallback) if connection fails
            return [[0.0] * 1024 for _ in texts]

    def _parse_file(self, filepath: Path) -> str:
        """Parse contents of files including TXT, PDF, and DOCX."""
        ext = filepath.suffix.lower()
        if ext == ".txt":
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
        elif ext == ".pdf":
            reader = PdfReader(filepath)
            return "\n".join([page.extract_text() or "" for page in reader.pages])
        elif ext in [".docx", ".doc"]:
            doc = Document(filepath)
            return "\n".join([para.text for para in doc.paragraphs])
        elif ext in [".py", ".json", ".md", ".js", ".ts", ".html", ".css"]:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
        return ""

    async def index_file(self, filepath: str) -> str:
        """Extract text, chunk it recursively, embed via NVIDIA, and index in Qdrant & BM25."""
        path = Path(filepath)
        if not path.exists():
            return f"File {path.name} not found."

        text = self._parse_file(path)
        if not text.strip():
            return f"Could not extract any content from {path.name}."

        # Recursive splitting is the gold standard for parsing documents retaining semantic context
        splitter = RecursiveCharacterTextSplitter(chunk_size=750, chunk_overlap=120)
        chunks = splitter.split_text(text)

        if not chunks:
            return f"No text chunks created for {path.name}."

        embeddings = await self._get_embeddings(chunks)

        # Build Points for Qdrant insertion
        points = []
        start_idx = len(self.chunks)
        for i, (chunk, vector) in enumerate(zip(chunks, embeddings)):
            global_idx = start_idx + i
            meta = {"source": path.name, "chunk_index": i, "text": chunk}
            self.chunks.append(chunk)
            self.metadatas.append(meta)
            
            points.append(PointStruct(
                id=global_idx,
                vector=vector,
                payload=meta
            ))

        # Upload vectors to Qdrant
        self.qdrant.upsert(
            collection_name=self.collection_name,
            points=points
        )

        # Refresh BM25 database for keyword searching
        tokenized_corpus = [doc.lower().split(" ") for doc in self.chunks]
        self.bm25 = BM25Okapi(tokenized_corpus)

        return f"Successfully ingested **{path.name}** into the Vector Database ({len(chunks)} chunks)."

    async def retrieve(self, query: str, top_k: int = 4) -> str:
        """Retrieve most relevant chunks using Hybrid Search and Cross-Encoder Reranking."""
        if not self.chunks:
            return ""

        # 1. Vector Dense Retrieval
        query_vector = (await self._get_embeddings([query]))[0]
        vector_results = self.qdrant.search(
            collection_name=self.collection_name,
            query_vector=query_vector,
            limit=20  # Retrieve top 20 candidates for reranking
        )

        candidate_chunks = []
        seen = set()

        for result in vector_results:
            text = result.payload.get("text", "")
            if text not in seen:
                seen.add(text)
                candidate_chunks.append({
                    "text": text,
                    "source": result.payload.get("source", "unknown"),
                    "score": result.score
                })

        # 2. BM25 Keyword Search Retrieval (Fallback / Fusion)
        if self.bm25:
            tokenized_query = query.lower().split(" ")
            bm25_scores = self.bm25.get_scores(tokenized_query)
            top_bm25_indices = sorted(range(len(bm25_scores)), key=lambda i: bm25_scores[i], reverse=True)[:10]
            
            for idx in top_bm25_indices:
                if bm25_scores[idx] > 0:
                    text = self.chunks[idx]
                    if text not in seen:
                        seen.add(text)
                        candidate_chunks.append({
                            "text": text,
                            "source": self.metadatas[idx].get("source", "unknown"),
                            "score": float(bm25_scores[idx] / 10.0) # Scale down BM25 score
                        })

        if not candidate_chunks:
            return ""

        # 3. Cross-Encoder Reranking
        # Scores the semantic match quality of query + candidate chunk directly
        pairs = [[query, item["text"]] for item in candidate_chunks]
        rerank_scores = self.reranker.predict(pairs)

        for i, score in enumerate(rerank_scores):
            candidate_chunks[i]["rerank_score"] = float(score)

        # Sort candidate chunks by their new high-accuracy rerank scores
        candidate_chunks = sorted(candidate_chunks, key=lambda x: x["rerank_score"], reverse=True)
        final_results = candidate_chunks[:top_k]

        # 4. Format context block for LLM
        context_parts = []
        for i, item in enumerate(final_results, 1):
            context_parts.append(
                f"📎 **Context Chunk {i}** (Source: `{item['source']}`, Re-rank Score: `{item['rerank_score']:.4f}`):\n"
                f"{item['text']}\n"
            )

        return "\n".join(context_parts)
