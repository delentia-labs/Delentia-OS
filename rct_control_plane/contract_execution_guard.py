"""Per-task optional transaction guard for an explicitly bound execution."""
from contextvars import ContextVar
from typing import Any, Callable, Optional

execution_guard: ContextVar[Optional[Callable[[Any, dict, str], None]]] = ContextVar('contract_execution_guard', default=None)
