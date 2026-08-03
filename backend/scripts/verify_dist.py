"""Verify required files in built backend distributions."""

import tarfile
import zipfile
from pathlib import Path


def _contains_license(names: list[str]) -> bool:
    return any(Path(name).name == "LICENSE" for name in names)


dist = Path("dist")
wheel = next(dist.glob("*.whl"))
source = next(dist.glob("*.tar.gz"))
with zipfile.ZipFile(wheel) as wheel_archive:
    assert _contains_license(wheel_archive.namelist()), f"LICENSE missing from {wheel.name}"
with tarfile.open(source) as source_archive:
    assert _contains_license(source_archive.getnames()), f"LICENSE missing from {source.name}"
