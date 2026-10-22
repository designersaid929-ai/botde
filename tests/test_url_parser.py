import pytest
from bot.utils.url_parser import parse_instagram_input


def test_plain_username():
    res = parse_instagram_input("cristiano")
    assert res.is_valid
    assert res.input_type == "profile"
    assert res.username == "cristiano"


def test_at_username():
    res = parse_instagram_input("@natgeo")
    assert res.is_valid
    assert res.input_type == "profile"
    assert res.username == "natgeo"


def test_profile_url_https():
    res = parse_instagram_input("https://www.instagram.com/nasa/")
    assert res.is_valid
    assert res.input_type == "profile"
    assert res.username == "nasa"


def test_profile_url_with_query_params():
    res = parse_instagram_input("https://instagram.com/taylorswift?igsh=YzljYTk1ODg3Zg==")
    assert res.is_valid
    assert res.input_type == "profile"
    assert res.username == "taylorswift"


def test_post_url():
    res = parse_instagram_input("https://www.instagram.com/p/DB12345_xyz/")
    assert res.is_valid
    assert res.input_type == "post"
    assert res.shortcode == "DB12345_xyz"


def test_reel_url():
    res = parse_instagram_input("https://www.instagram.com/reel/C-abc999/?utm_source=ig_web_copy_link")
    assert res.is_valid
    assert res.input_type == "post"
    assert res.shortcode == "C-abc999"


def test_tv_url():
    res = parse_instagram_input("https://instagram.com/tv/B_xyz123/")
    assert res.is_valid
    assert res.input_type == "post"
    assert res.shortcode == "B_xyz123"


def test_story_url():
    res = parse_instagram_input("https://www.instagram.com/stories/leomessi/")
    assert res.is_valid
    assert res.input_type == "story"
    assert res.username == "leomessi"
    assert res.story_id is None


def test_story_url_with_id():
    res = parse_instagram_input("https://www.instagram.com/stories/leomessi/3456789123456/")
    assert res.is_valid
    assert res.input_type == "story"
    assert res.username == "leomessi"
    assert res.story_id == "3456789123456"


def test_reserved_paths_ignored():
    assert not parse_instagram_input("https://instagram.com/explore/").is_valid
    assert not parse_instagram_input("https://instagram.com/accounts/login/").is_valid
    assert not parse_instagram_input("explore").is_valid


def test_invalid_input():
    assert not parse_instagram_input("").is_valid
    assert not parse_instagram_input("https://google.com").is_valid
    assert not parse_instagram_input("/start").is_valid
