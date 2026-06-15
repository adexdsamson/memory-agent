"""OSSS3Store — S3-compatible T0 object store (Alibaba OSS / AWS S3 / MinIO).

Satisfies ObjectStorePort Protocol by structural typing.

endpoint_url=None for AWS S3; set to 'https://oss-{region}.aliyuncs.com' for
Alibaba OSS or the appropriate endpoint for MinIO / other S3-compatible stores.

Config(s3={'addressing_style':'path'}) is required for Alibaba OSS compatibility
(Pitfall 6 — OSS does not support virtual-hosted-style bucket addressing).

Sync boto3 client wrapped in asyncio.to_thread (D-13) for each I/O method, keeping
the async event loop unblocked.

One S3 object per turn (A6): key = '{session_id}/{offset}.json'. append() lists
existing objects under the session prefix to compute the next offset, then puts
the new object. This is NOT atomic under concurrent writes (list+put is not a
single transaction) — acceptable for v1 single-writer usage. On retry, the same
offset key is overwritten with the same data, making the operation idempotent.

API keys are accepted as constructor parameters from config — never hardcoded,
never logged. The class __repr__ deliberately omits credentials.

boto3 is in the 'cloud' extra. Importing this module without 'cloud' installed
raises ImportError at import time — that is the correct behavior for an optional
adapter; callers should guard with try/except ImportError.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

import boto3  # type: ignore[import-untyped]
from botocore.config import Config  # type: ignore[import-untyped]

from mnema.core.schema import MemoryRecord, Turn

# ---------------------------------------------------------------------------
# session_id validation (T-04-06-01: path traversal prevention)
# Copied verbatim from local_fs.py — same regex, same exception message.
# ---------------------------------------------------------------------------
_VALID_SESSION_ID = re.compile(r"^[A-Za-z0-9_\-]+$")


def _validate_session_id(session_id: str) -> None:
    """Raise ValueError if session_id contains characters that could be used for path traversal.

    Only alphanumeric characters, hyphens, and underscores are permitted (T-04-06-01 mitigation).
    """
    if not _VALID_SESSION_ID.match(session_id):
        raise ValueError(
            f"Invalid session_id {session_id!r}: only alphanumeric characters, "
            "hyphens, and underscores are permitted."
        )


# ---------------------------------------------------------------------------
# OSSS3Store
# ---------------------------------------------------------------------------


class OSSS3Store:
    """S3-compatible T0 object store — one S3 object per turn, append-only.

    Satisfies ObjectStorePort Protocol by structural typing.

    Supports Alibaba OSS, AWS S3, and MinIO via the S3-compatible API.
    Set endpoint_url to None for AWS S3, or to the provider endpoint for OSS/MinIO.

    Single-writer concurrency model: append() uses list_objects_v2 + put_object,
    which is not atomic. Concurrent writers may overwrite each other's offsets.
    This is documented and accepted for v1; multi-writer safety is deferred to v2.

    Credentials are stored inside the boto3 client and never exposed by __repr__.
    """

    def __init__(
        self,
        bucket: str,
        *,
        aws_access_key_id: str,
        aws_secret_access_key: str,
        endpoint_url: str | None = None,
        region_name: str = "us-east-1",
    ) -> None:
        """Construct an OSSS3Store.

        Args:
            bucket: Name of the S3 bucket to use.
            aws_access_key_id: Access key ID (from config — never hardcoded).
            aws_secret_access_key: Secret access key (from config — never hardcoded).
            endpoint_url: Override endpoint for OSS/MinIO (None for AWS S3).
            region_name: AWS/OSS region (default "us-east-1").
        """
        self._bucket = bucket
        # boto3 ships no type stubs; annotate as Any so pyright-strict does not flag
        # every dynamic client method (reportUnknownMemberType). Runtime behavior is
        # unaffected. (botocore-stubs/boto3-stubs would be the heavier typed alternative.)
        self._client: Any = boto3.client(  # type: ignore[reportUnknownMemberType]
            "s3",
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            endpoint_url=endpoint_url,
            region_name=region_name,
            config=Config(s3={"addressing_style": "path"}),  # OSS requires path-style — Pitfall 6
        )

    def __repr__(self) -> str:
        """Repr excludes credentials (T-04-06-02)."""
        return f"OSSS3Store(bucket={self._bucket!r})"

    async def append(self, session_id: str, turn: Turn) -> str:
        """Append a Turn as a new S3 object; returns a t0://session_id/N ref.

        Key layout: {session_id}/{offset}.json (0-based, one object per turn).
        offset is computed by counting existing objects under the session prefix.
        """
        _validate_session_id(session_id)

        def _call() -> str:
            resp = self._client.list_objects_v2(
                Bucket=self._bucket, Prefix=f"{session_id}/"
            )
            offset: int = resp.get("KeyCount", 0)
            key = f"{session_id}/{offset}.json"
            self._client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=turn.model_dump_json().encode(),
            )
            return f"t0://{session_id}/{offset}"

        return await asyncio.to_thread(_call)

    async def get(self, ref: str) -> Turn:
        """Retrieve the Turn at the given t0://session_id/N ref.

        Raises ValueError if the ref format is invalid.
        Raises botocore.exceptions.ClientError if the object does not exist in S3.
        """
        if not ref.startswith("t0://"):
            raise ValueError(f"Invalid t0 ref format: {ref!r} (expected 't0://session_id/N')")

        remainder = ref[len("t0://"):]
        slash_idx = remainder.rfind("/")
        if slash_idx == -1:
            raise ValueError(f"Invalid t0 ref format: {ref!r} (missing offset)")

        session_id = remainder[:slash_idx]
        offset_str = remainder[slash_idx + 1:]

        _validate_session_id(session_id)

        try:
            int(offset_str)  # validate it's a valid integer
        except ValueError:
            raise ValueError(f"Invalid t0 ref offset: {offset_str!r} in {ref!r}")

        def _call() -> Turn:
            key = f"{session_id}/{offset_str}.json"
            obj = self._client.get_object(Bucket=self._bucket, Key=key)
            return Turn.model_validate(json.loads(obj["Body"].read()))

        return await asyncio.to_thread(_call)

    async def archive(self, record: MemoryRecord) -> str:
        """Archive a T1 record to cold storage; returns an archived:// ref.

        Key layout: archived/{record.id}.json
        Never hard-deletes records — FORG-04 preserved.
        """

        def _call() -> str:
            key = f"archived/{record.id}.json"
            self._client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=record.model_dump_json().encode(),
            )
            return f"archived://{record.id}"

        return await asyncio.to_thread(_call)

    async def append_audit(self, entry: dict[str, Any]) -> None:
        """Append one eviction audit entry to the S3 audit prefix (FORG-04).

        Key layout: eviction_audit/{evicted_at}_{record_id}.json
        Timestamps with ':' are sanitized to '-' for S3 key safety.
        """

        def _call() -> None:
            ts = str(entry.get("evicted_at", "0")).replace(":", "-").replace(" ", "_")
            rid = str(entry.get("record_id", "unknown"))
            key = f"eviction_audit/{ts}_{rid}.json"
            self._client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=json.dumps(entry).encode(),
            )

        await asyncio.to_thread(_call)
