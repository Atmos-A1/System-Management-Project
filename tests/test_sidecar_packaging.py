"""Packaging contract tests for the Panther sidecar delivery.

These tests verify the delivery contract without requiring a full build or Windows.
They check that all required files exist and contain the expected configuration.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).parent.parent
SRC_DIR = REPO_ROOT / "src"


# ---------------------------------------------------------------------------
# File existence
# ---------------------------------------------------------------------------


def test_run_sidecar_exists():
    """run_sidecar.py exists at repo root."""
    assert (REPO_ROOT / "run_sidecar.py").exists(), "run_sidecar.py missing at repo root"


def test_build_sidecar_exists():
    """build_sidecar.py exists at repo root."""
    assert (REPO_ROOT / "build_sidecar.py").exists(), "build_sidecar.py missing at repo root"


def test_parent_watchdog_exists():
    """parent_watchdog.py exists in sidecar package."""
    assert (SRC_DIR / "panther/sidecar/parent_watchdog.py").exists(), "parent_watchdog.py missing"


def test_stdio_has_configure_stdio():
    """stdio.py has configure_stdio function."""
    stdio_path = SRC_DIR / "panther/sidecar/transport/stdio.py"
    content = stdio_path.read_text()
    assert "def configure_stdio()" in content, "configure_stdio() missing from stdio.py"


def test_server_calls_configure_stdio():
    """server.py calls configure_stdio() at start of main()."""
    server_path = SRC_DIR / "panther/sidecar/server.py"
    content = server_path.read_text()
    assert "configure_stdio()" in content, "server.py does not call configure_stdio()"


# ---------------------------------------------------------------------------
# run_sidecar.py contract
# ---------------------------------------------------------------------------


def test_run_sidecar_reconfigures_utf8():
    """run_sidecar.py reconfigures stdio for UTF-8 (delegates to stdio.py)."""
    content = (REPO_ROOT / "run_sidecar.py").read_text()
    # run_sidecar.py delegates to stdio.py's configure_stdio
    assert "configure_stdio" in content, "run_sidecar.py missing configure_stdio call"
    assert "_configure_stdio" in content, "run_sidecar.py missing stdio import"
    # The actual reconfigure logic is in stdio.py
    stdio_content = (SRC_DIR / "panther/sidecar/transport/stdio.py").read_text()
    assert "reconfigure" in stdio_content
    assert "utf-8" in stdio_content.lower()
    assert "backslashreplace" in stdio_content


def test_run_sidecar_only_starts_watchdog_when_frozen():
    """run_sidecar.py only starts watchdog when frozen."""
    content = (REPO_ROOT / "run_sidecar.py").read_text()
    assert "frozen" in content, "run_sidecar.py missing frozen check"
    assert "start_parent_watchdog" in content, "run_sidecar.py missing watchdog start"
    # Should only call watchdog when frozen
    assert "if getattr(sys, \"frozen\", False)" in content or 'if getattr(sys, "frozen", False)' in content


def test_run_sidecar_wraps_main_in_try_except():
    """run_sidecar.py wraps main in try/except with traceback to stderr."""
    content = (REPO_ROOT / "run_sidecar.py").read_text()
    assert "try:" in content and "except Exception:" in content
    assert "traceback.print_exc" in content
    assert "sys.stderr" in content
    assert "return 1" in content  # Returns 1 on fatal error (sys.exit(1) at bottom)


# ---------------------------------------------------------------------------
# build_sidecar.py contract
# ---------------------------------------------------------------------------


def test_build_sidecar_contains_required_pyinstaller_flags():
    """build_sidecar.py contains all required PyInstaller flags."""
    content = (REPO_ROOT / "build_sidecar.py").read_text()

    # Required flags
    assert "--onefile" in content
    assert "--console" in content
    assert "--clean" in content
    assert "--noconfirm" in content
    assert "--name" in content
    assert "panther-sidecar" in content

    # Required hidden imports
    assert "panther.services.directory_browser" in content
    assert "psutil._psutil_windows" in content

    # Required exclusions (must NOT collect Qt) - as separate list elements
    assert "--exclude-module" in content
    assert "PySide6" in content
    assert "shiboken6" in content
    assert "pytest" in content
    assert "tkinter" in content

    # Must NOT use --collect-submodules panther
    assert "--collect-submodules panther" not in content, "build_sidecar.py must not use --collect-submodules panther"

    # Must NOT use --windowed
    assert "--windowed" not in content, "build_sidecar.py must not use --windowed (breaks stdin/stdout pipes)"


def test_build_sidecar_target_triple_naming():
    """build_sidecar.py names output with target triple."""
    content = (REPO_ROOT / "build_sidecar.py").read_text()
    assert "target_triple" in content
    assert "panther-sidecar-" in content
    assert "x86_64-pc-windows-msvc" in content
    assert "x86_64-unknown-linux-gnu" in content


def test_build_sidecar_bloat_guard():
    """build_sidecar.py has 80 MB size check."""
    content = (REPO_ROOT / "build_sidecar.py").read_text()
    assert "80" in content
    assert "MB" in content or "bloat" in content.lower()


def test_build_sidecar_fails_if_missing():
    """build_sidecar.py fails with clear message if executable missing."""
    content = (REPO_ROOT / "build_sidecar.py").read_text()
    assert "not found" in content.lower() or "missing" in content.lower()
    assert "sys.exit" in content or "exit" in content


# ---------------------------------------------------------------------------
# tauri.conf.json contract
# ---------------------------------------------------------------------------


def test_tauri_conf_parses():
    """tauri.conf.json is valid JSON."""
    conf_path = REPO_ROOT / "src-tauri/tauri.conf.json"
    with open(conf_path) as f:
        conf = json.load(f)
    assert conf is not None


def test_tauri_conf_external_bin():
    """tauri.conf.json has correct externalBin."""
    conf_path = REPO_ROOT / "src-tauri/tauri.conf.json"
    with open(conf_path) as f:
        conf = json.load(f)
    assert "bundle" in conf
    assert "externalBin" in conf["bundle"]
    assert conf["bundle"]["externalBin"] == ["binaries/panther-sidecar"]


def test_tauri_conf_targets_nsis():
    """tauri.conf.json targets nsis."""
    conf_path = REPO_ROOT / "src-tauri/tauri.conf.json"
    with open(conf_path) as f:
        conf = json.load(f)
    assert "targets" in conf["bundle"]
    assert conf["bundle"]["targets"] == ["nsis"]


def test_tauri_conf_nsis_current_user():
    """tauri.conf.json has nsis installMode currentUser."""
    conf_path = REPO_ROOT / "src-tauri/tauri.conf.json"
    with open(conf_path) as f:
        conf = json.load(f)
    assert "windows" in conf["bundle"]
    assert "nsis" in conf["bundle"]["windows"]
    assert conf["bundle"]["windows"]["nsis"]["installMode"] == "currentUser"


# ---------------------------------------------------------------------------
# main.rs contract
# ---------------------------------------------------------------------------


def test_main_rs_env_vars():
    """main.rs sets PYTHONUTF8, PYTHONIOENCODING, PYTHONUNBUFFERED and no PYTHONPATH in bundled branch."""
    main_rs = REPO_ROOT / "src-tauri/src/main.rs"
    content = main_rs.read_text()

    # Required env vars in bundled branch
    assert 'PYTHONUTF8' in content
    assert 'PYTHONIOENCODING' in content
    assert 'PYTHONUNBUFFERED' in content

    # No PYTHONPATH in bundled branch (the sidecar is self-contained)
    # The bundled branch is the one using app.shell().sidecar()
    bundled_section = content[content.find('app.shell().sidecar'):content.find('spawn_dev_sidecar')]
    assert 'PYTHONPATH' not in bundled_section, "Bundled branch must not set PYTHONPATH"

    # Dev fallback still has PYTHONPATH
    dev_section = content[content.find('spawn_dev_sidecar'):]
    assert 'PYTHONPATH' in dev_section


def test_main_rs_sidecar_ref_type():
    """ipc/mod.rs defines SidecarRef as Arc<Option<SidecarHandle>>."""
    ipc_mod = REPO_ROOT / "src-tauri/src/ipc/mod.rs"
    content = ipc_mod.read_text()
    assert "SidecarRef" in content
    assert "Arc<Mutex<Option<crate::ipc::transport::SidecarHandle>>>" in content


def test_main_rs_always_manages_ref():
    """main.rs always manages the sidecar ref even on failure."""
    main_rs = REPO_ROOT / "src-tauri/src/main.rs"
    content = main_rs.read_text()
    # Should manage ipc_state and sidecar_ref in both success and failure paths
    assert "app.manage(ipc_state" in content
    assert "app.manage(sidecar_ref" in content


def test_main_rs_takes_child_on_terminated():
    """main.rs takes child out of handle on Terminated event."""
    main_rs = REPO_ROOT / "src-tauri/src/main.rs"
    content = main_rs.read_text()
    assert "CommandEvent::Terminated" in content
    assert ".take()" in content
    assert "child.lock().await.take()" in content


def test_main_rs_logs_clear_diagnostic_on_failure():
    """main.rs logs clear stderr diagnosis on sidecar failure."""
    main_rs = REPO_ROOT / "src-tauri/src/main.rs"
    content = main_rs.read_text()
    assert "eprintln" in content
    assert "sidecar" in content.lower()


# ---------------------------------------------------------------------------
# metrics.rs contract
# ---------------------------------------------------------------------------


def test_metrics_rs_accepts_sidecar_ref():
    """metrics.rs accepts State<'_, SidecarRef>."""
    metrics_rs = REPO_ROOT / "src-tauri/src/commands/metrics.rs"
    content = metrics_rs.read_text()
    assert "SidecarRef" in content
    assert "State<'_, SidecarRef>" in content


