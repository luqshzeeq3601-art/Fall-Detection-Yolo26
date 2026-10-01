"""Smoke test: top-level package imports and exposes a version."""


def test_package_imports() -> None:
    import eldercare

    assert isinstance(eldercare.__version__, str)
    assert eldercare.__version__ != ""
