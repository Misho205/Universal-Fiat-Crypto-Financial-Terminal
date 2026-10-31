import os
import tempfile

from modal_backend import config


def test_live_defaults_off(monkeypatch):
  monkeypatch.delenv("LIVE_MODE", raising=False)
  monkeypatch.delenv("LIVE_APPROVAL_FILE", raising=False)
  import importlib
  importlib.reload(config)
  assert config.live_mode_status() == "OFF"
  assert config.live_approved() is False
  config.assert_sandbox()  # must not raise in sandbox


def test_live_requested_without_approval_is_blocked(monkeypatch, tmp_path):
  monkeypatch.setenv("LIVE_MODE", "true")
  monkeypatch.setenv("LIVE_APPROVAL_FILE", str(tmp_path / "missing.json"))
  import importlib
  importlib.reload(config)
  assert config.live_mode_status() == "BLOCKED"
  try:
    config.assert_sandbox()
    raise AssertionError("should have raised")
  except RuntimeError as e:
    assert "LIVE_APPROVAL_FILE" in str(e)
  finally:
    monkeypatch.delenv("LIVE_MODE", raising=False)
    monkeypatch.delenv("LIVE_APPROVAL_FILE", raising=False)
    importlib.reload(config)


def test_live_approved_with_file(monkeypatch, tmp_path):
  f = tmp_path / "approval.json"
  f.write_text('{"approved": true, "by": "ops"}')
  monkeypatch.setenv("LIVE_MODE", "true")
  monkeypatch.setenv("LIVE_APPROVAL_FILE", str(f))
  import importlib
  importlib.reload(config)
  assert config.live_approved() is True
  assert config.live_mode_status() == "ON-APPROVED"
  config.assert_sandbox()  # approved live does not trip the sandbox guard
  monkeypatch.delenv("LIVE_MODE", raising=False)
  monkeypatch.delenv("LIVE_APPROVAL_FILE", raising=False)
  importlib.reload(config)