def test_metrics_rs_returns_honest_error_when_none():
    """metrics.rs returns honest error when sidecar is None."""
    metrics_rs = REPO_ROOT / "src-tauri/src/commands/metrics.rs"
    content = metrics_rs.read_text()
    assert "is_none()" in content or "is_none" in content
    assert "not running" in content.lower() or "not installed" in content.lower()


# ---------------------------------------------------------------------------
# Workflow contract
# ---------------------------------------------------------------------------


def test_windows_workflow_exists():
    """tauri-windows.yml exists."""
    workflow = REPO_ROOT / ".github/workflows/tauri-windows.yml"
    assert workflow.exists(), "tauri-windows.yml missing"


def test_windows_workflow_parses():
    """tauri-windows.yml is valid YAML (skip if PyYAML not installed)."""
    pytest.importorskip("yaml")
    import yaml

    workflow = REPO_ROOT / ".github/workflows/tauri-windows.yml"
    with open(workflow) as f:
        data = yaml.safe_load(f)
    assert data is not None
    assert "jobs" in data
    assert "windows-tauri" in data["jobs"]
    assert "installer-verify" in data["jobs"]


def test_windows_workflow_has_smoke_test():
    """tauri-windows.yml contains the smoke test step."""
    workflow = REPO_ROOT / ".github/workflows/tauri-windows.yml"
    content = workflow.read_text()
    assert "Smoke test frozen sidecar" in content
    assert "system_monitor.get_cpu_percent" in content
    assert "jsonrpc" in content
    assert "result" in content


