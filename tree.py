"""
Print the directory tree starting from root.

Usage:
    python print_tree.py [root_path] [--all] [--max-depth N]
"""

import argparse
import os
import sys

DEFAULT_IGNORE = {
    "node_modules", ".git", "__pycache__", ".venv", "venv", "env",
    "dist", "build", ".next", ".turbo", ".pytest_cache", ".mypy_cache",
    ".idea", ".vscode", "coverage", ".cache", "*.egg-info",
    ".DS_Store", "site-packages",
}

def should_skip(name: str, ignore: set[str]) -> bool:
    if name in ignore:
        return True
    if name.endswith(".egg-info"):
        return True
    return False

def print_tree(root: str, ignore: set[str], max_depth: int | None, prefix: str = "", depth: int = 0):
    if max_depth is not None and depth > max_depth:
        return
    try:
        entries = sorted(
            os.listdir(root),
            key=lambda e: (not os.path.isdir(os.path.join(root, e)), e.lower()),
        )
    except PermissionError:
        print(prefix + "└── [permission denied]")
        return
    except FileNotFoundError:
        print(f"Path not found: {root}")
        return
    entries = [e for e in entries if not should_skip(e, ignore)]
    for i, entry in enumerate(entries):
        path = os.path.join(root, entry)
        is_last = i == len(entries) - 1
        connector = "└── " if is_last else "├── "
        is_dir = os.path.isdir(path)
        print(prefix + connector + entry + ("/" if is_dir else ""))
        if is_dir:
            extension = "    " if is_last else "│   "
            print_tree(path, ignore, max_depth, prefix + extension, depth + 1)

def main():
    parser = argparse.ArgumentParser(description="Print a directory tree.")
    parser.add_argument("root", nargs="?", default=".", help="Root directory (default: current dir)")
    parser.add_argument("--all", action="store_true", help="Don't skip common noise dirs (node_modules, .git, etc.)")
    parser.add_argument("--max-depth", type=int, default=None, help="Limit recursion depth")
    args = parser.parse_args()
    root = os.path.abspath(args.root)
    ignore = set() if args.all else DEFAULT_IGNORE
    print(root)
    print_tree(root, ignore, args.max_depth)

if __name__ == "__main__":
    main()