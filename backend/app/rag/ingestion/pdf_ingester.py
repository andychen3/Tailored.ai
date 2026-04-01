from pypdf import PdfReader


class PDFIngester:
    def extract_pages(self, file_path: str) -> list[dict]:
        """Return a list of {"text": str, "page": int} for each PDF page."""
        reader = PdfReader(file_path)
        pages = []
        for i, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            text = text.strip()
            if text:
                pages.append({"text": text, "page": i + 1})
        return pages
