from pathlib import Path
import fitz


def pdf2text(pdf_path: str) -> dict:
    """
    Extract text from a PDF file.

    Args:
        pdf_path (str): Path to the PDF file.

    Returns:
        dict: Structured result containing:
            - success (bool): Whether extraction succeeded
            - pdf_path (str): Path to the PDF
            - text (str | None): Extracted text
            - pages (int): Number of pages processed
            - error (str | None): Error message if extraction failed
    """

    try:
        path = Path(pdf_path)

        if not path.exists():
            return {
                "success": False,
                "pdf_path": pdf_path,
                "text": None,
                "pages": 0,
                "error": "PDF file does not exist"
            }

        text = []
        pages = 0

        with fitz.open(path) as doc:
            pages = len(doc)
            for page in doc:
                text.append(page.get_text())

        return {
            "success": True,
            "pdf_path": str(path),
            "text": "\n".join(text),
            "pages": pages,
            "error": None
        }

    except Exception as e:
        return {
            "success": False,
            "pdf_path": pdf_path,
            "text": None,
            "pages": 0,
            "error": str(e)
        }