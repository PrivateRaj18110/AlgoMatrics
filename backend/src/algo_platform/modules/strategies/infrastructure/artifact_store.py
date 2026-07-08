"""Uploaded strategy artifact storage and static validation.

Uploaded code is stored under the artifact directory keyed by checksum and
statically screened with an AST pass that rejects imports and calls outside
the strategy sandbox surface. Uploaded strategies are restricted to paper
mode until a platform administrator approves the version for live use;
container isolation is the roadmap for untrusted marketplace code.
"""

from __future__ import annotations

import ast
import hashlib
from dataclasses import dataclass
from pathlib import Path

from algo_platform.shared.domain.errors import ValidationFailed

_FORBIDDEN_IMPORTS = {
    "os",
    "sys",
    "subprocess",
    "socket",
    "shutil",
    "pathlib",
    "importlib",
    "ctypes",
    "multiprocessing",
    "threading",
    "signal",
    "inspect",
    "pickle",
    "marshal",
    "urllib",
    "http",
    "ftplib",
    "telnetlib",
    "smtplib",
    "requests",
    "httpx",
    "aiohttp",
}

_FORBIDDEN_CALLS = {"eval", "exec", "open", "compile", "__import__", "input", "breakpoint"}

_ALLOWED_IMPORT_PREFIXES = (
    "algo_strategy_sdk",
    "collections",
    "dataclasses",
    "datetime",
    "decimal",
    "enum",
    "math",
    "statistics",
    "typing",
    "itertools",
    "functools",
    "json",
    "random",
    "uuid",
)

_MAX_ARTIFACT_BYTES = 256 * 1024


@dataclass(frozen=True, slots=True)
class ValidatedArtifact:
    checksum: str
    entry_point: str
    class_name: str


def validate_strategy_source(source: str, *, entry_class: str) -> ValidatedArtifact:
    if len(source.encode("utf-8")) > _MAX_ARTIFACT_BYTES:
        raise ValidationFailed("strategy file must be 256 KB or smaller")
    try:
        tree = ast.parse(source)
    except SyntaxError as error:
        raise ValidationFailed(f"strategy file has a syntax error: {error.msg}") from error

    class_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                _check_import(alias.name)
        elif isinstance(node, ast.ImportFrom):
            _check_import(node.module or "")
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in _FORBIDDEN_CALLS:
                raise ValidationFailed(f"strategy code may not call '{func.id}'")
        elif isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            raise ValidationFailed("dunder attribute access is not allowed in strategies")
        elif isinstance(node, ast.ClassDef):
            class_names.add(node.name)

    if entry_class not in class_names:
        raise ValidationFailed(f"strategy file must define the entry class '{entry_class}'")
    checksum = hashlib.sha256(source.encode("utf-8")).hexdigest()
    return ValidatedArtifact(checksum=checksum, entry_point=entry_class, class_name=entry_class)


def _check_import(module: str) -> None:
    root = module.split(".")[0]
    if root in _FORBIDDEN_IMPORTS:
        raise ValidationFailed(f"strategy code may not import '{root}'")
    if root and not module.startswith(_ALLOWED_IMPORT_PREFIXES):
        raise ValidationFailed(f"import '{module}' is outside the strategy sandbox allowlist")


class ArtifactStore:
    def __init__(self, base_dir: Path) -> None:
        self._base = base_dir

    def save(self, *, checksum: str, source: str) -> str:
        self._base.mkdir(parents=True, exist_ok=True)
        relative = f"strategies/{checksum}.py"
        target = self._base / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source, encoding="utf-8")
        return relative

    def load(self, relative_path: str, *, expected_checksum: str) -> str:
        target = (self._base / relative_path).resolve()
        base = self._base.resolve()
        if not str(target).startswith(str(base)):
            raise ValidationFailed("artifact path escapes the artifact store")
        if not target.is_file():
            raise ValidationFailed("strategy artifact is missing")
        source = target.read_text(encoding="utf-8")
        actual = hashlib.sha256(source.encode("utf-8")).hexdigest()
        if actual != expected_checksum:
            raise ValidationFailed("strategy artifact checksum mismatch")
        return source
