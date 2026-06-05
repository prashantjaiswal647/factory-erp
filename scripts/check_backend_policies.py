from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


HTTP_METHODS = {"get", "post", "put", "patch", "delete"}
BULK_WRITE_MARKERS = {"bulk", "upload", "import"}
NON_WRITE_MARKERS = {"validate", "preview", "template", "download"}
REQUEST_PARAM_NAMES = {"payload", "body", "data", "input", "request_data"}
TENANT_FIELD_ALIASES = {
    "factory_id",
    "tenant_id",
    "factoryId",
    "factory_id_str",
    "factory_id_int",
}


@dataclass(frozen=True)
class Violation:
    rule: str
    path: Path
    line: int
    message: str

    def format(self, root: Path) -> str:
        try:
            display_path = self.path.relative_to(root)
        except ValueError:
            display_path = self.path
        return f"{display_path}:{self.line}: {self.rule} {self.message}"


def _attribute_chain(node: ast.AST) -> tuple[str, ...]:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return tuple(reversed(parts))


def _call_name(node: ast.Call) -> str:
    chain = _attribute_chain(node.func)
    return ".".join(chain)


def _decorated_endpoint(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for decorator in node.decorator_list:
        call = decorator if isinstance(decorator, ast.Call) else None
        chain = _attribute_chain(call.func if call else decorator)
        if chain and chain[-1] in HTTP_METHODS:
            return True
    return False


def _endpoint_paths(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    paths: list[str] = []
    for decorator in node.decorator_list:
        if not isinstance(decorator, ast.Call):
            continue
        chain = _attribute_chain(decorator.func)
        if not chain or chain[-1] not in HTTP_METHODS or not decorator.args:
            continue
        first_arg = decorator.args[0]
        if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
            paths.append(first_arg.value.lower())
    return paths


def _has_attribute(node: ast.AST, owner: str, attribute: str) -> bool:
    return any(
        isinstance(child, ast.Attribute)
        and child.attr == attribute
        and isinstance(child.value, ast.Name)
        and child.value.id == owner
        for child in ast.walk(node)
    )


def _has_dependency(node: ast.AST, dependency_name: str) -> bool:
    return any(
        (
            isinstance(child, ast.Call)
            and _call_name(child).endswith(dependency_name)
        )
        or (
            isinstance(child, ast.Name)
            and child.id == dependency_name
        )
        for child in ast.walk(node)
    )


def _delegates_current_user_to_bulk_helper(node: ast.AST) -> bool:
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        call_name = _call_name(child).lower()
        if not any(marker in call_name for marker in BULK_WRITE_MARKERS):
            continue
        if any(isinstance(arg, ast.Name) and arg.id == "current_user" for arg in child.args):
            return True
    return False


def _is_bulk_write_path(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    searchable = " ".join([node.name.lower(), *_endpoint_paths(node)])
    if not any(marker in searchable for marker in BULK_WRITE_MARKERS):
        return False
    if any(marker in searchable for marker in NON_WRITE_MARKERS):
        return False
    return any(arg.arg == "current_user" for arg in node.args.args)


def check_factory_scope(path: Path, tree: ast.AST) -> list[Violation]:
    violations: list[Violation] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not _is_bulk_write_path(node):
            continue
        if not (
            _has_attribute(node, "current_user", "factory_id")
            or _delegates_current_user_to_bulk_helper(node)
        ):
            violations.append(
                Violation(
                    "T0.2",
                    path,
                    node.lineno,
                    "authenticated bulk/upload/import endpoint must use current_user.factory_id",
                )
            )
    return violations


def check_request_factory_id(path: Path, tree: ast.AST) -> list[Violation]:
    if path.name == "super_admin.py":
        return []

    violations: list[Violation] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not _decorated_endpoint(node):
            continue

        request_factory_accesses = [
            child
            for child in ast.walk(node)
            if isinstance(child, ast.Attribute)
            and child.attr in TENANT_FIELD_ALIASES
            and isinstance(child.value, ast.Name)
            and child.value.id in REQUEST_PARAM_NAMES
        ]
        if not request_factory_accesses:
            continue

        trusted_system_route = _has_dependency(node, "require_n8n_api_key")
        authenticated_tenant_route = _has_attribute(node, "current_user", "factory_id")
        if trusted_system_route or authenticated_tenant_route:
            continue

        for access in request_factory_accesses:
            violations.append(
                Violation(
                    "T0.3",
                    path,
                    access.lineno,
                    f"request-supplied tenant field '{access.attr}' requires current_user.factory_id or an explicit trusted-system dependency",
                )
            )
    return violations


def check_create_all(path: Path, tree: ast.AST) -> list[Violation]:
    violations: list[Violation] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        chain = _attribute_chain(node.func)
        if len(chain) >= 2 and chain[-2:] == ("metadata", "create_all"):
            violations.append(
                Violation(
                    "T0.4",
                    path,
                    node.lineno,
                    "metadata.create_all() is prohibited outside tests and Alembic revisions",
                )
            )
    return violations


def _python_files(directory: Path) -> Iterable[Path]:
    if not directory.exists():
        return ()
    return sorted(path for path in directory.rglob("*.py") if "__pycache__" not in path.parts)


def run_checks(root: Path) -> list[Violation]:
    api_root = root / "apps" / "api"
    violations: list[Violation] = []

    router_root = api_root / "routers"
    for path in _python_files(router_root):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        violations.extend(check_factory_scope(path, tree))
        violations.extend(check_request_factory_id(path, tree))

    excluded_roots = {
        api_root / "tests",
        api_root / "alembic" / "versions",
    }
    for path in _python_files(api_root):
        if any(excluded == path or excluded in path.parents for excluded in excluded_roots):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        violations.extend(check_create_all(path, tree))

    return sorted(violations, key=lambda item: (str(item.path), item.line, item.rule))


def main() -> int:
    parser = argparse.ArgumentParser(description="Enforce Munshi AI backend safety policies.")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root. Defaults to the parent of scripts/.",
    )
    args = parser.parse_args()
    root = args.root.resolve()
    violations = run_checks(root)
    if violations:
        for violation in violations:
            print(violation.format(root))
        print(f"Backend policy checks failed: {len(violations)} violation(s).")
        return 1
    print("Backend policy checks passed: T0.2, T0.3, T0.4.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
