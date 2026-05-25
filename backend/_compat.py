from __future__ import annotations

from dataclasses import dataclass


def build_slots_dataclass(dataclass_fn=dataclass):
    def decorator(cls=None, **kwargs):
        def wrap(inner_cls):
            try:
                return dataclass_fn(inner_cls, slots=True, **kwargs)
            except TypeError as exc:
                if "slots" not in str(exc):
                    raise
                return dataclass_fn(inner_cls, **kwargs)

        if cls is None:
            return wrap
        return wrap(cls)

    return decorator


slots_dataclass = build_slots_dataclass()
