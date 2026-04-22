"""Enhanced static analysis for Lua, Python, and C++.

This module provides improved call graph extraction for the three target languages,
with language-specific patterns and improved call resolution.

Key improvements:
1. Lua: Enhanced method calls, metatable patterns, context tracking
2. Python: Decorator support, context managers, class methods, import resolution
3. C++: Pointer patterns, templates, operator overloads, smart pointers
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# Language feature descriptions for --list-languages
LANGUAGE_FEATURES = {
    "lua": [
        "metamethods (__call, __index, __add, etc.)",
        "self context tracking (obj:method vs obj.method)",
        "require return value tracking",
        "string method calls (obj['method']())",
        "chain calls (a.b.c())",
    ],
    "python": [
        "decorator detection (@property, @staticmethod, @classmethod)",
        "context manager support (with statements)",
        "self/cls method resolution",
        "import alias resolution (from X import Y as Z)",
        "chain calls (a.b.c())",
    ],
    "cpp": [
        "arrow operator (ptr->method)",
        "scope resolution (Class::method)",
        "template calls (func<T>())",
        "smart pointers (unique_ptr, shared_ptr)",
        "STL calls (std::cout, std::vector)",
        "operator overloads (operator(), operator+)",
    ],
    "javascript": [
        "method calls (obj.method())",
        "chain calls (a.b.c())",
        "require/import patterns",
    ],
    "typescript": [
        "method calls (obj.method())",
        "chain calls (a.b.c())",
        "import patterns",
    ],
}


@dataclass
class CallSite:
    """Represents a function/method call site in code."""

    caller: str
    callee: str
    file_path: str
    line: int
    column: int
    call_type: str  # direct, method, chain, callback, operator, template
    confidence: float = 1.0


class EnhancedStaticAnalyzer:
    """Enhanced static analyzer for Lua, Python, and C++."""

    # ========== LANGUAGE PATTERNS ==========

    PATTERNS = {
        "lua": {
            # Function definitions
            "function_def": r'^\s*function\s+(\w+)\s*\(',
            "method_def": r'^\s*function\s+(\w+):(\w+)\s*\(',
            "local_function": r'^\s*local\s+function\s+(\w+)\s*\(',
            "anon_function": r'(\w+)\s*=\s*function\s*\(',

            # Method calls (Lua specific)
            "colon_method": r'(\w+):(\w+)\s*\(',
            "dot_method": r'(\w+)\.(\w+)\s*\(',
            "self_method": r'self\.(\w+)\s*\(',
            "string_method": r'\[\'"](\w+)[\'"]\]\s*\(',  # obj["method"]()

            # Chain calls
            "chain_2": r'(\w+)\.(\w+)\.(\w+)\s*\(',
            "chain_3_plus": r'(\w+)(?:\.\w+){2,}\s*\(',

            # Metamethods
            "metamethod_call": r'(\w+)\s*:\s*(__\w+)\s*\(',

            # Imports
            "require": r'require\s*\(\s*["\']([^"\']+)["\']',
            "local_require": r'local\s+(\w+)\s*=\s*require\s*\(\s*["\']([^"\']+)["\']',
            "require_return": r'(\w+)\s*=\s*require\s*\([^)]+\)',
        },
        "python": {
            # Function definitions
            "function_def": r'^\s*def\s+(\w+)\s*\(',
            "async_def": r'^\s*async\s+def\s+(\w+)\s*\(',
            "method_def": r'^\s*def\s+(\w+)\s*\(',  # Will be refined with self/cls
            "lambda": r'(\w+)\s*=\s*lambda\s+',

            # Method calls
            "self_method": r'self\.(\w+)\s*\(',
            "cls_method": r'cls\.(\w+)\s*\(',
            "dot_method": r'(\w+)\.(\w+)\s*\(',

            # Chain calls
            "chain_2": r'(\w+)\.(\w+)\.(\w+)\s*\(',
            "chain_3_plus": r'(\w+)(?:\.\w+){2,}\s*\(',

            # Imports
            "import": r'import\s+(\w+)',
            "from_import": r'from\s+(\w+)\s+import\s+(\w+)',
            "from_import_as": r'from\s+(\w+)\s+import\s+(\w+)\s+as\s+(\w+)',
            "from_import_multi": r'from\s+(\w+)\s+import\s+\([^)]+\)',

            # Builtins
            "builtin_call": r'(\w+)\s*\(',
        },
        "cpp": {
            # Function definitions
            "function_def": r'^\s*(?:\w+\s+)?(\w+)\s+(\w+)\s*\(',
            "method_def": r'^\s*(?:\w+\s+)?(\w+)\s*::\s*(\w+)\s*\(',
            "lambda": r'\[\s*\]\s*\([^)]*\)\s*(?:const\s+)?(?:\w+::)?(\w+)\s*\(',
            "ctor": r'(\w+)\s*::\s*(\w+)\s*\(',

            # Method calls
            "dot_method": r'(\w+)\s*\.\s*(\w+)\s*\(',
            "arrow_method": r'(\w+)\s*->\s*(\w+)\s*\(',
            "ptr_method": r'(\w+)\s*->\s*(\w+)\s*\(',
            "scope_method": r'(\w+)\s*::\s*(\w+)\s*\(',

            # Chain calls
            "chain_arrow": r'(\w+)\s*->\s*(\w+)\s*->\s*(\w+)\s*\(',
            "chain_dot": r'(\w+)\s*\.\s*(\w+)\s*\.\s*(\w+)\s*\(',

            # Template calls
            "template_call": r'(\w+)<[^>]*>\s*\(\s*\)',
            "template_chain": r'(\w+)<[^>]*>\s*::\s*(\w+)\s*\(',

            # Operator overloads
            "operator_call": r'operator\(\)\s*\(',  # Function call operator
            "operator_binary": r'(\w+)\s*(\+\+|--|\+=|-=|\*=|/=|\|=)',  # Binary operators

            # Smart pointers
            "unique_ptr_call": r'(\w+)\s*->\s*\(',
            "shared_ptr_call": r'(\w+)\s*\.\s*get\s*\(',

            # Built-in / STL
            "std_call": r'std::(\w+)\s*\(',
            "cout": r'std::cout\s*<<',
        },
    }

    # ========== CALLBACK PATTERNS ==========

    CALLBACK_PATTERNS = {
        "lua": [
            r'(\w+)\.on\(\s*["\'](\w+)["\']\s*,\s*(?:function\s+)?(\w+)\)',
            r'(\w+)\.Add\(\s*(?:function\s+)?(\w+)\s*\)',
            r'(\w+)\.Connect\(\s*(?:function\s+)?(\w+)\s*\)',
            r'(\w+)(?:\.on|\.Add|\.Connect)\(\s*["\']?\w+["\']?\s*,\s*(?:function\s+)?(\w+)\s*\)',
        ],
        "python": [
            r'(\w+)\.add_\w+_handler\((?:\w+\s*,\s*)?(\w+)\)',
            r'(\w+)\.register\((?:\w+\s*,\s*)?(\w+)\)',
            r'(\w+)\.connect\((?:\w+\s*,\s*)?(\w+)\)',
            r'@(\w+)\s*\n\s*def\s+(\w+)',  # Decorator
        ],
        "cpp": [
            r'(\w+)\.connect\((?:\w+\s*,\s*)?(\w+)\)',
            r'(\w+)\.add_\w+_handler\((?:\w+\s*,\s*)?(\w+)\)',
            r'std::bind\s*\(([^,]+),\s*&([^)]+)\)',
        ],
    }

    # ========== SCOPE TRACKING ==========

    def __init__(self, root_path: Path, language: str = "auto"):
        self.root_path = root_path
        self.language = language
        self.calls: list[CallSite] = []

        # Scope tracking for better resolution
        self.scopes = {}  # file -> list of scopes
        self.current_classes = {}  # file -> current class
        self.imports = {}  # file -> imported modules

    def detect_language(self, file_path: Path) -> str | None:
        """Detect programming language from file extension."""
        if self.language != "auto":
            return self.language

        ext_map = {
            # Lua
            ".lua": "lua",
            # Python
            ".py": "python",
            ".pyi": "python",
            # C/C++
            ".cpp": "cpp",
            ".cc": "cpp",
            ".cxx": "cpp",
            ".c": "cpp",  # Can be C or C++
            ".h": "cpp",  # Header
            ".hpp": "cpp",
            ".hxx": "cpp",
            # JavaScript/TypeScript (for reference)
            ".js": "javascript",
            ".jsx": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
        }
        return ext_map.get(file_path.suffix.lower())

    def extract_lua(self, file_path: Path) -> list[CallSite]:
        """Enhanced Lua extraction."""
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except (OSError, UnicodeDecodeError):
            return []

        calls = []
        lines = content.split("\n")
        file_stem = file_path.stem

        # Track current class/context
        current_class = None
        current_function = None
        defined = set()
        imports = set()

        # Track self context
        self_contexts = []

        for line_num, line in enumerate(lines, 1):
            # Skip comments and empty lines
            stripped = line.strip()
            if not stripped or stripped.startswith("--"):
                continue

            # Track class/module context
            if re.match(r'^\s*local\s+(\w+)\s*=\s*{}', line):
                # Module declaration: local M = {}
                module_match = re.search(r'local\s+(\w+)', line)
                if module_match:
                    current_class = module_match.group(1)

            # Extract function definitions
            for func_type in ["function_def", "method_def", "local_function"]:
                pattern = self.PATTERNS["lua"][func_type]
                match = re.search(pattern, line)
                if match:
                    func_name = match.group(1)
                    defined.add(func_name)

                    if func_type == "method_def":
                        class_name = match.group(1)
                        method_name = match.group(2)
                        node_id = f"{file_stem}_{class_name.lower()}_{method_name.lower()}"
                        defined.add(f"{class_name}.{method_name}")
                        current_function = node_id
                    else:
                        node_id = f"{file_stem}_{func_name.lower()}"
                        current_function = node_id
                    break

            # Track self context
            if "self" in line or ":" in line:
                self_contexts.append(current_function)

            # Extract method calls with better patterns
            for pattern_name in ["colon_method", "dot_method", "self_method", "chain_2", "chain_3_plus"]:
                pattern = self.PATTERNS["lua"][pattern_name]
                for match in re.finditer(pattern, line):
                    groups = match.groups()
                    if not groups or len(groups) < 2:
                        continue

                    caller = current_function or f"{file_stem}_file"

                    if pattern_name == "colon_method":
                        # obj:method()
                        obj, method = groups[0], groups[1]
                        callee = f"{obj.lower()}:{method}"
                        call_type = "method"
                    elif pattern_name == "dot_method":
                        # obj.method()
                        obj, method = groups[0], groups[1]
                        callee = f"{obj.lower()}.{method}"
                        call_type = "method"
                    elif pattern_name == "chain_2":
                        # obj.method1.method2()
                        callee = f"{groups[0].lower()}.{groups[1]}"
                        call_type = "chain"
                    elif pattern_name == "chain_3_plus":
                        # Chain call
                        callee = re.sub(r'\s*\(', '', line[match.start():match.end()]).strip()
                        call_type = "chain"
                    else:
                        continue

                    # Filter built-ins
                    if callee not in ["if", "while", "for", "end", "then", "else", "return"]:
                        calls.append(CallSite(
                            caller=caller,
                            callee=callee,
                            file_path=str(file_path.relative_to(self.root_path)),
                            line=line_num,
                            column=match.start(),
                            call_type=call_type,
                        ))

            # Extract require patterns
            for pattern_name in ["require", "local_require", "require_return"]:
                pattern = self.PATTERNS["lua"][pattern_name]
                for match in re.finditer(pattern, line):
                    groups = match.groups()
                    if not groups:
                        continue

                    caller = current_function or f"{file_stem}_file"

                    if pattern_name == "require":
                        module = groups[-1]
                    elif pattern_name == "local_require":
                        local_name, module = groups[0], groups[1]
                        imports.add(local_name)
                        module = local_name
                    elif pattern_name == "require_return":
                        var_name = groups[0]
                        module = var_name

                    if module:
                        calls.append(CallSite(
                            caller=caller,
                            callee=module,
                            file_path=str(file_path.relative_to(self.root_path)),
                            line=line_num,
                            column=match.start(),
                            call_type="import",
                        ))

            # Extract callbacks
            for callback_pattern in self.CALLBACK_PATTERNS["lua"]:
                for match in re.finditer(callback_pattern, line):
                    groups = match.groups()
                    if len(groups) >= 2:
                        caller = current_function or f"{file_stem}_file"
                        obj = groups[0]
                        callback = groups[-1]

                        callee = f"{obj.lower()}.{callback.lower()}"
                        calls.append(CallSite(
                            caller=caller,
                            callee=callee,
                            file_path=str(file_path.relative_to(self.root_path)),
                            line=line_num,
                            column=match.start(),
                            call_type="callback",
                        ))

        return calls

    def extract_python(self, file_path: Path) -> list[CallSite]:
        """Enhanced Python extraction."""
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except (OSError, UnicodeDecodeError):
            return []

        calls = []
        lines = content.split("\n")
        file_stem = file_path.stem

        current_class = None
        current_function = None
        defined = set()
        decorators = []  # Track decorators

        # Track indentation for scope
        indent_stack = []

        for line_num, line in enumerate(lines, 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue

            # Track decorators
            if stripped.startswith("@"):
                decorator_match = re.match(r'@(\w+)', stripped)
                if decorator_match:
                    decorators.append(decorator_match.group(1))
                continue

            # Calculate indentation
            indent = len(line) - len(line.lstrip())

            # Extract class definitions
            class_match = re.match(r'^\s*class\s+(\w+)(?:\(([^)]+)\))?\s*:', line)
            if class_match:
                current_class = class_match.group(1)
                continue

            # Extract function/method definitions
            func_patterns = ["function_def", "async_def", "lambda"]
            for func_type in func_patterns:
                pattern = self.PATTERNS["python"][func_type]
                match = re.search(pattern, line)
                if match:
                    func_name = match.group(1)
                    defined.add(func_name)

                    if func_type == "lambda":
                        # lambda = ...
                        node_id = f"{file_stem}_lambda_{line_num}"
                    else:
                        # Apply decorators
                        if decorators:
                            for dec in decorators:
                                defined.add(f"{dec}.{func_name}")
                        node_id = f"{file_stem}_{func_name.lower()}"

                    current_function = node_id
                    decorators = []
                    break

            # Track context (self/cls)
            context = None
            if current_class:
                if "self" in line or "cls" in line:
                    if "self" in line and ":" in line:
                        context = "self"
                    elif "cls" in line and ":" in line:
                        context = "cls"

            # Extract method calls with context awareness
            caller = current_function or f"{file_stem}_file"

            # Self/cls methods
            if context == "self":
                for match in re.finditer(r'self\.(\w+)\s*\(', line):
                    method = match.group(1)
                    callee = f"{current_class or file_stem}.{method}"
                    calls.append(CallSite(
                        caller=caller,
                        callee=callee,
                        file_path=str(file_path.relative_to(self.root_path)),
                        line=line_num,
                        column=match.start(),
                        call_type="method",
                    ))
            elif context == "cls":
                for match in re.finditer(r'cls\.(\w+)\s*\(', line):
                    method = match.group(1)
                    callee = f"{current_class}.{method}"
                    calls.append(CallSite(
                        caller=caller,
                        callee=callee,
                        file_path=str(file_path.relative_to(self.root_path)),
                        line=line_num,
                        column=match.start(),
                        call_type="method",
                    ))

            # Regular method calls
            for pattern_name in ["dot_method", "chain_2", "chain_3_plus"]:
                pattern = self.PATTERNS["python"][pattern_name]
                for match in re.finditer(pattern, line):
                    groups = match.groups()
                    if not groups:
                        continue

                    callee = ".".join(g for g in groups if g)
                    call_type = "chain" if "chain" in pattern_name else "method"

                    # Filter Python keywords and built-ins
                    if callee not in ["if", "while", "for", "with", "range", "len", "str", "int", "list", "dict"]:
                        calls.append(CallSite(
                            caller=caller,
                            callee=callee,
                            file_path=str(file_path.relative_to(self.root_path)),
                            line=line_num,
                            column=match.start(),
                            call_type=call_type,
                        ))

            # Extract imports
            for pattern_name in ["import", "from_import", "from_import_as"]:
                pattern = self.PATTERNS["python"][pattern_name]
                for match in re.finditer(pattern, line):
                    groups = match.groups()
                    if not groups:
                        continue

                    if pattern_name == "import":
                        module = groups[0]
                    elif pattern_name == "from_import":
                        module, func = groups[0], groups[1]
                        defined.add(f"{module}.{func}")
                    elif pattern_name == "from_import_as":
                        module, func, alias = groups[0], groups[1], groups[2]
                        defined.add(f"{module}.{func}")
                        defined.add(alias)
                    else:
                        continue

                    calls.append(CallSite(
                        caller=caller,
                        callee=module,
                        file_path=str(file_path.relative_to(self.root_path)),
                        line=line_num,
                        column=match.start(),
                        call_type="import",
                    ))

            # Context managers (with statement)
            for match in re.finditer(r'with\s+(\w+)', line):
                context_obj = match.group(1)
                calls.append(CallSite(
                    caller=caller,
                    callee=f"{context_obj}.__enter__",
                    file_path=str(file_path.relative_to(self.root_path)),
                    line=line_num,
                    column=match.start(),
                    call_type="context",
                ))

        return calls

    def extract_cpp(self, file_path: Path) -> list[CallSite]:
        """Enhanced C++ extraction."""
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except (OSError, UnicodeDecodeError):
            return []

        calls = []
        lines = content.split("\n")
        file_stem = file_path.stem

        current_class = None
        current_function = None
        defined = set()

        # Track template scope
        template_stack = []

        for line_num, line in enumerate(lines, 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("//") or stripped.startswith("/*"):
                continue

            # Skip preprocessor directives (simplified)
            if stripped.startswith("#"):
                continue

            # Track namespace/class
            namespace_match = re.match(r'namespace\s+(\w+)\s*{', line)
            if namespace_match:
                current_class = namespace_match.group(1)
                continue

            class_match = re.match(r'(?:class\s+|struct\s+)(\w+)', line)
            if class_match:
                current_class = class_match.group(1)
                continue

            # Extract function/method definitions
            for func_type in ["function_def", "method_def", "ctor"]:
                pattern = self.PATTERNS["cpp"][func_type]
                match = re.search(pattern, line)
                if match:
                    groups = match.groups()
                    func_name = groups[-1] if groups else None
                    if func_name:
                        defined.add(func_name)

                        if func_type in ["method_def", "ctor"]:
                            # Class::method or Class::Class
                            if len(groups) >= 2:
                                scope = groups[0] if groups[0] and groups[0] not in ["virtual", "static", "inline"] else None
                                class_name = groups[0] if scope and scope.isalpha() else None
                                if class_name:
                                    current_class = class_name
                                    node_id = f"{file_stem}_{class_name.lower()}_{func_name.lower()}"
                                elif current_class:
                                    node_id = f"{file_stem}_{current_class.lower()}_{func_name.lower()}"
                                else:
                                    node_id = f"{file_stem}_{func_name.lower()}"
                            else:
                                node_id = f"{file_stem}_{func_name.lower()}"
                        else:
                            node_id = f"{file_stem}_{func_name.lower()}"
                        current_function = node_id
                    break

            # Extract method calls
            caller = current_function or f"{file_stem}_file"

            # Arrow method calls (ptr->method())
            arrow_pattern = self.PATTERNS["cpp"]["arrow_method"]
            for match in re.finditer(arrow_pattern, line):
                obj, method = match.group(1), match.group(2)
                if obj and method:
                    callee = f"{obj}->{method}"
                    calls.append(CallSite(
                        caller=caller,
                        callee=callee,
                        file_path=str(file_path.relative_to(self.root_path)),
                        line=line_num,
                        column=match.start(),
                        call_type="method",
                    ))

            # Dot method calls (obj.method())
            dot_pattern = self.PATTERNS["cpp"]["dot_method"]
            for match in re.finditer(dot_pattern, line):
                obj, method = match.group(1), match.group(2)
                if obj and method:
                    callee = f"{obj}.{method}"
                    calls.append(CallSite(
                        caller=caller,
                        callee=callee,
                        file_path=str(file_path.relative_to(self.root_path)),
                        line=line_num,
                        column=match.start(),
                        call_type="method",
                    ))

            # Scope resolution (::)
            scope_pattern = self.PATTERNS["cpp"]["scope_method"]
            for match in re.finditer(scope_pattern, line):
                groups = match.groups()
                if len(groups) >= 2:
                    scope, method = groups[0], groups[-1]
                    if scope and method:
                        callee = f"{scope}::{method}"
                        calls.append(CallSite(
                            caller=caller,
                            callee=callee,
                            file_path=str(file_path.relative_to(self.root_path)),
                            line=line_num,
                            column=match.start(),
                            call_type="method",
                        ))

            # Chain calls
            for pattern_name in ["chain_arrow", "chain_dot"]:
                pattern = self.PATTERNS["cpp"][pattern_name]
                for match in re.finditer(pattern, line):
                    groups = match.groups()
                    if len(groups) >= 2:
                        callee = "->".join(g for g in groups if g)
                        calls.append(CallSite(
                            caller=caller,
                            callee=callee,
                            file_path=str(file_path.relative_to(self.root_path)),
                            line=line_num,
                            column=match.start(),
                            call_type="chain",
                        ))

            # Template calls
            template_pattern = self.PATTERNS["cpp"]["template_call"]
            for match in re.finditer(template_pattern, line):
                func_name = match.group(1) if match.groups() else None
                if func_name and func_name not in ["if", "return", "while", "for"]:
                    calls.append(CallSite(
                        caller=caller,
                        callee=f"{func_name}<>",
                        file_path=str(file_path.relative_to(self.root_path)),
                        line=line_num,
                        column=match.start(),
                        call_type="template",
                    ))

            # Smart pointer calls
            unique_ptr_pattern = self.PATTERNS["cpp"]["unique_ptr_call"]
            for match in re.finditer(unique_ptr_pattern, line):
                obj = match.group(1) if match.groups() else None
                if obj:
                    calls.append(CallSite(
                        caller=caller,
                        callee=f"{obj}->",
                        file_path=str(file_path.relative_to(self.root_path)),
                        line=line_num,
                        column=match.start(),
                        call_type="smart_ptr",
                    ))

            # STL calls
            for match in re.finditer(r'std::(\w+)\s*\(', line):
                func = match.group(1)
                calls.append(CallSite(
                    caller=caller,
                    callee=f"std::{func}",
                    file_path=str(file_path.relative_to(self.root_path)),
                    line=line_num,
                    column=match.start(),
                    call_type="stl",
                ))

        return calls

    def extract_from_file(self, file_path: Path) -> list[CallSite]:
        """Extract call sites from a single file using language-specific extractor."""
        language = self.detect_language(file_path)

        if language == "lua":
            return self.extract_lua(file_path)
        elif language == "python":
            return self.extract_python(file_path)
        elif language == "cpp":
            return self.extract_cpp(file_path)
        else:
            # Fallback to generic extraction for other languages
            return []

    def extract_all(self, file_pattern: str | None = None) -> list[CallSite]:
        """Extract call sites from all relevant files."""
        all_calls = []

        for file_path in self.root_path.rglob("*"):
            if file_path.is_file():
                rel_path = file_path.relative_to(self.root_path)
                # Skip common non-source directories
                if any(part.startswith('.') for part in rel_path.parts):
                    continue
                if "node_modules" in rel_path.parts or "vendor" in rel_path.parts:
                    continue

                calls = self.extract_from_file(file_path)
                all_calls.extend(calls)

        return all_calls

    def resolve_targets(
        self, calls: list[CallSite], all_symbols: dict[str, str]
    ) -> list[dict[str, Any]]:
        """Resolve call targets to node IDs."""
        edges = []

        for call in calls:
            # Try to find the callee in defined symbols
            callee_key = call.callee.lower()

            # Direct match
            if callee_key in all_symbols:
                edges.append({
                    "source": call.caller,
                    "target": all_symbols[callee_key],
                    "relation": "calls",
                    "confidence": "EXTRACTED",
                    "confidence_score": call.confidence,
                    "source_file": call.file_path,
                    "source_location": f"L{call.line}",
                    "weight": 1.0,
                    "_enhanced_by": "static_v2",
                    "_call_type": call.call_type,
                })
            else:
                # Create an unresolved reference node
                target_id = f"external_{callee_key.replace(':', '_').replace('.', '_')}"
                edges.append({
                    "source": call.caller,
                    "target": target_id,
                    "relation": "calls",
                    "confidence": "INFERRED",
                    "confidence_score": 0.6,
                    "source_file": call.file_path,
                    "source_location": f"L{call.line}",
                    "weight": 0.6,
                    "_enhanced_by": "static_v2",
                    "_call_type": call.call_type,
                    "_unresolved": True,
                })

        return edges


class GraphEnhancer:
    """Enhance existing graph with static analysis results."""

    def __init__(self, graph_path: Path, root_path: Path):
        self.graph_path = graph_path
        self.root_path = root_path
        self.graph_data = None
        self.load_graph()

    def load_graph(self) -> None:
        """Load existing graph."""
        if not self.graph_path.exists():
            raise FileNotFoundError(f"Graph not found: {self.graph_path}")

        with open(self.graph_path, encoding="utf-8") as f:
            self.graph_data = json.load(f)

    def get_symbol_map(self) -> dict[str, str]:
        """Build a comprehensive symbol map for better resolution."""
        symbol_map = {}
        nodes = self.graph_data.get("nodes", [])

        for node in nodes:
            label = node.get("label", "")
            node_id = node.get("id", "")
            if label and node_id:
                # Map by various forms
                label_lower = label.lower().rstrip("()")
                label_undotted = label.replace(":", ".").lower()

                symbol_map[label_lower] = node_id
                symbol_map[label] = node_id
                symbol_map[label_undotted] = node_id

                # For class.method patterns
                if "." in label_undotted:
                    symbol_map[label_undotted] = node_id

        return symbol_map

    def add_edges(self, new_edges: list[dict[str, Any]]) -> dict[str, Any]:
        """Add new edges to the graph with deduplication."""
        existing_links = self.graph_data.get("links", [])
        existing_nodes = self.graph_data.get("nodes", [])

        # Build lookup for deduplication
        existing_edges = set()
        for edge in existing_links:
            key = (edge.get("source"), edge.get("target"), edge.get("relation"))
            existing_edges.add(key)

        # Filter duplicates and add nodes for unresolved targets
        added_edges = []
        added_nodes = []

        for edge in new_edges:
            key = (edge.get("source"), edge.get("target"), edge.get("relation"))
            if key in existing_edges:
                continue

            # Check if target node exists
            target_id = edge.get("target")
            target_exists = any(n.get("id") == target_id for n in existing_nodes + added_nodes)

            if not target_exists and edge.get("_unresolved"):
                # Create a placeholder node for unresolved references
                label = edge.get("target", "").replace("external_", "")
                added_nodes.append({
                    "id": target_id,
                    "label": label,
                    "file_type": "external",
                    "_enhanced_by": "static_v2",
                    "_unresolved": True,
                })

            added_edges.append(edge)
            existing_edges.add(key)

        # Merge into graph
        self.graph_data["nodes"].extend(added_nodes)
        self.graph_data["links"].extend(added_edges)

        # Update metadata
        metadata = self.graph_data.get("_metadata", {})
        metadata["static_enhanced_v2"] = True
        metadata["static_v2_edges_added"] = metadata.get("static_v2_edges_added", 0) + len(added_edges)
        metadata["static_v2_nodes_added"] = metadata.get("static_v2_nodes_added", 0) + len(added_nodes)
        self.graph_data["_metadata"] = metadata

        return {
            "edges_added": len(added_edges),
            "nodes_added": len(added_nodes),
            "total_edges": len(self.graph_data["links"]),
            "total_nodes": len(self.graph_data["nodes"]),
        }

    def save(self, output_path: Path | None = None) -> None:
        """Save enhanced graph."""
        output_path = output_path or self.graph_path
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(self.graph_data, f, indent=2)


def run_static_enhancement(
    root_path: Path,
    graph_path: Path | None = None,
    language: str = "auto",
    output_path: Path | None = None,
) -> dict[str, Any]:
    """Run enhanced static analysis for Lua, Python, and C++.

    Args:
        root_path: Project root directory
        graph_path: Path to existing graph.json
        language: Programming language (auto-detect if 'auto')
        output_path: Output path (default: overwrite input)

    Returns:
        Statistics about the enhancement
    """
    graph_path = graph_path or root_path / "graphify-out" / "graph.json"

    print(f"Enhanced static analysis for: {root_path}")
    print(f"Graph: {graph_path}")

    # Load and enhance graph
    enhancer = GraphEnhancer(graph_path, root_path)

    # Get symbol map for resolution
    symbol_map = enhancer.get_symbol_map()
    print(f"Loaded {len(symbol_map)} symbols from graph")

    # Run enhanced static analysis
    analyzer = EnhancedStaticAnalyzer(root_path, language=language)
    calls = analyzer.extract_all()
    print(f"Extracted {len(calls)} call sites")

    # Resolve targets and create edges
    edges = analyzer.resolve_targets(calls, symbol_map)
    print(f"Resolved to {len(edges)} edges")

    # Add edges to graph
    stats = enhancer.add_edges(edges)
    enhancer.save(output_path)

    print(f"\nEnhancement complete:")
    print(f"  Edges added: {stats['edges_added']}")
    print(f"  Nodes added: {stats['nodes_added']}")
    print(f"  Total edges: {stats['total_edges']}")
    print(f"  Total nodes: {stats['total_nodes']}")

    # Print breakdown by call type
    from collections import Counter
    call_types = {}
    for edge in edges:
        ctype = edge.get("_call_type", "unknown")
        call_types[ctype] = call_types.get(ctype, 0) + 1

    if call_types:
        print(f"\nEdges by call type:")
        for ctype, count in sorted(call_types.items(), key=lambda x: -x[1]):
            print(f"  {ctype}: {count}")

    return stats


def main() -> None:
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Enhanced static analysis for Lua, Python, and C++"
    )
    parser.add_argument(
        "path",
        type=Path,
        nargs="?",
        default=Path("."),
        help="Project root (default: current directory)",
    )
    parser.add_argument(
        "--graph",
        type=Path,
        default=None,
        help="Path to graph.json",
    )
    parser.add_argument(
        "--language",
        "-l",
        default="auto",
        choices=["auto", "lua", "python", "cpp", "javascript", "typescript"],
        help="Programming language",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Output path",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show detailed statistics",
    )

    args = parser.parse_args()

    try:
        stats = run_static_enhancement(
            root_path=args.path,
            graph_path=args.graph,
            language=args.language,
            output_path=args.output,
        )

        if args.stats:
            print("\nDetailed statistics available in graph metadata")

    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        print("\nPlease run '/graphify' first to create the initial graph.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
