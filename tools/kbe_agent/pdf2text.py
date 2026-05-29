"""
pdf2text.py - KBE Agent Tool
Extract raw text from a PDF file using pdfminer.six library.
"""

from pathlib import Path

from pdfminer.high_level import extract_text


def pdf2text(pdf_path: str) -> dict:
    """
    Extract raw text from a PDF file using pdfminer.six.
    
    Args:
        pdf_path (str): Path to the PDF file
        
    Returns:
        dict: Result containing:
            - success (bool): Whether extraction succeeded
            - text (str | None): Extracted text if successful
            - error (str | None): Error message if failed
    """
    try:
        pdf_file = Path(pdf_path)
        if not pdf_file.exists():
            return {
                "success": False,
                "text": None,
                "error": f"PDF file not found: {pdf_path}"
            }
        
        # Use pdfminer.six to extract text
        text = extract_text(str(pdf_file))
        
        return {
            "success": True,
            "text": text,
            "error": None
        }
        
    except Exception as e:
        return {
            "success": False,
            "text": None,
            "error": str(e)
        }
