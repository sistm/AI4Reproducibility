"""
validate_outputs.py

Validates that the Review agent generated all 4 required outputs:
- final_review.md
- exhaustive_audit_report.md
- checklist.md
- risk_matrix.json

This prevents incomplete reviews from being accepted.
"""

import os
import sys


def validate_review_outputs(review_dir):
    """
    Validate all 4 required Review agent outputs exist
    
    Args:
        review_dir: Path to the review directory
    
    Returns:
        tuple: (success: bool, missing: list)
    """
    required_outputs = [
        'final_review.md',
        'exhaustive_audit_report.md',
        'checklist.md',
        'risk_matrix.json'
    ]
    
    review_path = os.path.join(review_dir, 'review')
    
    if not os.path.exists(review_path):
        print(f"❌ Review directory not found: {review_path}")
        return False, []
    
    missing = []
    
    for output in required_outputs:
        output_path = os.path.join(review_path, output)
        if not os.path.exists(output_path):
            missing.append(output_path)
            print(f"   ❌ Missing: {output}")
    
    if missing:
        print(f"⚠️  Missing {len(missing)}/{len(required_outputs)} outputs")
        return False, missing
    else:
        print(f"✅ All {len(required_outputs)} outputs present")
        return True, []


if __name__ == '__main__':
    import sys
    
    if len(sys.argv) > 1:
        review_dir = sys.argv[1]
        print(f"🔍 Validating Review outputs for: {review_dir}")
        success, missing = validate_review_outputs(review_dir)
        
        if success:
            print("✅ Validation passed")
            sys.exit(0)
        else:
            print("❌ Validation failed - missing outputs detected")
            sys.exit(1)
    else:
        print("❌ Usage: python validate_outputs.py <review_directory>")
        sys.exit(1)
