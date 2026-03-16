import os
import chromadb
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction

_DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "chroma_store"))
_client = None
_embedding_fn = None
COLLECTIONS = {}


def _get_client():
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(path=_DB_PATH)
    return _client


def _get_embedding_fn():
    global _embedding_fn
    if _embedding_fn is None:
        _embedding_fn = OpenAIEmbeddingFunction(
            api_key=os.getenv("OPENAI_API_KEY"),
            model_name="text-embedding-3-small",
        )
    return _embedding_fn


def _get_collection(name: str):
    if name not in COLLECTIONS:
        COLLECTIONS[name] = _get_client().get_or_create_collection(
            name=name,
            embedding_function=_get_embedding_fn(),
        )
    return COLLECTIONS[name]


def index_text(text: str, collection: str, doc_id: str, chunk_size: int = 400, overlap: int = 50):
    """Chunk text and index into the specified ChromaDB collection."""
    words = text.split()
    if not words:
        return 0

    col = _get_collection(collection)
    chunks = []
    i = 0
    while i < len(words):
        chunk = " ".join(words[i : i + chunk_size])
        chunks.append(chunk)
        i += chunk_size - overlap

    ids = [f"{doc_id}_chunk_{j}" for j in range(len(chunks))]
    col.upsert(documents=chunks, ids=ids)
    return len(chunks)


def index_directory(directory: str, collection: str):
    """Index all .txt files in a directory into the specified collection."""
    indexed = 0
    for fname in os.listdir(directory):
        if fname.endswith(".txt"):
            path = os.path.join(directory, fname)
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
            doc_id = fname.replace(".txt", "")
            indexed += index_text(text, collection, doc_id)
    return indexed


def clear_collection(name: str):
    """Delete and recreate a collection (reset between runs)."""
    try:
        _get_client().delete_collection(name)
    except Exception:
        pass
    # Clear ALL cached collection objects — deleting one collection can invalidate
    # the ChromaDB segment reader for others when using PersistentClient.
    COLLECTIONS.clear()


def rag_search(query: str, collection: str, top_k: int = 6) -> str:
    """Retrieve the most relevant chunks from a collection for a given query."""
    col = _get_collection(collection)
    count = col.count()
    if count == 0:
        return f"Collection '{collection}' is empty. Nothing indexed yet."

    results = col.query(query_texts=[query], n_results=min(top_k, count))
    docs = results.get("documents", [[]])[0]

    if not docs:
        return f"No relevant results found in '{collection}' for: {query}"

    formatted = "\n\n".join(
        f"### Result {i+1}\n{doc}" for i, doc in enumerate(docs)
    )
    return formatted
