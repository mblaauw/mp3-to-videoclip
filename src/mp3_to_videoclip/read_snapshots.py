"""Opt-in scopes for synchronous read services and FastAPI read endpoints."""

import functools
import inspect

from .storage import read_snapshot


def read_operation(function):
    @functools.wraps(function)
    def scoped(root, *args, **kwargs):
        with read_snapshot(root):
            return function(root, *args, **kwargs)

    return scoped


def read_endpoint(function):
    """Preserve FastAPI's typed signature while moving reads to its worker pool."""
    signature = inspect.signature(function, eval_str=True)

    @functools.wraps(function)
    def scoped(*args, **kwargs):
        from .api._helpers import project_root

        bound = signature.bind(*args, **kwargs)
        root = project_root(bound.arguments["request"], bound.arguments["slug"])
        with read_snapshot(root):
            return function(*args, **kwargs)

    scoped.__signature__ = signature
    return scoped
