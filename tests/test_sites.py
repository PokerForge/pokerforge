from ui.sites import site_label, site_value, SITE_LABELS


def test_site_label_maps_every_known_source():
    assert site_label('ipoker') == 'iPoker'
    assert site_label('grosvenor_xml') == 'Grosvenor'
    assert site_label('pokerstars') == 'PokerStars'
    assert site_label('ggpoker') == 'GGPoker'
    assert site_label('winning_network') == 'Winning Network'


def test_site_label_falls_back_to_the_raw_value_for_an_unknown_source():
    assert site_label('some_future_site') == 'some_future_site'


def test_site_value_reverses_site_label_for_every_known_source():
    for source, label in SITE_LABELS.items():
        assert site_value(label) == source


def test_site_value_falls_back_to_treating_an_unknown_label_as_the_raw_value():
    assert site_value('some_future_site') == 'some_future_site'
