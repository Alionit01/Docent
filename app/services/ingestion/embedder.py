import time
import chromadb
from chromadb.utils import embedding_functions
from app.core.errors import AppError


class Embedder:
    def __init__(self, model_name: str = "all-MiniLM-L6-v2", persist_dir: str = "./data/chroma"):
        self.ef = embedding_functions.DefaultEmbeddingFunction()
        self.model_name = model_name
        self.client = chromadb.PersistentClient(path=persist_dir)
        self.collection = self.client.get_or_create_collection(
            name="docent_chunks",
            embedding_function=self.ef,
        )

    def embed(self, texts: list[str], batch_size: int = 64, max_retries: int = 3) -> list[list[float]] | None:
        """Embed a list of texts in batches. Returns embeddings or None on failure."""
        all_embeddings = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            for attempt in range(max_retries):
                try:
                    result = self.ef(batch)
                    all_embeddings.extend(result)
                    break
                except Exception:
                    if attempt < max_retries - 1:
                        time.sleep(2 ** attempt)
                    else:
                        return None
        return all_embeddings

    def store_chunks(self, chunks: list[dict]) -> bool:
        """Store chunks in ChromaDB. Returns False if operations fail."""
        ids = [c["id"] for c in chunks]
        texts = [c["content"] for c in chunks]
        metadatas = [
            {"document_id": c.get("document_id", ""), "page_number": c["page_number"],
             "chapter_hint": c.get("chapter_hint", "")}
            for c in chunks
        ]
        doc_ids = [c.get("document_id", "") for c in chunks]

        embeddings = self.embed(texts)
        if embeddings is None:
            return False

        try:
            self.collection.upsert(
                ids=ids,
                embeddings=embeddings,
                documents=texts,
                metadatas=metadatas,
            )
        except Exception:
            return False

        return True

    def query(self, query_text: str, top_k: int = 6, document_id: str | None = None,
              lesson_context_id: str | None = None) -> list[dict]:
        """Query ChromaDB for similar chunks. Returns list of {id, distance, metadata}."""
        query_embeddings = self.embed([query_text])
        if query_embeddings is None:
            return []

        kwargs = {
            "query_embeddings": query_embeddings,
            "n_results": top_k,
            "include": ["metadatas", "documents", "distances"],
        }
        if document_id:
            kwargs["where"] = {"document_id": document_id}

        try:
            results = self.collection.query(**kwargs)
        except Exception:
            return []

        chunks = []
        if results["ids"] and results["ids"][0]:
            for i in range(len(results["ids"][0])):
                chunks.append({
                    "id": results["ids"][0][i],
                    "content": results["documents"][0][i] if results["documents"] else "",
                    "distance": results["distances"][0][i] if results["distances"] else 0,
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                })

        return chunks
