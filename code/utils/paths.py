"""Path resolution utilities for BUYorNOT repository."""

from pathlib import Path


def get_repo_root() -> Path:
    """Resolve the repository root directory robustly.
    
    Walks up from the current file location until a known repository marker
    (e.g., AGENTS.md or dataset directory) is found. Falls back to three levels
    up from this file.
    """
    current = Path(__file__).resolve().parent
    for parent in [current] + list(current.parents):
        if (parent / "AGENTS.md").exists() or (parent / "dataset").is_dir():
            return parent
    # Fallback to repo root assuming code/utils/paths.py
    return Path(__file__).resolve().parent.parent.parent


def get_dataset_dir(repo_root: Path | None = None) -> Path:
    """Get the absolute path to the dataset directory."""
    root = repo_root or get_repo_root()
    return root / "dataset"


def get_images_dir(repo_root: Path | None = None) -> Path:
    """Get the absolute path to the dataset/media/images directory."""
    return get_dataset_dir(repo_root) / "media" / "images"


def get_image_path(image_id: str, repo_root: Path | None = None) -> Path:
    """Resolve the physical file path for a given image identifier.
    
    Example: 'image_01' -> '<repo_root>/dataset/media/images/image_01.png'
    """
    images_dir = get_images_dir(repo_root)
    # Handle if extension is already supplied or not
    filename = image_id if image_id.endswith(".png") else f"{image_id}.png"
    return images_dir / filename


def get_csv_path(filename: str, repo_root: Path | None = None) -> Path:
    """Get the path to a specific CSV file in the dataset directory."""
    return get_dataset_dir(repo_root) / filename
