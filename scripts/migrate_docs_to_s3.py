"""
Standalone migration: upload existing generated_docs/ to S3.
Run: python scripts/migrate_docs_to_s3.py
"""
import os
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
AGENT_ROOT = SCRIPT_DIR.parent
PROD_ROOT = AGENT_ROOT.parent
sys.path.insert(0, str(PROD_ROOT))
sys.path.insert(0, str(AGENT_ROOT))

from dotenv import load_dotenv
load_dotenv(AGENT_ROOT / ".env")

from s3_utils.operations import upload_file, object_exists
from s3_utils.helpers import generated_document_key
from s3_utils.config import get_s3_config


def extract_metadata(filename: str) -> dict:
    """Parse project_id and trade from filename pattern."""
    match = re.match(r"^(.+?)_(.+?)_(.+?)_(\d+)_([a-f0-9]{8})\.docx$", filename)
    if match:
        return {
            "doc_type": match.group(1),
            "trade": match.group(2),
            "slug": match.group(3),
            "project_id": int(match.group(4)),
        }
    # Try exhibit pattern: Exhibit_{slug}_{trade}_{type}_{pid}_{uuid}.docx
    match = re.match(r"^Exhibit_(.+?)_(.+?)_(.+?)_(\d+)_([a-f0-9]{8})\.docx$", filename)
    if match:
        return {
            "doc_type": "Exhibit",
            "slug": match.group(1),
            "trade": match.group(2),
            "project_id": int(match.group(4)),
        }
    return {}


def migrate():
    config = get_s3_config()
    if not config.is_s3_enabled:
        print("ERROR: STORAGE_BACKEND is not 's3'. Set it in .env first.")
        return

    docs_dir = AGENT_ROOT / "generated_docs"
    if not docs_dir.exists():
        print(f"No generated_docs/ directory found at {docs_dir}")
        return

    files = list(docs_dir.glob("*.docx"))
    print(f"Found {len(files)} documents to migrate.")

    migrated = skipped = failed = 0
    for f in files:
        meta = extract_metadata(f.name)
        if not meta:
            print(f"  SKIP (unrecognized name): {f.name}")
            skipped += 1
            continue

        s3_key = generated_document_key(
            config.agent_prefix,
            meta.get("slug", ""),
            meta["project_id"],
            meta["trade"],
            f.name,
        )
        if object_exists(s3_key):
            print(f"  EXISTS: {s3_key}")
            skipped += 1
            continue

        if upload_file(str(f), s3_key):
            print(f"  UPLOADED: {s3_key}")
            migrated += 1
        else:
            print(f"  FAILED: {f.name}")
            failed += 1

    print(f"\nMigration complete: {migrated} uploaded, {skipped} skipped, {failed} failed")


if __name__ == "__main__":
    migrate()
