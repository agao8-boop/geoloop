"""Regression guard: static/main.js queries these ids; index.html must keep them."""

import pytest
from app import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


REQUIRED_IDS = [
    "btn-smart", "btn-manual", "panel-smart", "panel-manual",
    "zip_code", "soil_confidence", "building_type", "floor_area_m2",
    "year_built", "proto-area-hint", "year-factor-hint",
    "s_B", "s_A", "s_T_in_HP", "s_mfls",
    "smart-error", "smart-btn",
    "pipeline-panel", "pipeline-s1", "pipeline-s2",
    "smart-result", "sres-L", "sres-H", "sres-NB",
    "sres-NB-range",
    "two-pass-block", "sres-L-heat", "sres-L-cool", "sres-governing",
    "sres-imbalance-line", "sres-solar-line",
    "bar-L-heat", "bar-L-cool",
    "cost-section", "cost-region-tag", "cost-state-tag",
    "cost-best-pft", "cost-best-total", "cost-base-pft", "cost-base-total",
    "cost-worst-pft", "cost-worst-total",
    "cost-cmp-base", "cost-cmp-us", "cost-cmp-best", "cost-cmp-worst",
    "cost-breakdown-table", "cost-breakdown-body",
    "cost-range-marker", "cost-range-min", "cost-range-max", "cost-range-label",
    "s6-section", "s6-headline", "s6-before-L", "s6-before-cost",
    "s6-after-L", "s6-after-cost", "s6-peaker-kw", "s6-peaker-type",
    "s6-chart-a",
    "s6-cap-note", "s6-cap-kw", "s6-nb-val", "s6-h-val",
    "s6-comparison", "s6-m1-cutoff", "s6-m2-cutoff", "s6-m1-hrs", "s6-m2-hrs",
    "s6-m1-coverage", "s6-m2-coverage", "s6-m1-peaker", "s6-m2-peaker",
    "s6-m1-L", "s6-m2-L", "s6-m1-save", "s6-m2-save",
    "sizing-form", "calc-error", "calc-btn",
    "result-panel", "res-L", "res-H", "res-NB",
]


@pytest.fixture(scope="module")
def index_html():
    app.config["TESTING"] = True
    with app.test_client() as c:
        return c.get("/").get_data(as_text=True)


def test_index_renders(client):
    assert client.get("/").status_code == 200


@pytest.mark.parametrize("el_id", REQUIRED_IDS)
def test_index_contains_hook_id(index_html, el_id):
    assert f'id="{el_id}"' in index_html, f"main.js hook id '{el_id}' missing"


def test_geometry_input_present(index_html):
    # s_NB before the methodology-precision plan, s_H_target after
    assert 'id="s_H_target"' in index_html or 'id="s_NB"' in index_html


def test_references_renders(client):
    assert client.get("/references").status_code == 200


def test_dev_renders(client):
    assert client.get("/dev").status_code == 200
