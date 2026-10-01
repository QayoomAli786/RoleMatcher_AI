"""Portable column types that work with both PostgreSQL and SQLite."""

from __future__ import annotations

import uuid as _uuid

from sqlalchemy import String, Text, TypeDecorator
from sqlalchemy.dialects.postgresql import JSONB as _PG_JSONB
from sqlalchemy.dialects.postgresql import UUID as _PG_UUID


class JSONB(TypeDecorator):
    """Transparent JSONB that falls back to JSON/TEXT on SQLite."""

    impl = Text
    cache_ok = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._pg_type = _PG_JSONB(*args, **kwargs)

    @property
    def impl_callable(self):
        return self._pg_type if self._is_pg else Text

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return self._pg_type
        return dialect.type_descriptor(Text())

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if dialect.name == "postgresql":
            return value  # native JSONB
        import json
        return json.dumps(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        if dialect.name == "postgresql":
            return value  # already dict/list
        import json
        return json.loads(value)


class UUID(TypeDecorator):
    """Portable UUID that uses native UUID on PostgreSQL and CHAR(36) on SQLite."""

    impl = String(36)
    cache_ok = True

    def __init__(self, as_uuid: bool = True, **kwargs):
        super().__init__(**kwargs)
        self.as_uuid = as_uuid
        self._pg_type = _PG_UUID(as_uuid=as_uuid)

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return self._pg_type
        return dialect.type_descriptor(String(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if dialect.name == "postgresql":
            return value
        # SQLite: store as string
        if isinstance(value, _uuid.UUID):
            return str(value)
        return value

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        if dialect.name == "postgresql":
            return value if self.as_uuid else str(value)
        # SQLite: parse string back to UUID
        if self.as_uuid and isinstance(value, str):
            return _uuid.UUID(value)
        return value

    # Preserve ForeignKey behaviour
    def coerce_to_isomorphic_binary(self, obj):
        return self._pg_type.coerce_to_isomorphic_binary(obj)
