"""Hardened XML reading on raw ``pyexpat``: no DTD, no entities, no network, bounded size/depth.

Any ``<!DOCTYPE`` (and so any ``<!ENTITY``) aborts parsing before an entity can be declared, so
external-entity and billion-laughs documents are rejected deterministically. External parameter
entities are never parsed. Element, depth and byte budgets are enforced while streaming."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO
from xml.parsers import expat

from .types import MAX_XML_BYTES, MAX_XML_DEPTH, MAX_XML_NODES, ProfileError

_CHUNK = 64 * 1024


class UnsafeXml(ProfileError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(code, message)


def split_name(name: str) -> tuple[str | None, str]:
    """Expat reports ``uri}local`` with ``namespace_separator='}'``."""
    if "}" in name:
        ns, _, local = name.partition("}")
        return ns, local
    return None, name


def _new_parser() -> expat.XMLParserType:
    parser = expat.ParserCreate(namespace_separator="}")
    parser.buffer_text = True
    parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)

    def refuse_doctype(*_: object) -> None:
        raise UnsafeXml("xml_dtd_forbidden", "XML with a DOCTYPE or entity declaration is refused")

    parser.StartDoctypeDeclHandler = refuse_doctype
    parser.EntityDeclHandler = refuse_doctype
    parser.ExternalEntityRefHandler = refuse_doctype
    return parser


def stream_xml(
    handle: IO[bytes],
    *,
    on_start: Callable[[str, dict[str, str], int, int], None],
    on_end: Callable[[str, str, int], None],
    max_bytes: int = MAX_XML_BYTES,
) -> None:
    """Drive callbacks: ``on_start(name, attrs, depth, line)`` and ``on_end(name, text, depth)``.

    ``text`` is the element's own character data (concatenated, not stripped)."""
    parser = _new_parser()
    depth = 0
    nodes = 0
    stack: list[list[str]] = []

    def start(name: str, attrs: dict[str, str]) -> None:
        nonlocal depth, nodes
        depth += 1
        nodes += 1
        if depth > MAX_XML_DEPTH:
            raise UnsafeXml("xml_too_deep", "XML nesting exceeds the depth limit")
        if nodes > MAX_XML_NODES:
            raise UnsafeXml("xml_too_large", "XML exceeds the element-count limit")
        stack.append([])
        on_start(name, attrs, depth, parser.CurrentLineNumber)

    def end(name: str) -> None:
        nonlocal depth
        text = "".join(stack.pop())
        on_end(name, text, depth)
        depth -= 1

    def chars(data: str) -> None:
        if stack:
            stack[-1].append(data)

    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.CharacterDataHandler = chars
    total = 0
    try:
        while True:
            chunk = handle.read(_CHUNK)
            if not chunk:
                parser.Parse(b"", True)
                break
            total += len(chunk)
            if total > max_bytes:
                raise UnsafeXml("xml_too_large", "XML exceeds the size limit")
            parser.Parse(chunk, False)
    except expat.ExpatError as exc:
        raise ProfileError("xml_malformed", f"XML is not well formed: {exc}") from exc
    except RecursionError as exc:  # pragma: no cover - depth is bounded above
        raise UnsafeXml("xml_too_deep", "XML nesting is too deep") from exc


@dataclass
class Node:
    tag: str
    ns: str | None
    attrs: dict[str, str]
    line: int
    text: str = ""
    children: list[Node] = field(default_factory=list)

    def find(self, tag: str) -> Node | None:
        for c in self.children:
            if c.tag == tag:
                return c
        return None

    def findall(self, tag: str) -> list[Node]:
        return [c for c in self.children if c.tag == tag]

    def value(self, tag: str) -> str | None:
        node = self.find(tag)
        return None if node is None else node.text.strip()


def parse_tree(path: Path, *, max_bytes: int = MAX_XML_BYTES) -> Node:
    """Whole-document tree for small structured documents (WITSML objects)."""
    root: list[Node] = []
    stack: list[Node] = []

    def on_start(name: str, attrs: dict[str, str], depth: int, line: int) -> None:
        ns, local = split_name(name)
        local_attrs = {split_name(k)[1]: v for k, v in attrs.items()}
        node = Node(local, ns, local_attrs, line)
        if stack:
            stack[-1].children.append(node)
        else:
            root.append(node)
        stack.append(node)

    def on_end(name: str, text: str, depth: int) -> None:
        stack.pop().text = text

    with path.open("rb") as handle:
        stream_xml(handle, on_start=on_start, on_end=on_end, max_bytes=max_bytes)
    if not root:
        raise ProfileError("xml_malformed", "XML has no root element")
    return root[0]


def iter_children(node: Node) -> Iterator[Node]:
    yield from node.children