def test_windows_workflow_uploads_installer():
    """tauri-windows.yml uploads NSIS installer."""
    workflow = REPO_ROOT / ".github/workflows/tauri-windows.yml"
    content = workflow.read_text()
    assert "panther-nsis-installer" in content
    assert "upload-artifact" in content


def test_windows_workflow_smoke_test_uses_processstartinfo():
    """tauri-windows.yml smoke test uses ProcessStartInfo (no RedirectStandardInput $null)."""
    workflow = REPO_ROOT / ".github/workflows/tauri-windows.yml"
    content = workflow.read_text()
    assert "ProcessStartInfo" in content, "Smoke test must use ProcessStartInfo"
    assert "RedirectStandardInput" in content, "Must redirect stdin"
    assert "RedirectStandardInput \$null" not in content, "Must not use dead \$null redirection"
    assert "StandardInput.WriteLine" in content, "Must write to stdin via WriteLine"
    assert "StandardInput.Close" in content, "Must close stdin"


def test_windows_workflow_install_locate_uses_panther_sidecar_exe():
    """tauri-windows.yml install-locate step asserts panther-sidecar.exe (Tauri strips triple)."""
    workflow = REPO_ROOT / ".github/workflows/tauri-windows.yml"
    content = workflow.read_text()
    assert "panther-sidecar.exe" in content, "Must look for panther-sidecar.exe (Tauri strips triple at bundle time)"
    # Triple-suffixed name accepted as fallback
    assert "panther-sidecar-x86_64-pc-windows-msvc.exe" in content


