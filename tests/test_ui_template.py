"""Regression guard: static/main.js queries these ids; index.html must keep them."""

import pytest
from app import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


REQUIRED_IDS = [
    "panel-smart",
    "zip_code", "soil_confidence", "building_type", "floor_area_m2",
    "building_age", "proto-area-hint", "year-factor-hint",
    "s_wwr", "s_envelope", "s_glazing",
    "wizard-step1", "stage1-btn", "stage1-error", "stage1-result",
    "pipeline-nb", "step1-status", "pipeline-s1", "pipeline-s2",
    "s_H_min", "s_B", "s_T_in_HP_heat", "s_T_in_HP_cool",
    "borehole_config", "s_rbore", "s_rpin", "s_rpext", "s_LU",
    "s_kgrout", "s_kpipe", "s_hconv", "s_Cp", "s_mfls",
    "wizard-step2", "stage2-btn", "stage2-error", "step2-status",
    "smart-result", "sres-L", "sres-H", "sres-NB", "sres-NB-range",
    "two-pass-block", "sres-L-heat", "sres-L-cool", "sres-governing",
    "sres-imbalance-line", "sres-solar-line", "bar-L-heat", "bar-L-cool",
    "cost-section", "cost-region-tag", "cost-state-tag",
    "cost-best-pft", "cost-best-total", "cost-base-pft", "cost-base-total",
    "cost-worst-pft", "cost-worst-total",
    "cost-cmp-base", "cost-cmp-us", "cost-cmp-best", "cost-cmp-worst",
    "cost-breakdown-table", "cost-breakdown-body",
    "cost-range-marker", "cost-range-min", "cost-range-max", "cost-range-label",
    "cost-gshp-line", "cost-gshp-tons", "cost-gshp-equip",
    "s6-section", "s6-headline", "s6-before-L", "s6-before-cost",
    "s6-after-L", "s6-after-cost", "s6-peaker-kw", "s6-peaker-type",
    "s6-peaker-purpose", "s6-recalc-btn", "s6-savings-note",
    "s6-chart-a", "s6-chart-ldc",
    "s6-cap-note", "s6-cap-kw", "s6-nb-val", "s6-h-val",
    "s6-comparison", "s6-m2-cutoff", "s6-m2-hrs",
    "s6-m2-coverage", "s6-m2-peaker", "s6-m2-L", "s6-m2-save",
    "cost-system-summary", "cost-drill-base", "cost-hp-equip",
    "cost-peaker-row", "cost-peaker-label", "cost-peaker-equip", "cost-system-total",
    "s7-section", "s7-generate-btn", "s7-error", "s7-report",
    "s7-design", "s7-performance", "s7-cost", "s7-copy-btn",
    "r-score-card",
    "borehole-plan", "borehole-plan-report",
    "r-faq-card", "faq-topics", "faq-answer", "faq-answer-label", "faq-answer-text",
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
    assert 'id="s_H_min"' in index_html


DEV_REQUIRED_IDS = ["t-run", "t-hmin", "t-nb", "s4a-in", "s4a-out",
                    "s1a-out", "s1b-out", "s2-out", "s4-out", "s5-out",
                    "borehole-plan-dev"]


@pytest.fixture(scope="module")
def dev_html():
    app.config["TESTING"] = True
    with app.test_client() as c:
        with c.session_transaction() as sess:
            sess["dev_auth"] = True
        return c.get("/dev").get_data(as_text=True)


@pytest.mark.parametrize("el_id", DEV_REQUIRED_IDS)
def test_dev_contains_hook_id(dev_html, el_id):
    assert f'id="{el_id}"' in dev_html, f"dev.html hook id '{el_id}' missing"


def test_references_renders(client):
    assert client.get("/references").status_code == 200


def test_dev_renders(client):
    with client.session_transaction() as sess:
        sess["dev_auth"] = True
    assert client.get("/dev").status_code == 200


def test_dev_requires_auth(client):
    """Unauthenticated GET /dev must redirect to login (302), never 200."""
    resp = client.get("/dev")
    assert resp.status_code == 302, "/dev must redirect unauthenticated users to /dev-login"
    assert "dev-login" in (resp.headers.get("Location") or "")


def test_new_building_types_in_dropdown(index_html):
    """All 4 newly-enabled building types must appear in the main UI dropdown."""
    for val in ("retail_stripmall", "restaurant_fastfood",
                "restaurant_sitdown", "highrise_apartment"):
        assert f'value="{val}"' in index_html, f"building type '{val}' missing from dropdown"


def test_new_building_types_in_dev(dev_html):
    """All 4 newly-enabled building types must appear in the dev trace tool."""
    for val in ("retail_stripmall", "restaurant_fastfood",
                "restaurant_sitdown", "highrise_apartment"):
        assert f'value="{val}"' in dev_html, f"building type '{val}' missing from dev dropdown"
