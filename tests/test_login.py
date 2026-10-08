import subprocess
from pathlib import Path

from ticketswap_bot import bot


def test_find_browser_prefers_env(monkeypatch):
    monkeypatch.setenv("TICKETSWAP_BOT_BROWSER", "/x/chrome")
    assert bot.find_browser() == "/x/chrome"


def test_find_browser_windows_install(monkeypatch, tmp_path):
    monkeypatch.delenv("TICKETSWAP_BOT_BROWSER", raising=False)
    exe = tmp_path / "Google" / "Chrome" / "Application" / "chrome.exe"
    exe.parent.mkdir(parents=True)
    exe.write_text("")
    monkeypatch.setenv("PROGRAMFILES", str(tmp_path))
    assert bot.find_browser() == str(exe)


def test_login_opens_plain_chrome_with_profile(monkeypatch, tmp_path):
    calls = []

    class FakeProc:
        def __init__(self, args):
            calls.append(args)

        def wait(self):
            return 0

    monkeypatch.setattr(bot, "find_browser", lambda: "/x/chrome")
    monkeypatch.setattr(subprocess, "Popen", FakeProc)
    monkeypatch.setattr("builtins.input", lambda *a: "")
    bot.login(tmp_path / "profile")
    args = calls[0]
    assert args[0] == "/x/chrome"
    assert f"--user-data-dir={tmp_path / 'profile'}" in args
    assert args[-1] == bot.BASE_URL
    assert not any("remote-debugging" in a or "automation" in a for a in args)
    assert Path(tmp_path / "profile").is_dir()
