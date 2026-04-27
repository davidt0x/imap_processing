"""Tests for automatic SPDF validation of generated CDF files."""

from __future__ import annotations

from pathlib import Path

import pytest

from imap_processing.cdf.spdf_validation import SpdfValidationError
from imap_processing.tests import conftest as test_conftest


class _FakeItem:
    """Minimal pytest item stand-in for marker lookups."""

    def __init__(self, *, marked: bool):
        self._marked = marked

    def get_closest_marker(self, name: str):
        if self._marked and name == "spdf_autovalidate":
            return object()
        return None


def test_is_spdf_generated_cdf_validation_enabled(monkeypatch):
    """Test the env-var gate for auto-validation."""
    monkeypatch.setenv("IMAP_SPDF_VALIDATE_GENERATED_CDFS", "1")
    assert test_conftest.is_spdf_generated_cdf_validation_enabled() is True

    monkeypatch.setenv("IMAP_SPDF_VALIDATE_GENERATED_CDFS", "false")
    assert test_conftest.is_spdf_generated_cdf_validation_enabled() is False


def test_should_auto_validate_generated_cdfs_requires_marker(monkeypatch):
    """Test that rollout requires both env enablement and a marker."""
    monkeypatch.setenv("IMAP_SPDF_VALIDATE_GENERATED_CDFS", "1")

    assert test_conftest.should_auto_validate_generated_cdfs(
        _FakeItem(marked=True)
    ) is True
    assert test_conftest.should_auto_validate_generated_cdfs(
        _FakeItem(marked=False)
    ) is False


def test_get_generated_l2plus_cdfs_filters_levels(tmp_path):
    """Test that only generated L2+ products are discovered."""
    l1_file = tmp_path / "imap_hit_l1b_standard-rates_20100105_v001.cdf"
    l2_file = tmp_path / "imap_hit_l2_standard-intensity_20100105_v001.cdf"
    l2a_file = tmp_path / "imap_idex_l2a_sci-1week_20231218_v001.cdf"
    invalid_name = tmp_path / "notes.cdf"

    for file_path in [l1_file, l2_file, l2a_file, invalid_name]:
        file_path.write_text("cdf")

    assert test_conftest.get_generated_l2plus_cdfs(tmp_path) == [l2_file, l2a_file]


def test_auto_validate_generated_cdfs_noop_when_env_unset(tmp_path, monkeypatch):
    """Test that auto-validation is disabled unless explicitly enabled."""
    monkeypatch.delenv("IMAP_SPDF_VALIDATE_GENERATED_CDFS", raising=False)
    generated_file = tmp_path / "imap_hit_l2_standard-intensity_20100105_v001.cdf"
    generated_file.write_text("cdf")
    validated = []

    def validator(cdf_path: Path, *, stream_output: bool):
        validated.append((cdf_path, stream_output))

    result = test_conftest.auto_validate_generated_cdfs(
        tmp_path,
        _FakeItem(marked=True),
        validator=validator,
    )

    assert result == []
    assert validated == []


def test_auto_validate_generated_cdfs_noop_when_test_is_unmarked(
    tmp_path, monkeypatch
):
    """Test that auto-validation ignores unmarked tests."""
    monkeypatch.setenv("IMAP_SPDF_VALIDATE_GENERATED_CDFS", "1")
    generated_file = tmp_path / "imap_hit_l2_standard-intensity_20100105_v001.cdf"
    generated_file.write_text("cdf")
    validated = []

    def validator(cdf_path: Path, *, stream_output: bool):
        validated.append((cdf_path, stream_output))

    result = test_conftest.auto_validate_generated_cdfs(
        tmp_path,
        _FakeItem(marked=False),
        validator=validator,
    )

    assert result == []
    assert validated == []


def test_auto_validate_generated_cdfs_validates_discovered_l2plus(
    tmp_path, monkeypatch
):
    """Test validating all generated L2+ files while skipping lower levels."""
    monkeypatch.setenv("IMAP_SPDF_VALIDATE_GENERATED_CDFS", "1")
    monkeypatch.setattr(
        test_conftest,
        "is_spdf_validator_available",
        lambda: True,
    )

    skipped_l1 = tmp_path / "imap_hit_l1b_standard-rates_20100105_v001.cdf"
    validated_l2 = tmp_path / "imap_hit_l2_standard-intensity_20100105_v001.cdf"
    validated_l2a = tmp_path / "imap_idex_l2a_sci-1week_20231218_v001.cdf"
    for file_path in [skipped_l1, validated_l2, validated_l2a]:
        file_path.write_text("cdf")

    validated = []

    def validator(cdf_path: Path, *, stream_output: bool):
        validated.append((cdf_path, stream_output))

    result = test_conftest.auto_validate_generated_cdfs(
        tmp_path,
        _FakeItem(marked=True),
        validator=validator,
    )

    assert result == [validated_l2, validated_l2a]
    assert validated == [
        (validated_l2, False),
        (validated_l2a, False),
    ]


def test_auto_validate_generated_cdfs_raises_clean_failure(tmp_path, monkeypatch):
    """Test that validator failures fail the test cleanly."""
    monkeypatch.setenv("IMAP_SPDF_VALIDATE_GENERATED_CDFS", "1")
    monkeypatch.setattr(
        test_conftest,
        "is_spdf_validator_available",
        lambda: True,
    )

    generated_file = tmp_path / "imap_swe_l2_sci_20240510_v001.cdf"
    generated_file.write_text("cdf")

    def validator(cdf_path: Path, *, stream_output: bool):
        raise SpdfValidationError(
            f"SPDF validation failed for {cdf_path}.\n"
            "The following variables are not ISTP-compliant:\n\tepoch"
        )

    with pytest.raises(pytest.fail.Exception, match="generated CDF files"):
        test_conftest.auto_validate_generated_cdfs(
            tmp_path,
            _FakeItem(marked=True),
            validator=validator,
        )
