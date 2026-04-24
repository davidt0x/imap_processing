"""Helpers for running the official SPDF SKTEditor CLI validator."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


class SpdfValidatorUnavailableError(RuntimeError):
    """Raised when the local SPDF validator installation cannot be found."""


class SpdfValidationError(RuntimeError):
    """Raised when the SPDF validator reports validation failures."""


@dataclass(frozen=True)
class SpdfValidatorConfig:
    """Resolved configuration for the SPDF CLI validator."""

    java_executable: str
    skteditor_jar: Path
    cdf_java_jar: Path
    cdf_jni_lib_dir: Path
    cdf_lib_dir: Path

    @property
    def classpath(self) -> str:
        """Return the Java classpath required for SPDF validation."""
        return f"{self.skteditor_jar}{os.pathsep}{self.cdf_java_jar}"

    @property
    def java_library_path(self) -> str:
        """Return the Java native-library search path."""
        return os.pathsep.join([str(self.cdf_jni_lib_dir), str(self.cdf_lib_dir)])


def should_stream_spdf_output() -> bool:
    """Return ``True`` when SPDF validator output should stream to the console."""
    return os.environ.get("IMAP_SPDF_STREAM_OUTPUT", "").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _build_spdf_failure_message(
    cdf_path: Path, stdout: str | None, stderr: str | None
) -> str:
    """Build a readable validation failure message."""
    message_parts = []
    if stdout:
        message_parts.append(stdout.strip())
    if stderr:
        message_parts.append(stderr.strip())
    message = "\n".join(part for part in message_parts if part)
    return f"SPDF validation failed for {cdf_path}.\n{message}".rstrip()


def _spdf_output_has_compliance_errors(stdout: str | None, stderr: str | None) -> bool:
    """Return ``True`` when SPDF output reports non-compliant metadata."""
    combined_output = "\n".join(part for part in (stdout, stderr) if part)
    return "not ISTP-compliant" in combined_output


def _emit_spdf_output(stdout: str | None, stderr: str | None) -> None:
    """Print validator output to the console when any output is available."""
    if stdout:
        print(stdout, end="" if stdout.endswith("\n") else "\n")
    if stderr:
        print(stderr, end="" if stderr.endswith("\n") else "\n", file=sys.stderr)


def _resolve_existing_path(path_str: str | None) -> Path | None:
    """Return an existing path if one was provided."""
    if not path_str:
        return None
    path = Path(path_str).expanduser().resolve()
    return path if path.exists() else None


def resolve_spdf_validator_config() -> SpdfValidatorConfig:
    """
    Resolve the local SPDF CLI validator installation.

    Returns
    -------
    SpdfValidatorConfig
        Configuration needed to run ``gsfc.spdf.istp.tools.CDFCheck``.

    Raises
    ------
    SpdfValidatorUnavailableError
        If Java, ``spdfjavaClasses.jar``, or ``cdfjava.jar`` cannot be found.
    """
    java_executable = os.environ.get("SPDF_JAVA_EXECUTABLE") or shutil.which("java")
    if not java_executable:
        raise SpdfValidatorUnavailableError(
            "Java was not found. Install Java and ensure `java` is on PATH."
        )

    skteditor_jar = _resolve_existing_path(os.environ.get("SPDF_SKTEDITOR_JAR"))
    if skteditor_jar is None:
        skteditor_dir = _resolve_existing_path(os.environ.get("SPDF_SKTEDITOR_DIR"))
        if skteditor_dir is not None:
            candidate = skteditor_dir / "spdfjavaClasses.jar"
            if candidate.exists():
                skteditor_jar = candidate
    if skteditor_jar is None:
        raise SpdfValidatorUnavailableError(
            "SPDF SKTEditor was not found. Set `SPDF_SKTEDITOR_JAR` or "
            "`SPDF_SKTEDITOR_DIR`."
        )

    cdf_java_jar = _resolve_existing_path(os.environ.get("CDF_JAVA_JAR"))
    cdf_jni_lib_dir = _resolve_existing_path(os.environ.get("CDF_JNI_LIB"))
    cdf_lib_dir = _resolve_existing_path(os.environ.get("CDF_LIB"))
    if cdf_java_jar is None and cdf_lib_dir is not None:
        candidate = cdf_lib_dir / "cdfjava.jar"
        if candidate.exists():
            cdf_java_jar = candidate
    if cdf_java_jar is None:
        raise SpdfValidatorUnavailableError(
            "CDF Java support was not found. Set `CDF_JAVA_JAR` or `CDF_LIB`."
        )
    if cdf_lib_dir is None:
        cdf_lib_dir = cdf_java_jar.parent
    if cdf_jni_lib_dir is None:
        default_jni_dir = cdf_java_jar.parent.parent / "jni"
        if default_jni_dir.exists():
            cdf_jni_lib_dir = default_jni_dir
    if cdf_jni_lib_dir is None:
        raise SpdfValidatorUnavailableError(
            "CDF JNI native library directory was not found. Set `CDF_JNI_LIB`."
        )

    return SpdfValidatorConfig(
        java_executable=java_executable,
        skteditor_jar=skteditor_jar,
        cdf_java_jar=cdf_java_jar,
        cdf_jni_lib_dir=cdf_jni_lib_dir,
        cdf_lib_dir=cdf_lib_dir,
    )


def is_spdf_validator_available() -> bool:
    """Return ``True`` when the local SPDF CLI validator is available."""
    try:
        resolve_spdf_validator_config()
    except SpdfValidatorUnavailableError:
        return False
    return True


def build_spdf_validation_command(
    cdf_path: Path | str, config: SpdfValidatorConfig | None = None
) -> list[str]:
    """
    Build the Java command for validating a CDF with SPDF's CLI checker.

    Parameters
    ----------
    cdf_path : pathlib.Path or str
        CDF file to validate.
    config : SpdfValidatorConfig, optional
        Pre-resolved validator configuration.

    Returns
    -------
    list[str]
        The command suitable for ``subprocess.run``.
    """
    config = config or resolve_spdf_validator_config()
    return [
        config.java_executable,
        f"-Djava.library.path={config.java_library_path}",
        "-cp",
        config.classpath,
        "gsfc.spdf.istp.tools.CDFCheck",
        str(Path(cdf_path).resolve()),
    ]


def validate_cdf_with_spdf(
    cdf_path: Path | str,
    *,
    config: SpdfValidatorConfig | None = None,
    timeout: int = 120,
    stream_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    """
    Validate a CDF using the official SPDF SKTEditor CLI checker.

    Parameters
    ----------
    cdf_path : pathlib.Path or str
        The CDF file to validate.
    config : SpdfValidatorConfig, optional
        Pre-resolved validator configuration.
    timeout : int, optional
        Timeout in seconds for the validation subprocess.
    stream_output : bool, optional
        If ``True``, stream the validator stdout/stderr directly to the console
        instead of capturing it in the returned process object.

    Returns
    -------
    subprocess.CompletedProcess[str]
        The completed validation subprocess result.

    Raises
    ------
    SpdfValidationError
        If the CLI validator reports an error.
    """
    config = config or resolve_spdf_validator_config()
    cdf_path = Path(cdf_path).resolve()
    env = os.environ.copy()
    ld_library_path = env.get("LD_LIBRARY_PATH", "")
    required_paths = [str(config.cdf_jni_lib_dir), str(config.cdf_lib_dir)]
    existing_paths = [path for path in ld_library_path.split(":") if path]
    for required_path in reversed(required_paths):
        if required_path not in existing_paths:
            existing_paths.insert(0, required_path)
    env["LD_LIBRARY_PATH"] = ":".join(existing_paths)

    result = subprocess.run(
        build_spdf_validation_command(cdf_path, config=config),
        capture_output=True,
        text=True,
        env=env,
        timeout=timeout,
        check=False,
    )
    has_failures = result.returncode != 0 or _spdf_output_has_compliance_errors(
        result.stdout, result.stderr
    )
    if stream_output or has_failures:
        _emit_spdf_output(result.stdout, result.stderr)
    if has_failures:
        raise SpdfValidationError(
            _build_spdf_failure_message(cdf_path, result.stdout, result.stderr)
        )
    return result


def main(argv: list[str] | None = None) -> int:
    """Run the SPDF validator as a small local CLI."""
    parser = argparse.ArgumentParser(
        description="Validate one or more CDF files with the SPDF CLI checker."
    )
    parser.add_argument("cdf_files", nargs="+", help="CDF files to validate.")
    parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="Validation timeout in seconds for each file.",
    )
    parser.add_argument(
        "--stream-output",
        action="store_true",
        help="Stream validator stdout/stderr directly to the console.",
    )
    args = parser.parse_args(argv)

    try:
        config = resolve_spdf_validator_config()
    except SpdfValidatorUnavailableError as exc:
        parser.exit(2, f"{exc}\n")

    for cdf_file in args.cdf_files:
        try:
            result = validate_cdf_with_spdf(
                cdf_file,
                config=config,
                timeout=args.timeout,
                stream_output=args.stream_output,
            )
        except SpdfValidationError as exc:
            parser.exit(1, f"{exc}\n")
        output = result.stdout.strip()
        if output:
            print(output)
        print(f"SPDF validation passed: {Path(cdf_file).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
