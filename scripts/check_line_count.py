"""檢查 Python 原始碼檔案行數。

掃描 app/ 與 tests/ 目錄下所有 .py 檔案，計算有效行數
（排除空白行與純註解行）。超過 800 行產生警告，超過 1000 行產生錯誤。

Usage:
    python scripts/check_line_count.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# 行數門檻設定
WARN_THRESHOLD = 800
ERROR_THRESHOLD = 1000

# 掃描目標目錄（相對於專案根目錄）
TARGET_DIRS = ["app", "tests"]


def count_effective_lines(filepath: Path) -> int:
    """計算檔案的有效行數（排除空白行與純註解行）。

    Args:
        filepath: Python 原始碼檔案路徑。

    Returns:
        有效行數。
    """
    count = 0
    try:
        with open(filepath, encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                # 跳過空白行
                if not stripped:
                    continue
                # 跳過純註解行
                if stripped.startswith("#"):
                    continue
                count += 1
    except (OSError, UnicodeDecodeError) as e:
        print(f"  [WARN] 無法讀取 {filepath}: {e}")
    return count


def find_python_files(project_root: Path) -> list[Path]:
    """遞迴搜尋目標目錄下所有 .py 檔案。

    Args:
        project_root: 專案根目錄。

    Returns:
        Python 原始碼檔案路徑清單。
    """
    files: list[Path] = []
    for target_dir in TARGET_DIRS:
        dir_path = project_root / target_dir
        if not dir_path.exists():
            continue
        for py_file in sorted(dir_path.rglob("*.py")):
            # 排除 __pycache__ 與隱藏目錄
            parts = py_file.relative_to(project_root).parts
            if any(part.startswith(".") or part == "__pycache__" for part in parts):
                continue
            files.append(py_file)
    return files


def main() -> int:
    """主程式：掃描並報告檔案行數。

    Returns:
        退出碼。0 表示通過，1 表示有超過 1000 行的檔案。
    """
    # 以本腳本所在位置往上推算專案根目錄
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent

    py_files = find_python_files(project_root)

    if not py_files:
        print("未找到任何 Python 檔案。")
        return 0

    warnings: list[tuple[Path, int]] = []
    errors: list[tuple[Path, int]] = []

    print(f"掃描目標: {', '.join(TARGET_DIRS)}")
    print(f"門檻: 警告 >= {WARN_THRESHOLD} 行, 錯誤 >= {ERROR_THRESHOLD} 行")
    print("-" * 70)

    for filepath in py_files:
        line_count = count_effective_lines(filepath)
        rel_path = filepath.relative_to(project_root)

        if line_count >= ERROR_THRESHOLD:
            errors.append((rel_path, line_count))
            print(f"  [ERROR] {rel_path}: {line_count} 行")
        elif line_count >= WARN_THRESHOLD:
            warnings.append((rel_path, line_count))
            print(f"  [WARN]  {rel_path}: {line_count} 行")

    print("-" * 70)
    print(f"掃描完成: {len(py_files)} 個檔案")
    print(f"  警告: {len(warnings)} 個檔案 (>= {WARN_THRESHOLD} 行)")
    print(f"  錯誤: {len(errors)} 個檔案 (>= {ERROR_THRESHOLD} 行)")

    if errors:
        print("\n[FAIL] 以下檔案超過 1000 行硬限制，必須拆分:")
        for rel_path, count in errors:
            print(f"  - {rel_path} ({count} 行)")
        return 1

    if warnings:
        print("\n[WARN] 以下檔案接近行數限制，建議重構:")
        for rel_path, count in warnings:
            print(f"  - {rel_path} ({count} 行)")

    print("\n[OK] 行數檢查通過。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
