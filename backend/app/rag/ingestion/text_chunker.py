from langchain_text_splitters import RecursiveCharacterTextSplitter


class TextChunker:
    def __init__(self, chunk_size: int = 1500, chunk_overlap: int = 150):
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

    def chunk_text(self, text: str) -> list[dict]:
        docs = self._splitter.create_documents([text])
        return [{"text": doc.page_content, "chunk_index": i} for i, doc in enumerate(docs)]
