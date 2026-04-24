"""Tests for the SPDF CLI validation helpers."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest import mock

import pytest

from imap_processing.cdf.spdf_validation import (
    SpdfValidationError,
    SpdfValidatorConfig,
    SpdfValidatorUnavailableError,
    _spdf_output_has_compliance_errors,
    build_spdf_validation_command,
    is_spdf_validator_available,
    resolve_spdf_validator_config,
    should_stream_spdf_output,
    validate_cdf_with_spdf,
)


def test_resolve_spdf_validator_config_from_env(monkeypatch, tmp_path):
    """Test resolving the validator configuration from environment variables."""
    skteditor_jar = tmp_path / "spdfjavaClasses.jar"
    cdf_lib = tmp_path / "cdf-lib"
    cdf_lib.mkdir()
    cdf_jni_lib = tmp_path / "cdf-jni"
    cdf_jni_lib.mkdir()
    cdfjava_jar = cdf_lib / "cdfjava.jar"
    skteditor_jar.write_text("jar")
    cdfjava_jar.write_text("jar")
    monkeypatch.setenv("SPDF_SKTEDITOR_JAR", str(skteditor_jar))
    monkeypatch.delenv("SPDF_SKTEDITOR_DIR", raising=False)
    monkeypatch.delenv("CDF_JAVA_JAR", raising=False)
    monkeypatch.setenv("CDF_JNI_LIB", str(cdf_jni_lib))
    monkeypatch.setenv("CDF_LIB", str(cdf_lib))
    monkeypatch.setenv("SPDF_JAVA_EXECUTABLE", "/usr/bin/java")

    config = resolve_spdf_validator_config()

    assert config == SpdfValidatorConfig(
        java_executable="/usr/bin/java",
        skteditor_jar=skteditor_jar.resolve(),
        cdf_java_jar=cdfjava_jar.resolve(),
        cdf_jni_lib_dir=cdf_jni_lib.resolve(),
        cdf_lib_dir=cdf_lib.resolve(),
    )


def test_resolve_spdf_validator_config_missing_java(monkeypatch):
    """Test that missing Java raises a clear error."""
    monkeypatch.delenv("SPDF_JAVA_EXECUTABLE", raising=False)
    monkeypatch.delenv("SPDF_SKTEDITOR_JAR", raising=False)
    monkeypatch.delenv("SPDF_SKTEDITOR_DIR", raising=False)
    monkeypatch.delenv("CDF_JAVA_JAR", raising=False)
    monkeypatch.delenv("CDF_LIB", raising=False)
    with mock.patch(
        "imap_processing.cdf.spdf_validation.shutil.which",
        return_value=None,
    ):
        with pytest.raises(SpdfValidatorUnavailableError, match="Java was not found"):
            resolve_spdf_validator_config()


def test_build_spdf_validation_command(tmp_path):
    """Test the Java command built for SPDF validation."""
    cdf_path = tmp_path / "sample.cdf"
    config = SpdfValidatorConfig(
        java_executable="java",
        skteditor_jar=Path("/opt/skteditor/spdfjavaClasses.jar"),
        cdf_java_jar=Path("/opt/cdf/lib/cdfjava.jar"),
        cdf_jni_lib_dir=Path("/opt/cdf/jni"),
        cdf_lib_dir=Path("/opt/cdf/lib"),
    )

    command = build_spdf_validation_command(cdf_path, config=config)

    assert command == [
        "java",
        "-Djava.library.path=/opt/cdf/jni:/opt/cdf/lib",
        "-cp",
        "/opt/skteditor/spdfjavaClasses.jar:/opt/cdf/lib/cdfjava.jar",
        "gsfc.spdf.istp.tools.CDFCheck",
        str(cdf_path.resolve()),
    ]


def test_validate_cdf_with_spdf_success(tmp_path):
    """Test a successful validator subprocess run."""
    cdf_path = tmp_path / "sample.cdf"
    cdf_path.write_text("cdf")
    config = SpdfValidatorConfig(
        java_executable="java",
        skteditor_jar=Path("/opt/skteditor/spdfjavaClasses.jar"),
        cdf_java_jar=Path("/opt/cdf/lib/cdfjava.jar"),
        cdf_jni_lib_dir=Path("/opt/cdf/jni"),
        cdf_lib_dir=Path("/opt/cdf/lib"),
    )
    completed = subprocess.CompletedProcess(
        args=["java"],
        returncode=0,
        stdout="No issues found",
        stderr="",
    )

    with mock.patch(
        "imap_processing.cdf.spdf_validation.subprocess.run",
        return_value=completed,
    ) as mock_run:
        result = validate_cdf_with_spdf(cdf_path, config=config)

    assert result.stdout == "No issues found"
    assert mock_run.call_args.kwargs["env"]["LD_LIBRARY_PATH"].startswith("/opt/cdf/jni")
    assert mock_run.call_args.kwargs["capture_output"] is True


def test_validate_cdf_with_spdf_failure(tmp_path):
    """Test surfacing validator failures."""
    cdf_path = tmp_path / "sample.cdf"
    cdf_path.write_text("cdf")
    config = SpdfValidatorConfig(
        java_executable="java",
        skteditor_jar=Path("/opt/skteditor/spdfjavaClasses.jar"),
        cdf_java_jar=Path("/opt/cdf/lib/cdfjava.jar"),
        cdf_jni_lib_dir=Path("/opt/cdf/jni"),
        cdf_lib_dir=Path("/opt/cdf/lib"),
    )
    completed = subprocess.CompletedProcess(
        args=["java"],
        returncode=1,
        stdout="Validation issue",
        stderr="",
    )

    with mock.patch(
        "imap_processing.cdf.spdf_validation.subprocess.run",
        return_value=completed,
    ):
        with pytest.raises(SpdfValidationError, match="Validation issue"):
            validate_cdf_with_spdf(cdf_path, config=config)


def test_validate_cdf_with_spdf_stream_output(tmp_path):
    """Test streaming mode for the validator subprocess."""
    cdf_path = tmp_path / "sample.cdf"
    cdf_path.write_text("cdf")
    config = SpdfValidatorConfig(
        java_executable="java",
        skteditor_jar=Path("/opt/skteditor/spdfjavaClasses.jar"),
        cdf_java_jar=Path("/opt/cdf/lib/cdfjava.jar"),
        cdf_jni_lib_dir=Path("/opt/cdf/jni"),
        cdf_lib_dir=Path("/opt/cdf/lib"),
    )
    completed = subprocess.CompletedProcess(
        args=["java"],
        returncode=0,
        stdout=None,
        stderr=None,
    )

    with mock.patch(
        "imap_processing.cdf.spdf_validation.subprocess.run",
        return_value=completed,
    ) as mock_run:
        result = validate_cdf_with_spdf(cdf_path, config=config, stream_output=True)

    assert result.stdout is None
    assert mock_run.call_args.kwargs["capture_output"] is True


def test_validate_cdf_with_spdf_fails_on_noncompliance_output(tmp_path):
    """Test that non-compliance text in stdout fails validation."""
    cdf_path = tmp_path / "sample.cdf"
    cdf_path.write_text("cdf")
    config = SpdfValidatorConfig(
        java_executable="java",
        skteditor_jar=Path("/opt/skteditor/spdfjavaClasses.jar"),
        cdf_java_jar=Path("/opt/cdf/lib/cdfjava.jar"),
        cdf_jni_lib_dir=Path("/opt/cdf/jni"),
        cdf_lib_dir=Path("/opt/cdf/lib"),
    )
    completed = subprocess.CompletedProcess(
        args=["java"],
        returncode=0,
        stdout=(
            "Global errors:\n\tWarning: something\n"
            "The following variables are not ISTP-compliant:\n\tepoch\n"
        ),
        stderr="",
    )

    with mock.patch(
        "imap_processing.cdf.spdf_validation.subprocess.run",
        return_value=completed,
    ):
        with pytest.raises(SpdfValidationError, match="not ISTP-compliant"):
            validate_cdf_with_spdf(cdf_path, config=config)


def test_validate_cdf_with_spdf_failure_prints_output(tmp_path, capsys):
    """Test that failing validation prints checker output by default."""
    cdf_path = tmp_path / "sample.cdf"
    cdf_path.write_text("cdf")
    config = SpdfValidatorConfig(
        java_executable="java",
        skteditor_jar=Path("/opt/skteditor/spdfjavaClasses.jar"),
        cdf_java_jar=Path("/opt/cdf/lib/cdfjava.jar"),
        cdf_jni_lib_dir=Path("/opt/cdf/jni"),
        cdf_lib_dir=Path("/opt/cdf/lib"),
    )
    completed = subprocess.CompletedProcess(
        args=["java"],
        returncode=0,
        stdout="The following variables are not ISTP-compliant:\n\tepoch\n",
        stderr="",
    )

    with mock.patch(
        "imap_processing.cdf.spdf_validation.subprocess.run",
        return_value=completed,
    ):
        with pytest.raises(SpdfValidationError):
            validate_cdf_with_spdf(cdf_path, config=config, stream_output=False)

    captured = capsys.readouterr()
    assert "not ISTP-compliant" in captured.out


def test_spdf_output_has_compliance_errors():
    """Test compliance-error detection from SPDF output."""
    assert _spdf_output_has_compliance_errors(
        "The following variables are not ISTP-compliant:\n\tepoch",
        "",
    )
    assert not _spdf_output_has_compliance_errors(
        "Global errors:\n\tWarning: row major recommended.",
        "",
    )


def test_should_stream_spdf_output(monkeypatch):
    """Test the env-var driven streaming toggle."""
    monkeypatch.setenv("IMAP_SPDF_STREAM_OUTPUT", "1")
    assert should_stream_spdf_output() is True
    monkeypatch.setenv("IMAP_SPDF_STREAM_OUTPUT", "false")
    assert should_stream_spdf_output() is False


def test_is_spdf_validator_available(monkeypatch):
    """Test the public availability helper."""
    monkeypatch.setattr(
        "imap_processing.cdf.spdf_validation.resolve_spdf_validator_config",
        lambda: mock.sentinel.config,
    )
    assert is_spdf_validator_available() is True
