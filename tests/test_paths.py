"""Unit tests for code/utils/paths.py."""

from pathlib import Path
import pytest

from utils.paths import (
    get_csv_path,
    get_dataset_dir,
    get_image_path,
    get_images_dir,
    get_repo_root,
)


def test_repo_root_resolution():
    root = get_repo_root()
    assert root.is_dir()
    assert (root / "AGENTS.md").is_file() or (root / "dataset").is_dir()


def test_dataset_dir_resolution():
    root = get_repo_root()
    dataset_dir = get_dataset_dir(root)
    assert dataset_dir.is_dir()
    assert dataset_dir == root / "dataset"


def test_images_dir_resolution():
    root = get_repo_root()
    images_dir = get_images_dir(root)
    assert images_dir.is_dir()
    assert images_dir == root / "dataset" / "media" / "images"


def test_image_path_resolution():
    root = get_repo_root()
    path_without_ext = get_image_path("image_01", repo_root=root)
    assert path_without_ext.name == "image_01.png"
    assert path_without_ext.is_file()

    path_with_ext = get_image_path("image_02.png", repo_root=root)
    assert path_with_ext.name == "image_02.png"
    assert path_with_ext.is_file()


def test_csv_path_resolution():
    root = get_repo_root()
    csv_path = get_csv_path("requests.csv", repo_root=root)
    assert csv_path.name == "requests.csv"
    assert csv_path.is_file()
