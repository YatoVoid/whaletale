"""WhaleTale shared schemas.

The single source of truth for types that cross the edge/cloud/web boundary
(spec Section 15). Cloud SQLAlchemy models and, from M6, generated TypeScript
types both derive from these Pydantic models. Do not define the same object
twice.
"""

from schemas import enums, models

__all__ = ["enums", "models"]
