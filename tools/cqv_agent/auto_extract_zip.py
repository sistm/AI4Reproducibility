"""
auto_extract_zip.py

Automatically extracts .zip files in the input/assets/ directory before CQV analysis.
This ensures code and data supplements are available for quality verification.
"""

import os
from tools.tools import run_tool


def auto_extract_zip(review_dir):
    """
    Extract all .zip files in review_dir/input/assets/
    
    Args:
        review_dir: Path to the review directory (e.g., /ai4r/review_title)
    
    Returns:
        list: Names of successfully extracted files
    """
    assets_dir = os.path.join(review_dir, 'input', 'assets')
    
    if not os.path.exists(assets_dir):
        print("ℹ️  No assets directory found, skipping extraction")
        return []
    
    zip_files = [f for f in os.listdir(assets_dir) if f.endswith('.zip')]
    
    if not zip_files:
        print("ℹ️  No .zip files found in assets directory")
        return []
    
    print(f"📦 Found {len(zip_files)} .zip file(s) to extract")
    extracted = []
    
    for zip_file in zip_files:
        zip_path = os.path.join(assets_dir, zip_file)
        print(f"📦 Extracting {zip_file}...")
        
        try:
            result = run_tool('extract_zip', zip_path=zip_path)
            if result.get('success', False):
                extracted.append(zip_file)
                print(f"✅ Successfully extracted: {zip_file}")
            else:
                print(f"⚠️  Failed to extract {zip_file}: {result.get('error', 'Unknown error')}")
        except Exception as e:
            print(f"⚠️  Exception extracting {zip_file}: {str(e)}")
    
    return extracted


if __name__ == '__main__':
    import sys
    
    if len(sys.argv) > 1:
        review_dir = sys.argv[1]
        print(f"🔧 Auto-extracting .zip files for review: {review_dir}")
        extracted = auto_extract_zip(review_dir)
        print(f"📊 Extracted {len(extracted)} file(s)")
    else:
        print("❌ Usage: python auto_extract_zip.py <review_directory>")
        sys.exit(1)
