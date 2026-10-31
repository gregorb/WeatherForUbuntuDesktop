"""Where to find the script under test.

Default is the copy in this repository, so the tests exercise what you are
editing. Point WX_SCRIPT at ~/.local/bin/wx-wallpaper to test what is actually
installed instead.
"""
import importlib.machinery
import importlib.util
import os
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent / "wx-wallpaper.py"
INSTALLED = Path.home() / ".local/bin/wx-wallpaper"


def script_path():
    if os.environ.get("WX_SCRIPT"):
        return Path(os.environ["WX_SCRIPT"])
    return REPO if REPO.exists() else INSTALLED


def load(name="wx"):
    path = script_path()
    spec = importlib.util.spec_from_loader(
        name, importlib.machinery.SourceFileLoader(name, str(path)))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
