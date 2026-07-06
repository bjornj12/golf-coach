"""The `Source` protocol every data source (Trackman, GameBook, ...) implements.

This is the interface the source registry and the MCP tools consume. A source
normalizes its own raw shape into the shared model (`..model`) before handing
data back — sources carry no coaching opinions, just data plus enough context
(`SourceContext`) for a downstream analyzer to reason about trust/coverage.

Note: `auth` is intentionally NOT part of this protocol. Only some sources
(e.g. Trackman, which needs a captured bearer token) support authentication;
callers check `"auth" in source.supports()` and duck-type an `auth(...)` method
on the concrete source rather than the protocol requiring one everywhere.
"""

from __future__ import annotations

from typing import Any, Literal, Protocol, runtime_checkable

from ..model import ClubGapping, Finding, Handicap, Profile, Round, Session, SourceContext

Capability = Literal["rounds", "sessions", "profile", "handicap", "clubs", "auth"]


@runtime_checkable
class Source(Protocol):
    name: str
    context: SourceContext

    def supports(self) -> set[str]: ...

    async def rounds(self, **filters: Any) -> list[Round]: ...

    async def sessions(self, **filters: Any) -> list[Session]: ...

    async def profile(self) -> Profile | None: ...

    async def handicap(self) -> Handicap | None: ...

    async def club_gapping(self) -> ClubGapping | None: ...

    async def analyze(self) -> list[Finding]:
        """Fetch this source's data and run its expert analyzer, returning
        findings ([] if unavailable)."""
        ...
