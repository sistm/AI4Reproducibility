from pathlib import Path


def list_files(directory: str) -> dict:
    """
    Recursively list all files in a directory and its subdirectories.

    Args:
        directory (str): Path to the directory to explore.

    Returns:
        dict: Structured result containing:
            - success (bool): Whether the operation succeeded
            - root_directory (str): Directory explored
            - files (list[str]): List of file paths
            - total_files (int): Number of files found
            - error (str | None): Error message if something failed
    """

    try:
        root = Path(directory)

        if not root.exists():
            return {
                "success": False,
                "root_directory": directory,
                "files": [],
                "total_files": 0,
                "error": "Directory does not exist"
            }

        if not root.is_dir():
            return {
                "success": False,
                "root_directory": directory,
                "files": [],
                "total_files": 0,
                "error": "Path is not a directory"
            }

        files = [str(p) for p in root.rglob("*") if p.is_file()]

        return {
            "success": True,
            "root_directory": str(root),
            "files": files,
            "total_files": len(files),
            "error": None
        }

    except Exception as e:
        return {
            "success": False,
            "root_directory": directory,
            "files": [],
            "total_files": 0,
            "error": str(e)
        }