from pathlib import Path


def read_file(filepath: str) -> dict:
    """
    Read the content of a file.

    Args:
        filepath (str): Path to the file.

    Returns:
        dict: Structured result containing:
            - success (bool): Whether the read operation succeeded
            - filepath (str): Path to the file
            - content (str | None): File content if successful
            - size_bytes (int): File size in bytes
            - error (str | None): Error message if something failed
    """

    try:
        path = Path(filepath)

        if not path.exists():
            return {
                "success": False,
                "filepath": filepath,
                "content": None,
                "size_bytes": 0,
                "error": "File does not exist"
            }

        if not path.is_file():
            return {
                "success": False,
                "filepath": filepath,
                "content": None,
                "size_bytes": 0,
                "error": "Path is not a file"
            }

        content = path.read_text(encoding="utf-8", errors="replace")

        return {
            "success": True,
            "filepath": str(path),
            "content": content,
            "size_bytes": path.stat().st_size,
            "error": None
        }

    except Exception as e:
        return {
            "success": False,
            "filepath": filepath,
            "content": None,
            "size_bytes": 0,
            "error": str(e)
        }