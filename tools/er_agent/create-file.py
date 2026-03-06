from pathlib import Path


def create_file(filename: str, text: str) -> dict:
    """
    Create a file and write text content into it.

    Args:
        filename (str): Path and name of the file to create.
        text (str): Text content to write into the file.

    Returns:
        dict: Structured result containing:
            - success (bool): Whether the operation succeeded
            - filepath (str): Path to the created file
            - size_bytes (int): Size of the written content
            - error (str | None): Error message if something failed
    """

    try:
        path = Path(filename)

        # Create parent directories if they do not exist
        path.parent.mkdir(parents=True, exist_ok=True)

        path.write_text(text, encoding="utf-8")

        return {
            "success": True,
            "filepath": str(path),
            "size_bytes": path.stat().st_size,
            "error": None
        }

    except Exception as e:
        return {
            "success": False,
            "filepath": filename,
            "size_bytes": 0,
            "error": str(e)
        }