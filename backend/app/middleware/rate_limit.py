"""Signature-preserving rate-limit decorator.

slowapi 0.1.9's `Limiter.limit` wraps the endpoint in `async def wrapper(*args, **kwargs)`
using `functools.wraps`. That copies `__annotations__` and `__wrapped__`, but it does NOT
set `__signature__` — and FastAPI 0.115's `get_typed_signature` reads `call.__globals__`
to resolve string annotations (which is what `from __future__ import annotations` turns
every type hint into). The wrapper's `__globals__` is slowapi's module, so names like
`RegisterRequest` / `AsyncSession` never resolve, and FastAPI silently treats every
parameter as an untyped query parameter.

This module exposes `rate_limit(...)` which applies the slowapi decorator and then
attaches a fully-resolved `__signature__` to the wrapper, computed against the ORIGINAL
function's module globals. FastAPI now sees concrete types (Annotated[RegisterRequest,
...], Annotated[AsyncSession, Depends(get_db)], ...) and bodies / dependencies bind
correctly.
"""
from __future__ import annotations

import inspect
import typing
from typing import Callable, TypeVar

from slowapi import Limiter

F = TypeVar("F", bound=Callable[..., object])


def rate_limit(limiter: Limiter, limit_value: str) -> Callable[[F], F]:
    """Apply slowapi's limiter and preserve the wrapped function's resolved signature.

    Usage:
        @router.post("/register", ...)
        @rate_limit(limiter, settings.RATE_LIMIT_AUTH)
        async def register(request: Request, payload: RegisterRequest, ...): ...
    """
    def decorator(func: F) -> F:
        wrapped = limiter.limit(limit_value)(func)

        # Resolve string annotations once, in the ORIGINAL function's module scope.
        # `include_extras=True` keeps `Annotated[X, Body()]` / `Annotated[X, Depends()]`
        # metadata intact — that's exactly what FastAPI uses to decide body vs dep.
        try:
            hints = typing.get_type_hints(func, include_extras=True)
        except Exception:
            hints = {}

        original_sig = inspect.signature(func)
        new_params = [
            p.replace(annotation=hints.get(p.name, p.annotation))
            for p in original_sig.parameters.values()
        ]
        wrapped.__signature__ = inspect.Signature(  # type: ignore[attr-defined]
            parameters=new_params,
            return_annotation=hints.get("return", original_sig.return_annotation),
        )
        # Mirror the resolved annotations dict for any consumer that reads it directly.
        wrapped.__annotations__ = hints
        return wrapped  # type: ignore[return-value]
    return decorator
