import os, logging
import boto3
from botocore.config import Config
from fastapi import HTTPException

logger = logging.getLogger(__name__)
_client = None


def storage_config():
    cfg = {k: (os.environ.get(k) or "").strip() for k in ("S3_BUCKET", "S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY", "S3_ENDPOINT", "S3_REGION")}
    cfg["enabled"] = bool(cfg["S3_BUCKET"] and cfg["S3_ACCESS_KEY_ID"] and cfg["S3_SECRET_ACCESS_KEY"])
    return cfg


def storage_enabled():
    return storage_config()["enabled"]


def client():
    global _client
    if _client is None:
        cfg = storage_config()
        if not cfg["enabled"]:
            raise HTTPException(503, "Penyimpanan file belum dikonfigurasi. Isi S3_BUCKET, S3_ACCESS_KEY_ID, S3_SECRET_ACCESS_KEY (dan S3_ENDPOINT untuk R2) di environment backend")
        _client = boto3.client(
            "s3",
            endpoint_url=cfg["S3_ENDPOINT"] or None,
            region_name=cfg["S3_REGION"] or "auto",
            aws_access_key_id=cfg["S3_ACCESS_KEY_ID"],
            aws_secret_access_key=cfg["S3_SECRET_ACCESS_KEY"],
            config=Config(signature_version="s3v4", retries={"max_attempts": 3}),
        )
    return _client


def put_object(path: str, data: bytes, content_type: str) -> str:
    client().put_object(Bucket=storage_config()["S3_BUCKET"], Key=path, Body=data, ContentType=content_type)
    return path


def get_object(path: str):
    obj = client().get_object(Bucket=storage_config()["S3_BUCKET"], Key=path)
    return obj["Body"].read(), obj.get("ContentType") or "application/octet-stream"
