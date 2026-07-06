"""Pluggable data sources. Importing this package registers the built-in sources.

Importing the source submodules here (for their `registry.register(...)` side
effect) is what makes `synthesize()` see real sources at runtime: `synthesis`
does `from .sources import registry`, which runs this `__init__` and registers
both built-ins. The submodules only import leaf helpers (client/queries/config/
gamebook_store) and `..registry`, so no import cycle results.
"""

from .gamebook import source as _gamebook_source  # noqa: F401  (registers GameBookSource)
from .trackman import source as _trackman_source  # noqa: F401  (registers TrackmanSource)
