from typing import Iterator

from ..engine.registry import Registry


def registry() -> Iterator[Registry]:
    r = Registry()
    try:
        yield r
    finally:
        r.close()
