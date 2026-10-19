import os

from ponto_eletronico.path_utils import configured_path


def test_configured_path_uses_default_for_empty_value(tmp_path):
    assert configured_path("  ", tmp_path) == tmp_path


def test_configured_path_translates_wsl_mount_to_windows_drive():
    if os.name == "nt":
        assert str(configured_path("/mnt/c/Users/Leticia/data", ".")) == (
            "C:\\Users\\Leticia\\data"
        )


def test_configured_path_preserves_regular_windows_path(tmp_path):
    assert configured_path(str(tmp_path), ".") == tmp_path
