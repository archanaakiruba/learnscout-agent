import os
from pypdf import PdfReader


def read_file(file_path: str) -> str:
    """Read a PDF or text file and return its content as a string."""
    if not os.path.exists(file_path):
        return f"Error: file not found at {file_path}"

    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".pdf":
        reader = PdfReader(file_path)
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n".join(pages).strip()

    if ext in (".txt", ".md"):
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read().strip()

    return f"Error: unsupported file type '{ext}'. Supported: .pdf, .txt, .md"
