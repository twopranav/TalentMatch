"""
Print a clean directory tree starting from root.

Designed for displaying project structure without repetitive/generated noise.

Usage:
    python print_tree.py [root_path]
    python print_tree.py [root_path] --all
    python print_tree.py [root_path] --max-depth N
"""

import argparse
import os


# Directories that usually contain generated, cached, or dependency files.
DEFAULT_IGNORE_DIRS = {
    "node_modules",
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    "dist",
    "build",
    ".next",
    ".turbo",
    ".pytest_cache",
    ".mypy_cache",
    ".idea",
    ".vscode",
    "coverage",
    ".cache",
    "site-packages",
    ".ruff_cache",
}


# Individual files that are generally not useful when viewing a project tree.
DEFAULT_IGNORE_FILES = {
    ".DS_Store",
    "Thumbs.db",
}


# Directories whose contents should be summarized instead of printed individually.
# The directory itself will still be shown.
COLLAPSE_DIRS = {
    "versions",
}


def should_skip_dir(name: str, ignore: set[str]) -> bool:
    """Return True if a directory should be completely hidden."""

    if name in ignore:
        return True

    # Python package metadata directories
    if name.endswith(".egg-info"):
        return True

    return False


def should_skip_file(name: str, ignore: set[str]) -> bool:
    """Return True if an individual file should be hidden."""

    if name in ignore:
        return True

    # Python bytecode
    if name.endswith(".pyc"):
        return True

    # Python compiled cache files
    if name.endswith(".pyo"):
        return True

    return False


def get_entries(
    root: str,
    ignore_dirs: set[str],
    ignore_files: set[str],
):
    """Return visible entries sorted with directories first."""

    try:
        entries = os.listdir(root)
    except PermissionError:
        return None
    except FileNotFoundError:
        return None

    visible = []

    for entry in entries:
        path = os.path.join(root, entry)

        if os.path.isdir(path):
            if not should_skip_dir(entry, ignore_dirs):
                visible.append(entry)
        else:
            if not should_skip_file(entry, ignore_files):
                visible.append(entry)

    # Directories first, then files, alphabetically.
    visible.sort(
        key=lambda entry: (
            not os.path.isdir(os.path.join(root, entry)),
            entry.lower(),
        )
    )

    return visible


def count_visible_files(
    root: str,
    ignore_dirs: set[str],
    ignore_files: set[str],
) -> int:
    """Count files inside a directory without recursively walking subdirectories."""

    try:
        entries = os.listdir(root)
    except (PermissionError, FileNotFoundError):
        return 0

    count = 0

    for entry in entries:
        path = os.path.join(root, entry)

        if os.path.isfile(path):
            if not should_skip_file(entry, ignore_files):
                count += 1

    return count


def print_tree(
    root: str,
    ignore_dirs: set[str],
    ignore_files: set[str],
    max_depth: int | None,
    prefix: str = "",
    depth: int = 0,
):
    """Recursively print the directory tree."""

    if max_depth is not None and depth > max_depth:
        return

    entries = get_entries(root, ignore_dirs, ignore_files)

    if entries is None:
        print(prefix + "└── [permission denied or path unavailable]")
        return

    for index, entry in enumerate(entries):
        path = os.path.join(root, entry)
        is_last = index == len(entries) - 1
        connector = "└── " if is_last else "├── "

        if os.path.isdir(path):
            print(prefix + connector + entry + "/")

            extension = "    " if is_last else "│   "
            child_prefix = prefix + extension

            # Collapse repetitive directories such as alembic/versions.
            if entry in COLLAPSE_DIRS:
                file_count = count_visible_files(
                    path,
                    ignore_dirs,
                    ignore_files,
                )

                if file_count:
                    print(
                        child_prefix
                        + "└── "
                        + f"[{file_count} files hidden]"
                    )
                else:
                    print(child_prefix + "└── [empty]")

                continue

            print_tree(
                path,
                ignore_dirs,
                ignore_files,
                max_depth,
                child_prefix,
                depth + 1,
            )

        else:
            print(prefix + connector + entry)


def main():
    parser = argparse.ArgumentParser(
        description="Print a clean project directory tree."
    )

    parser.add_argument(
        "root",
        nargs="?",
        default=".",
        help="Root directory (default: current directory)",
    )

    parser.add_argument(
        "--all",
        action="store_true",
        help="Show normally ignored generated/dependency directories and files.",
    )

    parser.add_argument(
        "--max-depth",
        type=int,
        default=None,
        help="Limit recursion depth.",
    )

    args = parser.parse_args()

    root = os.path.abspath(args.root)

    if not os.path.exists(root):
        print(f"Path not found: {root}")
        return

    if args.all:
        ignore_dirs = set()
        ignore_files = set()
    else:
        ignore_dirs = DEFAULT_IGNORE_DIRS
        ignore_files = DEFAULT_IGNORE_FILES

    print(root)
    print_tree(
        root,
        ignore_dirs,
        ignore_files,
        args.max_depth,
    )


if __name__ == "__main__":
    main()
