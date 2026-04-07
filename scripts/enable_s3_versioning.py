#!/usr/bin/env python3
"""Enable S3 versioning on the production bucket."""
import sys

sys.path.insert(0, ".")

from config import get_settings

settings = get_settings()

import boto3

s3 = boto3.client(
    "s3",
    region_name=settings.s3_region,
    aws_access_key_id=settings.aws_access_key_id,
    aws_secret_access_key=settings.aws_secret_access_key,
)
s3.put_bucket_versioning(
    Bucket=settings.s3_bucket_name,
    VersioningConfiguration={"Status": "Enabled"},
)
print(f"Versioning enabled on {settings.s3_bucket_name}")