def test_windows_workflow_graceful_close_uses_closemainwindow():
    """tauri-windows.yml graceful shutdown test uses CloseMainWindow."""
    workflow = REPO_ROOT / ".github/workflows/tauri-windows.yml"
    content = workflow.read_text()
    assert "CloseMainWindow" in content, "Graceful shutdown test must use CloseMainWindow"
    assert "WaitForExit" in content, "Must wait for exit after CloseMainWindow"
    assert "Graceful shutdown" in content or "graceful" in content.lower()


def test_windows_workflow_has_forced_kill_test():
    """tauri-windows.yml has separate forced-kill orphan test."""
    workflow = REPO_ROOT / ".github/workflows/tauri-windows.yml"
    content = workflow.read_text()
    assert "Forced kill" in content or "forced kill" in content.lower()
    assert "Stop-Process" in content
    assert "Force" in content


def test_windows_workflow_uploads_build_summary():
    """tauri-windows.yml writes and uploads build-summary.txt."""
    workflow = REPO_ROOT / ".github/workflows/tauri-windows.yml"
    content = workflow.read_text()
    assert "build-summary.txt" in content
    assert "if: always()" in content


def test_windows_workflow_installer_upload_missing_artifact_policy():
    """The NSIS upload runs under `always()` so a missing artifact must warn.

    The upload step executes even when an earlier build step failed, in which
    case no installer exists. Failing the upload there would report a second,
    misleading error and obscure the real root cause, so the policy is `warn`.
    The installer is never silently dropped: `installer-verify` depends on the
    build job and is skipped when the bundle was not produced.
    """
    workflow = REPO_ROOT / ".github/workflows/tauri-windows.yml"
    content = workflow.read_text()

    # Locate the installer upload step and inspect only its own config.
    marker = "name: Upload NSIS installer"
    assert marker in content, "installer upload step is missing"
    step = content.split(marker, 1)[1]
    # Stop at the next top-level step definition.
    step = step.split("\n      - name:", 1)[0]

    assert "if-no-files-found: warn" in step, (
        "installer upload under `if: always()` must warn on a missing artifact, "
        "not fail with a misleading second error"
    )
    assert "if-no-files-found: error" not in step


def test_windows_workflow_installer_upload_gated_by_build():
    """installer-verify runs only when the build job succeeded."""
    workflow = REPO_ROOT / ".github/workflows/tauri-windows.yml"
    content = workflow.read_text()
    assert "needs: windows-tauri" in content


