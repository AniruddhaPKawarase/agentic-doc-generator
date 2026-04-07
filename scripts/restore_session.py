#!/usr/bin/env python3
"""Restore sessions from S3 backup after restart."""
import sys

sys.path.insert(0, ".")

from config import get_settings
from s3_utils.operations import list_objects

settings = get_settings()
prefix = f"{settings.s3_agent_prefix}/sessions/"
objects = list_objects(prefix, max_keys=100)
print(f"Found {len(objects)} session backups in S3")
for obj in objects:
    key = obj["Key"]
    session_id = key.split("/")[-1].replace(".json", "")
    print(f"  - {session_id} ({obj.get('Size', 0)} bytes)")
