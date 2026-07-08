"""Architecture tests: dependency rules from FOUNDATION.md, enforced.

- Domain layers import no framework, ORM, broker SDK, transport, or Redis.
- Domain layers do not import application or infrastructure layers.
- Bounded contexts do not import another context's infrastructure
  (shared infrastructure and public application facades are allowed).
"""

from __future__ import annotations

import ast
from pathlib import Path

BACKEND_SRC = Path(__file__).resolve().parents[2] / "backend" / "src"
PLATFORM = BACKEND_SRC / "algo_platform"

FORBIDDEN_IN_DOMAIN = {
    "sqlalchemy",
    "fastapi",
    "starlette",
    "httpx",
    "redis",
    "alembic",
    "asyncpg",
    "jwt",
    "pydantic_settings",
}

# Cross-context imports allowed for non-presentation code. Presentation layers
# are composition points and may wire other contexts' application services;
# everything else must use these consciously whitelisted facades. Read-model
# projections over another context's tables are listed explicitly.
ALLOWED_CROSS_CONTEXT = {
    ("organizations", "identity"): {"application.directory"},
    ("brokerage", "billing"): {"application.service"},
    ("trading", "billing"): {"application.service"},
    ("trading", "risk"): {"application.service"},
    ("trading", "brokerage"): {
        "application.service",
        "infrastructure.repositories",
        "infrastructure.models",  # engine cash/equity projection
    },
    ("trading", "instruments"): {
        "application.directory",
        "application.venue_directory",
    },
    ("trading", "notifications"): {"application.service"},
    ("trading", "organizations"): {"application.policy"},
    ("trading", "portfolio"): {"infrastructure.models"},  # snapshot writer
    ("strategies", "billing"): {"application.service"},
    ("strategies", "risk"): {"application.service"},
    ("strategies", "brokerage"): {"infrastructure.repositories"},
    ("strategies", "trading"): {
        "application.order_service",
        "infrastructure.models",
        "infrastructure.repositories",
    },
    ("strategies", "instruments"): {
        "application.directory",
        "application.venue_directory",
    },
    ("strategies", "market_data"): {"application.simulator"},
    ("strategies", "notifications"): {"application.service"},
    ("strategies", "organizations"): {"application.policy"},
    ("billing", "notifications"): {"application.service"},
    ("portfolio", "brokerage"): {"infrastructure.models"},  # read model join
    ("portfolio", "instruments"): {"application.directory"},
    ("portfolio", "trading"): {"infrastructure.models"},  # read model join
}

# Platform-wide technical services usable from any context.
GLOBALLY_ALLOWED_TARGETS = {
    ("audit", "application.service"),
    ("audit", "infrastructure.models"),
}


def iter_python_files(base: Path) -> list[Path]:
    return sorted(p for p in base.rglob("*.py") if "__pycache__" not in p.parts)


def imports_of(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.append(node.module)
    return found


def test_domain_layers_are_framework_free() -> None:
    violations: list[str] = []
    domain_files = [p for p in iter_python_files(PLATFORM) if "domain" in p.parts]
    assert domain_files, "no domain files found - check repository layout"
    for path in domain_files:
        for module in imports_of(path):
            root = module.split(".")[0]
            if root in FORBIDDEN_IN_DOMAIN:
                violations.append(f"{path.relative_to(BACKEND_SRC)} imports {module}")
    assert not violations, "domain must stay framework-free:\n" + "\n".join(violations)


def test_domain_does_not_import_outer_layers() -> None:
    violations: list[str] = []
    for path in iter_python_files(PLATFORM / "modules"):
        if "domain" not in path.parts:
            continue
        for module in imports_of(path):
            if not module.startswith("algo_platform"):
                continue
            if (
                ".infrastructure" in module
                or ".presentation" in module
                or (".application" in module)
            ):
                violations.append(f"{path.relative_to(BACKEND_SRC)} imports {module}")
    assert not violations, "domain must not depend on outer layers:\n" + "\n".join(violations)


def test_cross_context_imports_use_public_facades() -> None:
    violations: list[str] = []
    modules_dir = PLATFORM / "modules"
    for path in iter_python_files(modules_dir):
        parts = path.relative_to(modules_dir).parts
        source_context = parts[0]
        in_presentation = "presentation" in parts
        for module in imports_of(path):
            prefix = "algo_platform.modules."
            if not module.startswith(prefix):
                continue
            remainder = module[len(prefix) :]
            target_context = remainder.split(".")[0]
            if target_context == source_context:
                continue
            target_path = remainder[len(target_context) + 1 :]
            # Domain value objects/enums are a context's public contract.
            if target_path.startswith("domain."):
                continue
            if (target_context, target_path) in GLOBALLY_ALLOWED_TARGETS:
                continue
            # Composition points may wire other contexts' application
            # services and presentation dependencies - never raw infra.
            if in_presentation and target_path.startswith(("application.", "presentation.")):
                continue
            allowed = ALLOWED_CROSS_CONTEXT.get((source_context, target_context), set())
            if target_path in allowed:
                continue
            violations.append(
                f"{path.relative_to(BACKEND_SRC)} -> {module} "
                f"(add an application facade or whitelist consciously)"
            )
    assert not violations, "cross-context imports must go through public facades:\n" + "\n".join(
        violations
    )
