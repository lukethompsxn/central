"""
Reader implementations.
"""

import json

from . import abc
from .exceptions import LibraryRequiredError
from .utils.compat import ConfigParser, PY2

try:
    import yaml
except:
    yaml = None


__all__ = [
    'add_reader',
    'get_reader',
    'remove_reader',
    'IniReader',
    'JsonReader',
    'YamlReader',
]


MSG_NO_YAML = """
You need to install the library PyYAML to use the YamlReader. See https://pypi.python.org/pypi/PyYAML
"""


__readers = {}


def add_reader(name, reader_cls):
    """
    Add a reader class.
    :param str name: The name of the reader.
    :param reader_cls: The reader class.
    """
    __readers[name] = reader_cls


def get_reader(name):
    """
    Get a reader by name.
    :param str name: The name of the reader.
    :return: The reader class found, otherwise None.
    """
    return __readers.get(name)


def remove_reader(name):
    """
    Remove a reader by name.
    :param str name: The name of the reader.
    :return: The reader class removed, None if not found.
    """
    return __readers.pop(name, None)


class IniReader(abc.Reader):
    """
    A reader for ini content.

    Example usage:

    .. code-block:: python

        from configd.readers import IniReader

        reader = IniReader()

        with open('config.ini') as f:
            data = reader.read(f)

    """

    def read(self, stream):
        """
        Read the given stream and returns it as a dict.
        :param stream: The stream to read the configuration from.
        :return dict: The configuration read from the stream.
        """
        if stream is None:
            raise ValueError('stream cannot be None')

        parser = ConfigParser()

        if PY2:
            parser.readfp(stream)
        else:
            parser.read_file(stream)

        data = {}

        for section in parser.sections():
            data_section = data[section] = {}

            for option in parser.options(section):
                data_section[option] = parser.get(section, option, raw=True)

        return data


class JsonReader(abc.Reader):
    """
    A reader for json content.

    Example usage:

    .. code-block:: python

        from configd.readers import JsonReader

        reader = JsonReader()

        with open('config.json') as f:
            data = reader.read(f)

    """

    def read(self, stream):
        """
        Read the given stream and returns it as a dict.
        :param stream: The stream to read the configuration from.
        :return dict: The configuration read from the stream.
        """
        if stream is None:
            raise ValueError('stream cannot be None')

        return json.load(stream)


class YamlReader(abc.Reader):
    """
    A reader for yaml content.

    The library PyYAML must be installed.

    Example usage:

    .. code-block:: python

        from configd.readers import YamlReader

        reader = YamlReader()

        with open('config.yaml') as f:
            data = reader.read(f)

    """

    def __init__(self):
        if not yaml:
            raise LibraryRequiredError(MSG_NO_YAML)

    def read(self, stream):
        """
        Read the given stream and returns it as a dict.
        :param stream: The stream to read the configuration from.
        :return dict: The configuration read from the stream.
        """
        if stream is None:
            raise ValueError('stream cannot be None')

        return yaml.load(stream)


add_reader('ini', IniReader)
add_reader('json', JsonReader)
add_reader('yaml', YamlReader)