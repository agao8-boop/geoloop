import importlib
import pathlib
import pytest

PACKAGES = [
    "geosite",
    "geosite.s1_site",
    "geosite.s2_simulation",
    "geosite.s3_loads",
    "geosite.s4_sizing",
    "geosite.s5_cost",
    "geosite.s6_strategy",
    "geosite.s7_report",
]

DATA_DIRS = [
    "data/idf_prototypes",
    "data/weather",
    "data/soil_cache",
    "outputs",
    "notebooks",
]

ROOT = pathlib.Path(__file__).parent.parent


@pytest.mark.parametrize("module", PACKAGES)
def test_package_importable(module):
    importlib.import_module(module)


@pytest.mark.parametrize("rel", DATA_DIRS)
def test_directory_exists(rel):
    assert (ROOT / rel).is_dir()
