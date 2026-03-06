import re


def clean_text(raw_text: str) -> dict:
    """
    Clean text extracted from a PDF by removing LaTeX math, commands,
    encoding artifacts, and excessive whitespace while preserving readable text.

    Args:
        raw_text (str): Raw text extracted from a PDF (e.g., output of pdf2text).

    Returns:
        dict: Structured result containing:
            - success (bool)
            - cleaned_text (str)
            - original_length (int)
            - cleaned_length (int)
            - error (str | None)
    """

    try:
        text = raw_text
        original_length = len(text)

        # Remove LaTeX math expressions
        text = re.sub(r"\$\$.*?\$\$", " ", text, flags=re.DOTALL)
        text = re.sub(r"\$.*?\$", " ", text)
        text = re.sub(r"\\\[.*?\\\]", " ", text, flags=re.DOTALL)
        text = re.sub(r"\\\(.*?\\\)", " ", text)

        # Remove LaTeX commands like \cite{}, \ref{}, \alpha
        text = re.sub(r"\\[a-zA-Z]+\{.*?\}", " ", text)
        text = re.sub(r"\\[a-zA-Z]+", " ", text)

        # Remove non-printable characters
        text = re.sub(r"[^\x20-\x7E\n\t]", " ", text)

        # Remove repeated punctuation artifacts
        text = re.sub(r"[\|\_]{2,}", " ", text)

        # Normalize whitespace
        text = re.sub(r"\s+", " ", text).strip()

        return {
            "success": True,
            "cleaned_text": text,
            "original_length": original_length,
            "cleaned_length": len(text),
            "error": None
        }

    except Exception as e:
        return {
            "success": False,
            "cleaned_text": None,
            "original_length": 0,
            "cleaned_length": 0,
            "error": str(e)
        }