"""LocalFSVault — local filesystem T2 canonical vault adapter.

Satisfies VaultStore Protocol by structural typing (D-08).

T2 layout:
  {base_dir}/{user_id}.md  — one markdown file per user, sectioned by record_type.
  Each record is a markdown bullet point under the appropriate section header.
  Dedup: same summary/content → bullet skipped (D3-12 MVP dedup by string equality).

Security (T-03-03-01 mitigation): user_id is validated against an allowlist pattern
before path construction. A user_id containing '..' or path separators raises
ValueError to prevent directory traversal — mirrors LocalFS._validate_session_id().

Git-versioned: files are committed to the repo by the developer; no git commands
are issued here (TIER-03).

I/O note (D-13): file I/O here is sync inside async wrappers, acceptable for the
local-only MVP path. Mark for asyncio.to_thread wrap in Phase 4 if needed.
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

from mnema.core.schema import MemoryRecord

# ---------------------------------------------------------------------------
# user_id validation (T-03-03-01: path traversal prevention)
# ---------------------------------------------------------------------------

_VALID_USER_ID = re.compile(r"^[A-Za-z0-9_\-]+$")


def _validate_user_id(user_id: str) -> None:
    """Raise ValueError if user_id contains characters that could be used for path traversal.

    Only alphanumeric characters, hyphens, and underscores are permitted
    (T-03-03-01 mitigation — mirrors LocalFS._validate_session_id pattern).
    """
    if not _VALID_USER_ID.match(user_id):
        raise ValueError(
            f"Invalid user_id {user_id!r}: only alphanumeric characters, "
            "hyphens, and underscores are permitted."
        )


# ---------------------------------------------------------------------------
# LocalFSVault
# ---------------------------------------------------------------------------


class LocalFSVault:
    """T2 canonical vault — human-readable per-user markdown file.

    Satisfies VaultStore Protocol by structural typing.

    Writes {base_dir}/{user_id}.md — one file per user, sectioned by record_type.
    Each fact/preference/procedure/event is a markdown bullet point under its section.
    Dedup: same summary/content → bullet skipped (D3-12 MVP dedup).
    Git-versioned: the files are intended to be committed to the repository;
    no git commands are issued by this class.
    """

    def __init__(self, base_dir: str) -> None:
        self._base = Path(base_dir)
        self._base.mkdir(parents=True, exist_ok=True)

    def _vault_path(self, user_id: str) -> Path:
        """Return the vault file path for user_id after validating it (T-03-03-01)."""
        _validate_user_id(user_id)
        return self._base / f"{user_id}.md"

    async def promote(self, record: MemoryRecord) -> None:
        """Promote a confirmed, stable record into the T2 canonical vault.

        Idempotent: if the record's summary already appears in the file, returns
        without writing (D3-12 MVP dedup by string equality). Safe to call multiple
        times on the same record.

        Args:
            record: A confirmed (non-provisional), live MemoryRecord to promote.
        """
        path = self._vault_path(record.user_id)
        existing = path.read_text(encoding="utf-8") if path.exists() else ""

        # Compute the display summary — prefer record.summary, fall back to content[:80]
        summary = (record.summary or record.content[:80]).strip()

        # D3-12: dedup by exact bullet-line match (CR-02: not a raw substring search,
        # which would false-positive when a short summary appears inside a longer
        # existing bullet — e.g. "blood pressure" inside "has low blood pressure").
        bullet_line = f"- {summary}\n"
        if bullet_line in existing:
            return

        # Build the section header from the record_type: e.g. RecordType.FACT → "## Facts"
        section_header = f"## {record.record_type.value.capitalize()}s"
        bullet = bullet_line

        if section_header + "\n" in existing:
            # Insert bullet immediately after the section header line
            updated = existing.replace(
                section_header + "\n",
                section_header + "\n" + bullet,
                1,  # replace only the first occurrence
            )
        else:
            # Section does not exist yet — append a new section block
            updated = existing + f"\n{section_header}\n{bullet}"

        # lstrip() removes any leading whitespace from an initially-empty file
        final = updated.lstrip() if not existing else updated

        # CR-01: atomic write — write to a sibling temp file, then rename over the
        # target. os.replace() is atomic on POSIX and on Windows (unlike rename()).
        # A crash mid-write cannot leave the vault file truncated to zero bytes.
        tmp_fd, tmp_path_str = tempfile.mkstemp(dir=self._base, suffix=".tmp")
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
                fh.write(final)
            os.replace(tmp_path_str, path)
        except Exception:
            try:
                os.unlink(tmp_path_str)
            except OSError:
                pass
            raise

    async def get_user_model(self, user_id: str) -> str:
        """Return the current T2 user model markdown as a string.

        Returns an empty string if no vault file exists for user_id yet.
        Validates user_id before path construction (T-03-03-01).

        Args:
            user_id: The user whose vault model to retrieve.

        Returns:
            Markdown string of the user's canonical model, or "" if none exists.
        """
        path = self._vault_path(user_id)
        return path.read_text(encoding="utf-8") if path.exists() else ""
