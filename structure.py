import os

# Set target directory (your project root) and output path
PROJECT_ROOT = r"C:\Users\pranav\OneDrive - EMMVEE Photovoltaic Power Limited\Desktop\Py Projects\TaskHub"
OUTPUT_FILE = r"C:\Users\pranav\OneDrive - EMMVEE Photovoltaic Power Limited\Desktop\Py Projects\TaskHub\file_structure.txt"

# Folders and files to exclude from the visual tree
EXCLUDE_DIRS = {".git", ".venv", "node_modules", ".pytest_cache", "__pycache__", ".idea", ".vscode"}
EXCLUDE_FILES = {".DS_Store", "desktop.ini"}

def build_tree(dir_path: str, prefix: str = "") -> list[str]:
    lines = []
    
    # Get sorted list of all valid items in directory
    try:
        entries = sorted([
            e for e in os.listdir(dir_path) 
            if e not in EXCLUDE_DIRS and e not in EXCLUDE_FILES
        ])
    except PermissionError:
        return lines

    # Separate directories and files so directories appear first
    dirs = [e for e in entries if os.path.isdir(os.path.join(dir_path, e))]
    files = [e for e in entries if os.path.isfile(os.path.join(dir_path, e))]
    sorted_entries = dirs + files

    total = len(sorted_entries)
    for index, entry in enumerate(sorted_entries):
        full_path = os.path.join(dir_path, entry)
        is_last = (index == total - 1)
        
        # Determine tree branch graphics
        connector = "└── " if is_last else "├── "
        icon = "📁 " if os.path.isdir(full_path) else "📄 "
        
        lines.append(f"{prefix}{connector}{icon}{entry}")
        
        # Recurse if entry is a directory
        if os.path.isdir(full_path):
            extension = "    " if is_last else "│   "
            lines.extend(build_tree(full_path, prefix + extension))
            
    return lines

def generate_structure_file():
    root_name = os.path.basename(os.path.normpath(PROJECT_ROOT))
    tree_lines = [f"📁 {root_name}"] + build_tree(PROJECT_ROOT)
    
    # Write cleanly formatted output to the destination file
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(tree_lines))
        
    print(f"Successfully generated accurate file structure at:\n{OUTPUT_FILE}")

if __name__ == "__main__":
    generate_structure_file()