def test_windows_workflow_silent_install_waits():
    """Silent install must block until the installer exits and check its code.

    PowerShell's call operator does not wait for GUI-subsystem executables, so
    the install would race the discovery step and a failed install would be
    silently swallowed.
    """
    workflow = REPO_ROOT / ".github/workflows/tauri-windows.yml"
    content = workflow.read_text()

    marker = "name: Silent install"
    assert marker in content
    step = content.split(marker, 1)[1].split("\n      - name:", 1)[0]

    assert "Start-Process" in step
    assert "-Wait" in step
    assert "-PassThru" in step
    assert "ExitCode" in step
    # The non-waiting form must not be used to launch the installer.
    assert "& $installer.FullName /S" not in step


def test_windows_workflow_no_invalid_programfiles_x86_token():
    """`$env:ProgramFiles(x86)` is invalid PowerShell and must not be used."""
    workflow = REPO_ROOT / ".github/workflows/tauri-windows.yml"
    lines = workflow.read_text().splitlines()

    # Ignore comments: explanatory notes legitimately quote the bad token.
    offenders = [
        (i, line)
        for i, line in enumerate(lines, 1)
        if ("$env:ProgramFiles(x86)" in line or "$env:PROGRAMFILES(x86)" in line)
        and not line.lstrip().startswith("#")
    ]
    assert not offenders, f"invalid PowerShell env token used at lines: {offenders}"
    assert '[System.Environment]::GetEnvironmentVariable("ProgramFiles(x86)")' in "\n".join(lines)


def test_windows_workflow_pins_tauri_cli():
    """The Tauri CLI must be pinned, not a floating `@^2` range."""
    workflow = REPO_ROOT / ".github/workflows/tauri-windows.yml"
    content = workflow.read_text()
    assert "@tauri-apps/cli@^2" not in content
    assert "@tauri-apps/cli@2." in content


def test_rust_passes_owner_pid_to_sidecar():
    """Tauri exports its own PID so the watchdog can detect a force-kill.

    A frozen onefile sidecar's OS parent is the PyInstaller bootloader, not the
    Tauri app, so watching `os.getppid()` alone cannot see the app disappear.
    """
    main_rs = REPO_ROOT / "src-tauri/src/main.rs"
    content = main_rs.read_text()
    assert content.count('env("PANTHER_PARENT_PID"') == 2, (
        "both the bundled and dev sidecar spawn paths must set PANTHER_PARENT_PID"
    )


def test_rust_kills_whole_sidecar_process_tree():
    """The bundled sidecar must spawn into a process group / job object.

    A PyInstaller onefile executable is a bootloader plus a grandchild hosting
    the interpreter. Without `set_process_group(true)` the plugin's kill path
    falls back to `Child::kill()`, which terminates only the direct child and
    leaves the grandchild orphaned.
    """
    main_rs = REPO_ROOT / "src-tauri/src/main.rs"
    content = main_rs.read_text()
    assert "set_process_group(true)" in content


def test_ci_workflow_runs_full_suite():
    """ci.yml must run the whole tests/ directory, not only selected files.

    Per-file steps were added for timeout isolation; a catch-all step is needed
    so storage/UI/process suites are still executed.
    """
    workflow = REPO_ROOT / ".github/workflows/ci.yml"
    content = workflow.read_text()
    assert 'run: python -m pytest -q -ra' in content
    assert "tests/\n" in content or "tests/ --" in content or "tests/ " in content
    assert "--ignore=tests/test_sidecar_stage0.py" in content


# ---------------------------------------------------------------------------
# Gitignore contract
# ---------------------------------------------------------------------------


def test_gitignore_has_binaries():
    """src-tauri/binaries/ is gitignored."""
    gitignore = REPO_ROOT / ".gitignore"
    content = gitignore.read_text()
    assert "src-tauri/binaries/" in content


def test_gitignore_has_build_sidecar():
    """build/sidecar-* is gitignored."""
    gitignore = REPO_ROOT / ".gitignore"
    content = gitignore.read_text()
    # build/ already covers it, but check for explicit entry
    assert "build/sidecar-" in content or "build/" in content


# ---------------------------------------------------------------------------
# Run if executed directly
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    pytest.main([__file__, "-v"])