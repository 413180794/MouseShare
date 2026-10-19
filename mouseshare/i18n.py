"""App-owned messages and locale selection. User content never enters the catalog."""
import json
from pathlib import Path

from PySide6.QtCore import QLocale

_catalog = json.loads((Path(__file__).parent / 'locales/en.json').read_text(encoding='utf-8'))
_language = 'zh_CN'
_preference = 'system'


def resolve_language(preference='system', system_locale=None):
    if preference in ('zh_CN', 'en'):
        return preference
    locale = system_locale if system_locale is not None else QLocale.system().name()
    return 'zh_CN' if locale.lower().replace('-', '_').startswith('zh') else 'en'


def language():
    return _language


def set_language(preference='system', system_locale=None):
    global _language, _preference
    _preference = preference if preference in ('system', 'zh_CN', 'en') else 'system'
    _language = resolve_language(_preference, system_locale)
    QLocale.setDefault(QLocale(_language))


def render(value):
    return value.render() if isinstance(value, Message) else value


class Message(str):
    """Retain the source and parameters for open widgets when the locale changes."""
    def __new__(cls, source, values=None):
        values = values or {}
        text = _catalog.get(source, source) if _language == 'en' else source
        obj = super().__new__(cls, text.format(**{k: render(v) for k, v in values.items()}) if values else text)
        obj.source, obj.values = source, values
        return obj

    def render(self):
        return str(Message(self.source, self.values))

    def __add__(self, other):
        return Message('{left}{right}', dict(left=self, right=other))

    def __radd__(self, other):
        return Message('{left}{right}', dict(left=other, right=self))


def tr(source, **values):
    return Message(source, values)


def status_message(value):
    """Recover catalog-owned transfer statuses from older local history records."""
    if isinstance(value, Message):
        return value
    if value in _catalog:
        return tr(value)
    source = next((source for source, text in _catalog.items() if text == value), None)
    return tr(source) if source else value
