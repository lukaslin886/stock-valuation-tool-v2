"""
pagination.slice_page 單元測試。
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "app"))

from pagination import slice_page  # noqa: E402


def test_basic_first_page():
    assert slice_page(1000, 1, 100) == (0, 100, 10, 1)


def test_middle_page():
    assert slice_page(1000, 3, 100) == (200, 300, 10, 3)


def test_last_partial_page():
    # 950 筆、每頁 100 → 10 頁，第 10 頁只有 50 筆
    start, end, n_pages, page = slice_page(950, 10, 100)
    assert (start, end, n_pages, page) == (900, 950, 10, 10)


def test_page_overflow_clamped():
    # 要求第 99 頁但只有 10 頁 → 夾回第 10 頁
    assert slice_page(1000, 99, 100) == (900, 1000, 10, 10)


def test_page_below_one_clamped():
    assert slice_page(1000, 0, 100) == (0, 100, 10, 1)
    assert slice_page(1000, -5, 100) == (0, 100, 10, 1)


def test_page_size_zero_means_all():
    assert slice_page(300, 1, 0) == (0, 300, 1, 1)


def test_empty_total():
    assert slice_page(0, 1, 100) == (0, 0, 1, 1)


def test_exact_multiple():
    assert slice_page(500, 5, 100) == (400, 500, 5, 5)


def test_less_than_one_page():
    assert slice_page(30, 1, 100) == (0, 30, 1, 1)
