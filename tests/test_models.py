from geosite.models import SiteData, LoadPulses


def test_site_data_fields():
    sd = SiteData(
        geoid="17031010200",
        k=1.50, alpha=0.075, T_g=12.0,
        climate_zone="5A", data_available=True,
    )
    assert sd.geoid == "17031010200"
    assert sd.k == 1.50
    assert sd.data_available is True


def test_load_pulses_fields():
    lp = LoadPulses(q_h=-78500.0, q_m=-32000.0, q_y=-3800.0)
    assert lp.q_h < 0          # heating dominant → negative
    assert abs(lp.q_m) < abs(lp.q_h)    # monthly average less extreme than hourly peak
