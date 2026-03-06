import zipfile
from pathlib import Path


def extract_zip(zip_filepath: str) -> dict:
    """
    Extract a ZIP archive in place (into the same directory as the ZIP file).

    Args:
        zip_filepath (str): Path to the ZIP archive.

    Returns:
        dict: Structured result containing:
            - success (bool): Whether extraction succeeded
            - extracted_to (str): Directory where files were extracted
            - files_extracted (int): Number of files extracted
            - error (str | None): Error message if extraction failed
    """

    try:
        zip_path = Path(zip_filepath)

        if not zip_path.exists():
            return {
                "success": False,
                "extracted_to": None,
                "files_extracted": 0,
                "error": "ZIP file does not exist"
            }

        extract_dir = zip_path.parent

        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            members = zip_ref.namelist()
            zip_ref.extractall(extract_dir)

        return {
            "success": True,
            "extracted_to": str(extract_dir),
            "files_extracted": len(members),
            "error": None
        }

    except zipfile.BadZipFile:
        return {
            "success": False,
            "extracted_to": None,
            "files_extracted": 0,
            "error": "Invalid ZIP file"
        }

    except Exception as e:
        return {
            "success": False,
            "extracted_to": None,
            "files_extracted": 0,
            "error": str(e)
        }