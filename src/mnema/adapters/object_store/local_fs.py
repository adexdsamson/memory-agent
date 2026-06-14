"""LocalFS — local filesystem T0 object store adapter.

Satisfies ObjectStorePort Protocol by structural typing.

T0 layout:
  {base_dir}/{session_id}.jsonl  — one JSONL file per session, one Turn JSON per line
  t0_ref format: "t0://{session_id}/{line_offset}"  (0-based line number)

append(session_id, turn) -> "t0://session_id/0" for the first turn, etc.
get("t0://session_id/N") -> Turn at line N of session_id.jsonl

Security (T-1-06 mitigation): session_id is validated against an allowlist pattern
before path construction. A session_id containing '..' or path separators raises
ValueError to prevent directory traversal.

I/O note (D-13 cleanup): file I/O here is sync inside async wrappers, which is
acceptable for the local-only path (Phase 1). Mark for asyncio.to_thread wrap
in Phase 4 if performance profiling reveals contention.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from mnema.core.schema import MemoryRecord, Turn

# ---------------------------------------------------------------------------
# session_id validation (T-1-06: path traversal prevention)
# ---------------------------------------------------------------------------
_VALID_SESSION_ID = re.compile(r"^[A-Za-z0-9_\-]+$")


def _validate_session_id(session_id: str) -> None:
    """Raise ValueError if session_id contains characters that could be used for path traversal.

    Only alphanumeric characters, hyphens, and underscores are permitted (T-1-06 mitigation).
    """
    if not _VALID_SESSION_ID.match(session_id):
        raise ValueError(
            f"Invalid session_id {session_id!r}: only alphanumeric characters, "
            "hyphens, and underscores are permitted."
        )


# ---------------------------------------------------------------------------
# LocalFS
# ---------------------------------------------------------------------------
class LocalFS:
    """Local filesystem T0 object store — JSONL per session, append-only.

    Satisfies ObjectStorePort Protocol by structural typing.
    """

    def __init__(self, base_dir: str) -> None:
        self._base = Path(base_dir)
        self._base.mkdir(parents=True, exist_ok=True)

    async def append(self, session_id: str, turn: Turn) -> str:
        """Append a Turn to the session JSONL file; returns a t0://session_id/N ref.

        The returned ref is the 0-based line offset of the appended turn.
        """
        _validate_session_id(session_id)
        path = self._base / f"{session_id}.jsonl"

        # Count existing lines to determine the offset of the new turn
        line_count = 0
        if path.exists():
            with path.open("r", encoding="utf-8") as fh:
                for _ in fh:
                    line_count += 1

        # Append the new turn
        with path.open("a", encoding="utf-8") as fh:
            fh.write(turn.model_dump_json() + "\n")

        return f"t0://{session_id}/{line_count}"

    async def get(self, ref: str) -> Turn:
        """Retrieve the Turn at the given t0://session_id/offset ref.

        Raises ValueError if the ref format is invalid, the session file does not
        exist, or the offset is out of range.
        """
        # Parse ref
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
            offset = int(offset_str)
        except ValueError:
            raise ValueError(f"Invalid t0 ref offset: {offset_str!r} in {ref!r}")

        path = self._base / f"{session_id}.jsonl"
        if not path.exists():
            raise ValueError(f"No T0 log for session_id {session_id!r}")

        with path.open("r", encoding="utf-8") as fh:
            for i, line in enumerate(fh):
                if i == offset:
                    return Turn.model_validate(json.loads(line))

        raise ValueError(
            f"T0 ref {ref!r}: offset {offset} is out of range for session {session_id!r}"
        )

    async def archive(self, record: MemoryRecord) -> str:
        """Archive a T1 record to cold storage; returns an archive ref.

        Phase 3 eviction path — appends a full record JSON line to archived.jsonl.
        """
        path = self._base / "archived.jsonl"
        with path.open("a", encoding="utf-8") as fh:
            fh.write(record.model_dump_json() + "\n")
        return f"archived://{record.id}"

    async def append_audit(self, entry: dict) -> None:  # type: ignore[type-arg]
        """Append one eviction audit entry to the JSONL audit log (FORG-04).

        Writes json.dumps(entry) + newline to {base_dir}/eviction_audit.jsonl.
        Multiple calls append multiple lines — idempotent append, not overwrite.
        """
        import json  # noqa: PLC0415

        path = self._base / "eviction_audit.jsonl"
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
