"""Keep legacy assertions deterministic; locale-specific tests select their own locale."""
import pytest

from mouseshare.i18n import set_language


@pytest.fixture(autouse=True)
def app_message_locale():
    set_language('zh_CN')
    yield
    set_language('zh_CN')
