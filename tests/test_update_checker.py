"""core/update_checker.py — a manifest fetch that must never raise (it's
called from the UI thread's async worker) and must never treat "not set
up yet" as an error the same way it treats "actually failed"."""
import json

import core.update_checker as uc


def _manifest_url(tmp_path, data):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return "file:///" + str(path).replace("\\", "/")


def test_unconfigured_reports_not_checked_without_erroring(monkeypatch):
    monkeypatch.setattr(uc, "UPDATE_MANIFEST_URL", None)
    monkeypatch.setattr(uc, "GITHUB_REPO", None)
    result = uc.check_for_update()
    assert result.checked is False
    assert result.update_available is False
    assert "set up" in result.error


def test_github_repo_takes_priority_over_manifest_url(monkeypatch, tmp_path):
    """If both are configured, GITHUB_REPO wins — the manifest URL is only
    a fallback for when releases don't live on GitHub."""
    monkeypatch.setattr(uc, "GITHUB_REPO", "someone/somerepo")
    monkeypatch.setattr(uc, "UPDATE_MANIFEST_URL", "file:///should/not/be/used.json")
    calls = []
    monkeypatch.setattr(uc, "_check_github_releases",
                         lambda repo, timeout: calls.append(repo) or uc.UpdateCheckResult(checked=True, update_available=False))
    uc.check_for_update()
    assert calls == ["someone/somerepo"]


def test_github_release_newer_than_current_reports_update_available(monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            import json as _json
            return _json.dumps({
                "tag_name": "v9.9.9",
                "html_url": "https://github.com/someone/somerepo/releases/tag/v9.9.9",
                "body": "Big release",
                "assets": [{"name": "PokerForge-Setup-9.9.9.exe",
                            "browser_download_url": "https://example.com/PokerForge-Setup-9.9.9.exe"}],
            }).encode('utf-8')

    monkeypatch.setattr(uc.urllib.request, "urlopen", lambda *a, **k: FakeResponse())
    monkeypatch.setattr(uc, "GITHUB_REPO", "someone/somerepo")
    result = uc.check_for_update()
    assert result.checked is True
    assert result.update_available is True
    assert result.latest_version == "9.9.9"
    assert result.download_url == "https://example.com/PokerForge-Setup-9.9.9.exe"
    assert result.notes == "Big release"


def test_github_release_missing_tag_is_not_checked(monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            import json as _json
            return _json.dumps({"body": "no tag_name field"}).encode('utf-8')

    monkeypatch.setattr(uc.urllib.request, "urlopen", lambda *a, **k: FakeResponse())
    monkeypatch.setattr(uc, "GITHUB_REPO", "someone/somerepo")
    result = uc.check_for_update()
    assert result.checked is False
    assert result.error


def test_github_unreachable_is_handled_not_raised(monkeypatch):
    monkeypatch.setattr(uc, "GITHUB_REPO", "someone/somerepo")

    def _raise(*a, **k):
        raise OSError("network is down")

    monkeypatch.setattr(uc.urllib.request, "urlopen", _raise)
    result = uc.check_for_update()
    assert result.checked is False
    assert result.error


def test_newer_version_available(monkeypatch, tmp_path):
    url = _manifest_url(tmp_path, {"version": "9.9.9", "url": "https://example.com", "notes": "hi"})
    monkeypatch.setattr(uc, "UPDATE_MANIFEST_URL", url)
    result = uc.check_for_update()
    assert result.checked is True
    assert result.update_available is True
    assert result.latest_version == "9.9.9"
    assert result.download_url == "https://example.com"
    assert result.notes == "hi"


def test_same_version_reports_up_to_date(monkeypatch, tmp_path):
    url = _manifest_url(tmp_path, {"version": uc.APP_VERSION})
    monkeypatch.setattr(uc, "UPDATE_MANIFEST_URL", url)
    result = uc.check_for_update()
    assert result.checked is True
    assert result.update_available is False


def test_older_remote_version_is_not_an_update(monkeypatch, tmp_path):
    url = _manifest_url(tmp_path, {"version": "0.0.1"})
    monkeypatch.setattr(uc, "UPDATE_MANIFEST_URL", url)
    result = uc.check_for_update()
    assert result.checked is True
    assert result.update_available is False


def test_malformed_manifest_is_not_checked_not_a_crash(monkeypatch, tmp_path):
    url = _manifest_url(tmp_path, {"notes": "no version field"})
    monkeypatch.setattr(uc, "UPDATE_MANIFEST_URL", url)
    result = uc.check_for_update()
    assert result.checked is False
    assert result.error


def test_unreachable_url_is_handled_not_raised(monkeypatch):
    monkeypatch.setattr(uc, "UPDATE_MANIFEST_URL", "file:///definitely/does/not/exist.json")
    result = uc.check_for_update()
    assert result.checked is False
    assert result.error


def test_version_compare_orders_numerically_not_lexically():
    assert uc._version_gt("1.2.10", "1.2.9")
    assert uc._version_gt("2.0.0", "1.99.99")
    assert not uc._version_gt("1.2.9", "1.2.10")


def test_version_compare_pads_differing_segment_counts():
    # Plain tuple comparison would wrongly treat "1.0.0" as greater than
    # "1.0" (a shorter-but-equal prefix sorts as "less than" in Python) —
    # this is exactly the bug _version_gt exists to avoid.
    assert not uc._version_gt("1.0.0", "1.0")
    assert not uc._version_gt("1.0", "1.0.0")
    assert uc._version_gt("1.1", "1.0.9")
