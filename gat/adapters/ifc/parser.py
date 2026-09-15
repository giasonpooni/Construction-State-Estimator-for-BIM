"""Parser for the STEP Physical File structure (ISO 10303-21).

Purely syntactic: produces :class:`RawInstance` records with a recursive
argument model and no schema knowledge.  Unknown entity types survive as
opaque instances — the adapter is tolerant by design, and everything it
does not understand round-trips verbatim through the canonical writer.

Value model for instance arguments:

* ``int``, ``float``, ``str``
* ``EnumVal(name)`` — ``.T.``, ``.METRE.``
* ``Ref(step_id)`` — ``#123``
* ``None`` — ``$``
* ``OMITTED`` — ``*`` (a derived attribute placeholder)
* ``tuple`` — nested aggregate ``( ... )``
* ``Typed(name, args)`` — inline typed value, e.g. ``IFCREAL(320.)``
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from gat.adapters.ifc.lexer import TokKind, Token, tokenize
from gat.errors import SpfParseError


@dataclass(frozen=True)
class EnumVal:
    name: str


@dataclass(frozen=True)
class Ref:
    step_id: int


@dataclass(frozen=True)
class Typed:
    name: str
    args: tuple


class _Omitted:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "OMITTED"


OMITTED = _Omitted()


@dataclass(frozen=True)
class RawInstance:
    step_id: int
    type_name: str
    args: tuple


@dataclass
class IfcFile:
    header: dict[str, tuple]
    instances: dict[int, RawInstance]
    schema: str
    #: SHA-256 of the source bytes this file was parsed from.  It is the
    #: model's identity: the same bytes read through any path produce the
    #: same digest, which is what keeps a world digest path-independent.
    #: Empty only for a file assembled in memory without a source.
    content_sha256: str = ""

    def by_type(self, type_name: str) -> tuple[RawInstance, ...]:
        upper = type_name.upper()
        return tuple(
            inst
            for sid in sorted(self.instances)
            if (inst := self.instances[sid]).type_name == upper
        )

    def deref(self, ref: Ref) -> RawInstance:
        inst = self.instances.get(ref.step_id)
        if inst is None:
            raise SpfParseError(f"dangling reference #{ref.step_id}")
        return inst

    def max_step_id(self) -> int:
        return max(self.instances) if self.instances else 0


#: How deeply an argument list may nest before the file is refused.
#:
#: ``parse_arg_list`` and ``parse_value`` are mutually recursive, two Python
#: frames per level, so against the default 1000-frame limit a file nests
#: about 500 deep before the interpreter runs out of stack. That arrives as
#: ``RecursionError`` -- not a ``GatError``, so a caller catching the declared
#: hierarchy does not catch it, and a crafted file is a cheap way to knock
#: over anything parsing untrusted uploads.
#:
#: MEASURED, real IFC does not go deep: the shipped model nests 2, and the
#: public buildingSMART corpus nests 3 -- including a 317,671-instance
#: structural model. 64 is twenty times the deepest real file and an eighth
#: of what breaks, so it separates "malformed" from "large" without argument.
MAX_ARG_NESTING = 64


class _Parser:
    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.pos = 0
        self.depth = 0

    def peek(self) -> Token:
        if self.pos >= len(self.tokens):
            raise SpfParseError("unexpected end of file")
        return self.tokens[self.pos]

    def next(self) -> Token:
        tok = self.peek()
        self.pos += 1
        return tok

    def expect(self, kind: TokKind) -> Token:
        tok = self.next()
        if tok.kind is not kind:
            raise SpfParseError(
                f"expected {kind.value}, got {tok.kind.value} ({tok.value!r})",
                tok.line,
                tok.col,
            )
        return tok

    def expect_keyword(self, name: str) -> None:
        tok = self.expect(TokKind.KEYWORD)
        if str(tok.value).upper() != name:
            raise SpfParseError(f"expected {name}, got {tok.value!r}", tok.line, tok.col)

    def at_keyword(self, name: str) -> bool:
        tok = self.peek()
        return tok.kind is TokKind.KEYWORD and str(tok.value).upper() == name

    # -- grammar -----------------------------------------------------------

    def parse_file(self) -> IfcFile:
        self.expect_keyword("ISO-10303-21")
        self.expect(TokKind.SEMI)
        self.expect_keyword("HEADER")
        self.expect(TokKind.SEMI)

        header: dict[str, tuple] = {}
        while not self.at_keyword("ENDSEC"):
            tok = self.expect(TokKind.KEYWORD)
            args = self.parse_arg_list()
            self.expect(TokKind.SEMI)
            header[str(tok.value).upper()] = args
        self.expect_keyword("ENDSEC")
        self.expect(TokKind.SEMI)

        self.expect_keyword("DATA")
        self.expect(TokKind.SEMI)
        instances: dict[int, RawInstance] = {}
        while not self.at_keyword("ENDSEC"):
            ref_tok = self.expect(TokKind.REF)
            self.expect(TokKind.EQ)
            type_tok = self.expect(TokKind.KEYWORD)
            args = self.parse_arg_list()
            self.expect(TokKind.SEMI)
            step_id = int(ref_tok.value)
            if step_id in instances:
                raise SpfParseError(
                    f"duplicate instance #{step_id}", ref_tok.line, ref_tok.col
                )
            instances[step_id] = RawInstance(
                step_id, str(type_tok.value).upper(), args
            )
        self.expect_keyword("ENDSEC")
        self.expect(TokKind.SEMI)
        self.expect_keyword("END-ISO-10303-21")
        self.expect(TokKind.SEMI)

        schema = ""
        fs = header.get("FILE_SCHEMA")
        if fs and fs and isinstance(fs[0], tuple) and fs[0]:
            schema = str(fs[0][0])
        return IfcFile(header, instances, schema)

    def parse_arg_list(self) -> tuple:
        open_paren = self.peek()
        self.expect(TokKind.LPAREN)
        if self.depth >= MAX_ARG_NESTING:
            raise SpfParseError(
                f"argument list nests deeper than {MAX_ARG_NESTING}; refusing "
                "before the parser runs out of stack",
                open_paren.line,
                open_paren.col,
            )
        self.depth += 1
        try:
            args: list = []
            if self.peek().kind is TokKind.RPAREN:
                self.next()
                return tuple(args)
            while True:
                args.append(self.parse_value())
                tok = self.next()
                if tok.kind is TokKind.RPAREN:
                    return tuple(args)
                if tok.kind is not TokKind.COMMA:
                    raise SpfParseError(
                        f"expected ',' or ')', got {tok.value!r}", tok.line, tok.col
                    )
        finally:
            self.depth -= 1

    def parse_value(self):
        tok = self.peek()
        if tok.kind is TokKind.INT:
            self.next()
            return int(tok.value)
        if tok.kind is TokKind.REAL:
            self.next()
            return float(tok.value)
        if tok.kind is TokKind.STRING:
            self.next()
            return str(tok.value)
        if tok.kind is TokKind.ENUM:
            self.next()
            return EnumVal(str(tok.value))
        if tok.kind is TokKind.REF:
            self.next()
            return Ref(int(tok.value))
        if tok.kind is TokKind.DOLLAR:
            self.next()
            return None
        if tok.kind is TokKind.STAR:
            self.next()
            return OMITTED
        if tok.kind is TokKind.LPAREN:
            return self.parse_arg_list()
        if tok.kind is TokKind.KEYWORD:
            self.next()
            args = self.parse_arg_list()
            return Typed(str(tok.value).upper(), args)
        raise SpfParseError(f"unexpected token {tok.value!r}", tok.line, tok.col)


def parse_ifc(text: str, *, content_sha256: str | None = None) -> IfcFile:
    """Parse STEP text.

    ``content_sha256`` records the digest of the *bytes* the text came from.
    When omitted it is taken over the encoded text, so an in-memory model
    still gets a stable identity.
    """
    file = _Parser(tokenize(text)).parse_file()
    file.content_sha256 = (
        content_sha256
        if content_sha256 is not None
        else hashlib.sha256(text.encode("utf-8")).hexdigest()
    )
    return file


def parse_ifc_file(path: str) -> IfcFile:
    raw = Path(path).read_bytes()
    # Decode once and normalize line endings exactly as text mode would, so
    # the tokenizer sees what it always saw while the digest still covers
    # the bytes on disk.
    text = raw.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    return parse_ifc(text, content_sha256=hashlib.sha256(raw).hexdigest())
