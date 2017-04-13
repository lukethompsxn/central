"""
Core config implementations.
"""

import codecs
import logging
import os
import sys

from collections import KeysView, ItemsView, ValuesView, Mapping
from .. import abc
from ..compat import text_type, string_types, urlopen
from ..decoders import Decoder
from ..exceptions import ConfigError
from ..interpolation import BashInterpolator, ConfigLookup, ChainLookup, EnvironmentLookup
from ..readers import get_reader
from ..schedulers import FixedIntervalScheduler
from ..structures import IgnoreCaseDict
from ..utils import EventHandler, get_file_ext, make_ignore_case, merge_dict


logger = logging.getLogger(__name__)


NESTED_DELIMITER = '.'


class BaseConfig(abc.Config):
    """
    Base config class for implementing an `abc.Config`.
    """

    def __init__(self):
        self._lookup = ConfigLookup(self)
        self._updated = EventHandler()

    def get(self, key, default=None):
        """
        Get the value for given key if key is in the configuration, otherwise default.
        :param str key: The key to be found.
        :param default: The default value if the key is not found.
        :return: The value found, otherwise default.
        """
        return self.get_value(key, object, default)

    def get_bool(self, key, default=None):
        """
        Get the value for given key as a bool if key is in the configuration, otherwise None.
        :param str key: The key to be found.
        :param default: The default value if the key is not found.
        :return bool: The value found, otherwise default.
        """
        return self.get_value(key, bool, default=default)

    def get_dict(self, key, default=None):
        """
        Get the value for given key as a dict if key is in the configuration, otherwise None.
        :param str key: The key to be found.
        :param default: The default value if the key is not found.
        :return dict: The value found, otherwise default.
        """
        return self.get_value(key, dict, default=default)

    def get_int(self, key, default=None):
        """
        Get the value for given key as an int if key is in the configuration, otherwise None.
        :param str key: The key to be found.
        :param default: The default value if the key is not found.
        :return int: The value found, otherwise default.
        """
        return self.get_value(key, int, default=default)

    def get_float(self, key, default=None):
        """
        Get the value for given key as a float if key is in the configuration, otherwise None.
        :param str key: The key to be found.
        :param default: The default value if the key is not found.
        :return float: The value found, otherwise default.
        """
        return self.get_value(key, float, default=default)

    def get_list(self, key, default=None):
        """
        Get the value for given key as a list if key is in the configuration, otherwise None.
        :param str key: The key to be found.
        :param default: The default value if the key is not found.
        :return list: The value found, otherwise default.
        """
        return self.get_value(key, list, default=default)

    def get_str(self, key, default=None):
        """
        Get the value for given key as a str if key is in the configuration, otherwise None.
        :param str key: The key to be found.
        :param default: The default value if the key is not found.
        :return str: The value found, otherwise default.
        """
        return self.get_value(key, text_type, default=default)

    def keys(self):
        """
        Get all the keys of the configuration.
        :return tuple: The keys of the configuration.
        """
        return KeysView(self)

    def items(self):
        """
        Get all the items of the configuration (key/value pairs).
        :return tuple: The items of the configuration.
        """
        return ItemsView(self)

    def values(self):
        """
        Get all the values of the configuration.
        :return tuple: The values of the configuration.
        """
        return ValuesView(self)

    @property
    def lookup(self):
        """
        Get the lookup object used for interpolation.
        :return StrLookup: The lookup object.
        """
        return self._lookup

    @lookup.setter
    def lookup(self, value):
        """
        Set the lookup object used for interpolation.
        :param StrLookup value: The lookup object.
        """
        if value is None:
            self._lookup = ConfigLookup(self)
        elif isinstance(value, abc.StrLookup):
            self._lookup = value
        else:
            raise TypeError('lookup must be an abc.StrLookup')

        self._lookup_changed(self._lookup)

    @property
    def updated(self):
        """
        Get the updated event handler.
        :return EventHandler: The event handler.
        """
        return self._updated

    def on_updated(self, func):
        """
        Add a new callback for updated event.
        It can also be used as decorator.

        Example usage:

        .. code-block:: python

            from central.config import MemoryConfig

            config = MemoryConfig()

            @config.on_updated
            def config_updated():
                pass

        :param func: The callback.
        """
        self.updated.add(func)

    def prefixed(self, prefix):
        """
        Get a subset of the configuration prefixed by a key.

        Example usage:

        .. code-block:: python

            from central.config import MemoryConfig

            config = MemoryConfig().prefixed('database')

            host = config.get('host')

        :param str prefix: The prefix to prepend to the keys.
        :return abc.Config: The subset of the configuration prefixed by a key.
        """
        return PrefixedConfig(prefix, self)

    def reload_every(self, interval):
        """
        Get a reload configuration to reload the
        current configuration every interval given.
        :param Number interval: The interval in seconds between loads.
        :return ReloadConfig: The reload config object.
        """
        return ReloadConfig(self, FixedIntervalScheduler(interval))

    def _lookup_changed(self, lookup):
        """
        Called when the lookup property is changed.
        :param lookup: The new lookup object.
        """
        pass

    def __contains__(self, key):
        """
        Get true if key is in the configuration, otherwise false.
        :param str key: The key to be checked.
        :return bool: true if key is in the configuration, false otherwise.
        """
        return self.get_raw(key) is not None

    def __getitem__(self, key):
        """
        Get the value if key is in the configuration, otherwise KeyError is raised.
        :param str key: The key to be found.
        :return: The value found.
        """
        value = self.get_value(key, object)

        if value is None:
            raise KeyError(key)

        return value


class BaseDataConfig(BaseConfig):
    """
    Base config class that holds keys.
    """

    def __init__(self):
        super(BaseDataConfig, self).__init__()
        self._data = IgnoreCaseDict()
        self._decoder = Decoder.instance()
        self._interpolator = BashInterpolator()

    @property
    def decoder(self):
        """
        Get the decoder.
        :return abc.Decoder: The decoder.
        """
        return self._decoder

    @decoder.setter
    def decoder(self, value):
        """
        Set the decoder.
        :param abc.Decoder value: The decoder.
        """
        if not isinstance(value, abc.Decoder):
            raise TypeError('decoder must be an abc.Decoder')

        self._decoder = value

    @property
    def interpolator(self):
        """
        Get the interpolator.
        :return abc.StrInterpolator: The interpolator.
        """
        return self._interpolator

    @interpolator.setter
    def interpolator(self, value):
        """
        Set the interpolator.
        :param abc.StrInterpolator value: The interpolator.
        """
        if not isinstance(value, abc.StrInterpolator):
            raise TypeError('interpolator must be an abc.StrInterpolator')

        self._interpolator = value

    def get_raw(self, key):
        """
        Get the raw value for given key if key is in the configuration, otherwise None.
        Find the given key considering the nested delimiter as nested key.
        :param str key: The key to be found.
        :return: The value found, otherwise None.
        """
        if key is None:
            raise TypeError('key cannot be None')

        value = self._data.get(key)

        if value is not None:
            return value

        paths = key.split(NESTED_DELIMITER)

        if key == paths[0]:
            return None

        value = self._data.get(paths[0])

        for i in range(1, len(paths)):
            if value is None:
                break

            if not isinstance(value, Mapping):
                value = None
                break

            value = value.get(paths[i])

        return value

    def get_value(self, key, type, default=None):
        """
        Get the value for given key as the specified type if key is in the configuration, otherwise default.
        It can access a nested field by passing a . delimited path of keys and
        the interpolator is used to resolve variables.
        :param str key: The key to be found.
        :param type: The data type to convert the value to.
        :param default: The default value if the key is not found.
        :return: The value found, otherwise default.
        """
        if key is None:
            raise TypeError('key cannot be None')

        if type is None:
            raise TypeError('type cannot be None')

        value = self.get_raw(key)

        if value is None:
            if callable(default):
                return default()

            return default

        if isinstance(value, string_types):
            value = self._interpolator.resolve(value, self._lookup)

        if type is object:
            return value

        return self._decoder.decode(value, type)

    def __iter__(self):
        """
        Get a new iterator object that can iterate over the keys of the configuration.
        :return: The iterator.
        """
        return iter(self._data)

    def __len__(self):
        """
        Get the number of keys.
        :return int: The number of keys.
        """
        return len(self._data)


class ChainConfig(BaseConfig):
    """
    Combine multiple `abc.Config` in a fallback chain.

    The chain does not merge the configurations but instead
    treats them as overrides so that a key existing in a configuration supersedes
    the same key in the previous configuration.

    The chain works in reverse order, that means the last configuration
    in the chain overrides the previous one.

    Example usage:

    .. code-block:: python

        from central.config import CommandLineConfig, EnvironmentConfig, FallbackConfig

        config = ChainConfig(EnvironmentConfig(), CommandLineConfig())
        config.load()

        value = config.get('key1')

    :param configs: The list of `abc.Config`.
    """
    def __init__(self, *configs):
        super(ChainConfig, self).__init__()

        for config in configs:
            if not isinstance(config, abc.Config):
                raise TypeError('config must be an abc.Config')

            config.lookup = self._lookup
            config.updated.add(self._config_updated)

        self._configs = configs
        self._keys_cached = None

    @property
    def configs(self):
        """
        Get the sub configurations.
        :return tuple: The list of `abc.Config`.
        """
        return self._configs

    def get_raw(self, key):
        """
        Get the raw value for given key if key is in the configuration, otherwise None.
        It goes through every child to find the given key.
        :param str key: The key to be found.
        :return: The value found, otherwise None.
        """
        for config in reversed(self._configs):
            value = config.get_raw(key)
            if value is not None:
                return value

        return None

    def get_value(self, key, type, default=None):
        """
        Get the value for given key as the specified type if key is in the configuration, otherwise default.
        It goes through every child to find the given key.
        :param str key: The key to be found.
        :param type: The data type to convert the value to.
        :param default: The default value if the key is not found.
        :return: The value found, otherwise default.
        """
        for config in reversed(self._configs):
            value = config.get_value(key, type)
            if value is not None:
                return value

        if callable(default):
            return default()

        return default

    def load(self):
        """
        Load the sub configurations.

        This method does not trigger the updated event.
        """
        for config in self._configs:
            config.load()

    def _config_updated(self):
        """
        Called by updated event from the children.
        It is not intended to be called directly.
        """
        # reset the cache because the children's
        # configuration has been changed.
        self._keys_cached = None

        self.updated()

    def _lookup_changed(self, lookup):
        """
        Set the new lookup to the children.
        :param lookup: The new lookup object.
        """
        for config in self._configs:
            config.lookup = lookup

    def _build_cached_keys(self):
        """
        Build the cache for the children's keys.
        :return IgnoreCaseDict: The dict containing the keys. 
        """
        keys = IgnoreCaseDict()

        for config in self._configs:
            for key in config.keys():
                keys[key] = True

        return keys

    def _get_cached_keys(self):
        """
        Get the cache for the children's keys.
        :return IgnoreCaseDict: The dict containing the keys. 
        """
        if self._keys_cached is None:
            self._keys_cached = self._build_cached_keys()
        return self._keys_cached

    def __iter__(self):
        """
        Get a new iterator object that can iterate over the keys of the configuration.
        :return: The iterator.
        """
        return iter(self._get_cached_keys())

    def __len__(self):
        """
        Get the number of keys.
        :return int: The number of keys.
        """
        return len(self._get_cached_keys())


class CommandLineConfig(BaseDataConfig):
    """
    A command line based on `BaseDataConfig`.

    Example usage:

    .. code-block:: python

        from central.config import CommandLineConfig

        config = CommandLineConfig()
        config.load()

        value = config.get('key1')

    """

    def load(self):
        """
        Load the configuration from the command line args.

        This method does not trigger the updated event.
        """
        data = IgnoreCaseDict()

        # the first item is the file name.
        args = sys.argv[1:]

        iterator = iter(args)

        while True:
            try:
                current_arg = next(iterator)
            except StopIteration:
                break

            key_start_index = 0

            if current_arg.startswith('--'):
                key_start_index = 2

            elif current_arg.startswith('-'):
                key_start_index = 1

            separator = current_arg.find('=')

            if separator == -1:
                if key_start_index == 0:
                    raise ConfigError('Unrecognized argument %s format' % current_arg)

                key = current_arg[key_start_index:]

                try:
                    value = next(iterator)
                except StopIteration:
                    raise ConfigError('Value for argument %s is missing' % key)
            else:
                key = current_arg[key_start_index:separator].strip()

                if not key:
                    raise ConfigError('Unrecognized argument %s format' % current_arg)

                value = current_arg[separator + 1:].strip()

            data[key] = value

        self._data = data


class EnvironmentConfig(BaseDataConfig):
    """
    An environment variable configuration based on `BaseDataConfig`.

    Example usage:

    .. code-block:: python

        from central.config import EnvironmentConfig

        config = EnvironmentConfig()
        config.load()

        value = config.get('key1')

    """

    def load(self):
        """
        Load the configuration from environment variables.

        This method does not trigger the updated event.
        """
        self._data = IgnoreCaseDict(os.environ)


class FileConfig(BaseDataConfig):
    """
    A file configuration based on `BaseDataConfig`.

    Example usage:

    .. code-block:: python

        from central.config import FileConfig

        config = FileConfig('config.json')
        config.load()

        value = config.get('key')

    :param str filename: The filename to be read.
    :param abc.Reader reader: The reader used to read the file content as a dict,
        if None a reader based on the filename is going to be used.
    """

    def __init__(self, filename, reader=None):
        super(FileConfig, self).__init__()
        if not isinstance(filename, string_types):
            raise TypeError('filename must be a str')

        if reader is not None and not isinstance(reader, abc.Reader):
            raise TypeError('reader must be an abc.Reader')

        self._filename = filename
        self._reader = reader

    @property
    def filename(self):
        """
        Get the filename.
        :return str: The filename.
        """
        return self._filename

    @property
    def reader(self):
        """
        Get the reader.
        :return abc.Reader: The reader.
        """
        return self._reader

    def load(self):
        """
        Load the configuration from a file.
        Recursively load any filename referenced by an @next property in the configuration.

        This method does not trigger the updated event.
        """
        to_merge = []
        filename = self.filename
        paths = None

        while filename:
            file = self._find_file(filename, paths)

            if file is None:
                raise ConfigError('File %s not found' % filename)

            data = self._read_file(file)

            if not isinstance(data, IgnoreCaseDict):
                raise ConfigError('reader must return an IgnoreCaseDict object')

            next_filename = data.pop('@next', None)

            if next_filename is not None:
                if not isinstance(next_filename, string_types):
                    raise ConfigError('@next must be a str')

                # the next filename is relative to the previous filename.
                # the path from the filename is used to search
                # for the next filename.
                base_path = os.path.dirname(filename)
                if base_path:
                    paths = [base_path]

            filename = next_filename

            to_merge.append(data)

        data = to_merge[0]

        if len(to_merge) > 1:
            merge_dict(data, *to_merge[1:])

        self._data = data

    def _get_reader(self, filename):
        """
        Get an appropriated reader based on the filename,
        if not found an `ConfigError` is raised.
        :param str filename: The filename used to guess the appropriated reader.
        :return abc.Reader: A reader.
        """
        extension = get_file_ext(filename)

        if not extension:
            raise ConfigError('File %s is not supported' % filename)

        reader_cls = get_reader(extension)

        if reader_cls is None:
            raise ConfigError('File %s is not supported' % filename)

        return reader_cls()

    def _find_file(self, filename, paths=None):
        """
        Search all the given paths for the given config file.
        Returns the first path that exists and is a config file.
        :param str filename: The filename to be found.
        :param list paths: The paths to be searched.
        :return: The first file found, otherwise None.
        """
        if paths:
            filenames = [os.path.join(path, filename) for path in paths]
        else:
            filenames = [filename]

        # create a chain lookup to resolve any variable left
        # using environment variable.
        lookup = ChainLookup(EnvironmentLookup(), self._lookup)

        for filename in filenames:
            # resolve variables.
            filename = self._interpolator.resolve(filename, lookup)

            if os.path.exists(filename):
                return filename

        return None

    def _read_file(self, filename):
        """
        Read the content of the file.
        :param str filename: The filename to be read.
        :return IgnoreCaseDict: The data read from the file.
        """
        reader = self._reader or self._get_reader(filename)

        with self._open_file(filename) as stream:
            text_reader_cls = codecs.getreader('utf-8')

            with text_reader_cls(stream) as text_reader:
                return reader.read(text_reader)

    def _open_file(self, filename):
        """
        Open a stream for the given filename.
        :param str filename: The filename to be read.
        :return: The stream to read the file content.
        """
        return open(filename, mode='rb')


class MemoryConfig(BaseDataConfig):
    """
    In-memory implementation of `BaseDataConfig`.

    Example usage:

    .. code-block:: python

        from central.config import MemoryConfig

        config = MemoryConfig(data={'key': 'value'})

        value = config.get('key')

        config.set('other key', 'other value')

        value = config.get('other key')

    :param dict data: The initial data.
    """

    def __init__(self, data=None):
        super(MemoryConfig, self).__init__()

        if data is not None:
            if not isinstance(data, Mapping):
                raise TypeError('data must be a dict')

            self._data = make_ignore_case(data)

    def set(self, key, value):
        """
        Set a value for the given key.
        The updated event is triggered.
        :param str key: The key.
        :param value: The value.
        """
        if key is None:
            raise TypeError('key cannot be None')

        if isinstance(value, Mapping):
            value = make_ignore_case(value)

        self._data[key] = value
        self.updated()

    def load(self):
        """
        Do nothing
        """


class MergeConfig(BaseDataConfig):
    """
    Merge multiple `abc.Config`, in case of key collision last-match wins.

    Example usage:

    .. code-block:: python

        from central.config import FileConfig, MergeConfig

        config = MergeConfig(FileConfig('base.json'), FileConfig('dev.json'))
        config.load()

        value = config.get('key1')

    :param configs: The list of `abc.Config`.
    """
    def __init__(self, *configs):
        super(MergeConfig, self).__init__()

        if not isinstance(configs, (tuple, list)):
            raise TypeError('configs must be a list or tuple')

        for config in configs:
            if not isinstance(config, abc.Config):
                raise TypeError('config must be an abc.Config')

            config.lookup = self._lookup
            config.updated.add(self._config_updated)

        self._configs = configs
        self._raw_configs = [self._RawConfig(config) for config in self._configs]

    @property
    def configs(self):
        """
        Get the sub configurations.
        :return tuple: The list of `abc.Config`.
        """
        return self._configs

    def load(self):
        """
        Load the sub configurations and merge them
        into a single configuration.

        This method does not trigger the updated event.
        """
        for config in self._configs:
            config.load()

        data = IgnoreCaseDict()

        if len(self._configs) == 0:
            return data

        merge_dict(data, *self._raw_configs)

        self._data = data

    def _config_updated(self):
        """
        Called by updated event from the children.
        It is not intended to be called directly.
        """
        self.updated()

    class _RawConfig(Mapping):
        """
        Internal class used to merge a `abc.Config`.

        When we merge configs we want to merge the raw value
        rather than decoded and interpolated value.
        """
        def __init__(self, config):
            self._config = config

        def get(self, key, default=None):
            value = self._config.get_raw(key)
            if value is None:
                return default
            return value

        def __contains__(self, key):
            return key in self._config

        def __getitem__(self, key):
            value = self._config.get_raw(key)
            if value is None:
                raise KeyError(key)
            return value

        def __iter__(self):
            return iter(self._config)

        def __len__(self):
            return len(self._config)


class PrefixedConfig(BaseConfig):
    """
    A config implementation to view into another Config
    for keys starting with a specified prefix.

    Example usage:

    .. code-block:: python

        from central.config import PrefixedConfig, MemoryConfig

        config = MemoryConfig(data={'production.timeout': 10})

        prefixed = PrefixedConfig('production', config)

        value = prefixed.get('timeout')

    :param str prefix: The prefix to prepend to the keys.
    :param abc.Config config: The config to load the keys from.
    """
    def __init__(self, prefix, config):
        super(PrefixedConfig, self).__init__()

        if not isinstance(prefix, string_types):
            raise TypeError('prefix must be a str')

        if not isinstance(config, abc.Config):
            raise TypeError('config must be an abc.Config')

        self._prefix = prefix.rstrip(NESTED_DELIMITER)
        self._prefix_delimited = prefix if prefix.endswith(NESTED_DELIMITER) else prefix + NESTED_DELIMITER
        self._config = config
        self._config.lookup = self.lookup

    @property
    def config(self):
        """
        Get the config.
        :return abc.Config: The config.
        """
        return self._config

    @property
    def prefix(self):
        """
        Get the prefix.
        :return str: The prefix.
        """
        return self._prefix

    def get_raw(self, key):
        """
        Get the raw value for given key if key is in the configuration, otherwise None.
        :param str key: The key to be found.
        :return: The value found, otherwise default.
        """
        if key is None:
            raise TypeError('key cannot be None')

        try:
            key = self._prefix_delimited + key
        except TypeError:
            raise TypeError('key must be a str')

        return self._config.get_raw(key)

    def get_value(self, key, type, default=None):
        """
        Get the value for given key as the specified type if key is in the configuration, otherwise default.
        :param str key: The key to be found.
        :param type: The data type to convert the value to.
        :param default: The default value if the key is not found.
        :return: The value found, otherwise default.
        """
        if key is None:
            raise TypeError('key cannot be None')

        try:
            key = self._prefix_delimited + key
        except TypeError:
            raise TypeError('key must be a str')

        return self._config.get_value(key, type, default=default)

    def load(self):
        """
        Load the child configuration.

        This method does not trigger the updated event.
        """
        self._config.load()

    def _lookup_changed(self, lookup):
        """
        Set the new lookup to the child.
        :param lookup: The new lookup object.
        """
        self._config.lookup = lookup

    def __iter__(self):
        """
        Get a new iterator object that can iterate over the keys of the configuration.
        :return: The iterator.
        """
        keys = set()

        for key in self._config:
            if key == self._prefix:
                value = self._config.get(key)
                if isinstance(value, Mapping):
                    keys.update(value.keys())

            elif key.startswith(self._prefix_delimited):
                keys.update((key[len(self._prefix_delimited):],))

        return iter(keys)

    def __len__(self):
        """
        Get the number of keys.
        :return int: The number of keys.
        """
        length = 0

        for key in self._config:
            if key == self._prefix:
                value = self._config.get(key)
                if isinstance(value, Mapping):
                    length += len(value)

            elif key.startswith(self._prefix_delimited):
                length += 1

        return length


class ReloadConfig(BaseConfig):
    """
    A reload config that loads the configuration from its child
    from time to time, it is scheduled by a scheduler.

    Example usage:

    .. code-block:: python

        from central.config import ReloadConfig, FileConfig
        from central.schedulers import FixedIntervalScheduler

        config = ReloadConfig(FileConfig('config.json'), FixedIntervalScheduler())
        config.load()

        value = config.get('key')

    :param abc.Config config: The config to be reloaded from time to time.
    :param abc.Scheduler scheduler: The scheduler used to reload the configuration from the child.
    """
    def __init__(self, config, scheduler):
        super(ReloadConfig, self).__init__()

        if not isinstance(config, abc.Config):
            raise TypeError('config must be an abc.Config')

        if not isinstance(scheduler, abc.Scheduler):
            raise TypeError('scheduler must be an abc.Scheduler')

        self._config = config
        self._config.lookup = self.lookup
        self._scheduler = scheduler
        self._loaded = False

    @property
    def config(self):
        """
        Get the config.
        :return abc.Config: The config.
        """
        return self._config

    @property
    def scheduler(self):
        """
        Get the scheduler.
        :return abc.Scheduler: The scheduler.
        """
        return self._scheduler

    def get_raw(self, key):
        """
        Get the raw value for given key if key is in the configuration, otherwise None.
        :param str key: The key to be found.
        :return: The value found, otherwise default.
        """
        return self._config.get_raw(key)

    def get_value(self, key, type, default=None):
        """
        Get the value for given key as the specified type if key is in the configuration, otherwise default.
        :param str key: The key to be found.
        :param type: The data type to convert the value to.
        :param default: The default value if the key is not found.
        :return: The value found, otherwise default.
        """
        return self._config.get_value(key, type, default=default)

    def load(self):
        """
        Load the child configuration and start the scheduler
        to reload the child configuration from time to time.

        This method does not trigger the updated event.
        """
        self._config.load()

        if not self._loaded:
            self._scheduler.schedule(self._reload)
            self._loaded = True

    def _reload(self):
        """
        Reload the child configuration and trigger the updated event.
        It is only intended to be called by the scheduler.
        """
        try:
            self._config.load()
        except:
            logger.warning('Unable to load config ' + text_type(self._config), exc_info=True)

        try:
            self.updated()
        except:
            logger.warning('Error calling updated event from ' + str(self), exc_info=True)

    def _lookup_changed(self, lookup):
        """
        Set the new lookup to the child.
        :param lookup: The new lookup object.
        """
        self._config.lookup = lookup

    def __iter__(self):
        """
        Get a new iterator object that can iterate over the keys of the configuration.
        :return: The iterator.
        """
        return iter(self._config)

    def __len__(self):
        """
        Get the number of keys.
        :return int: The number of keys.
        """
        return len(self._config)


class UrlConfig(BaseDataConfig):
    """
    A url configuration based on `BaseDataConfig`.

    Example usage:

    .. code-block:: python

        from central.config import UrlConfig

        config = UrlConfig('http://date.jsontest.com/')
        config.load()

        value = config.get('time')

    :param str url: The url to be read.
    :param abc.Reader reader: The reader used to read the response from url as a dict,
        if None a reader based on the content type of the response is going to be used.
    """
    def __init__(self, url, reader=None):
        super(UrlConfig, self).__init__()

        if not isinstance(url, string_types):
            raise TypeError('url must be a str')

        if reader is not None and not isinstance(reader, abc.Reader):
            raise TypeError('reader must be an abc.Reader')

        self._url = url
        self._reader = reader

    @property
    def url(self):
        """
        Get the url.
        :return str: The url.
        """
        return self._url

    @property
    def reader(self):
        """
        Get the reader.
        :return abc.Reader: The reader.
        """
        return self._reader

    def load(self):
        """
        Load the configuration from a url.
        Recursively load any url referenced by an @next property in the response.

        This method does not trigger the updated event.
        """
        to_merge = []
        url = self.url

        # create a chain lookup to resolve any variable left
        # using environment variable.
        lookup = ChainLookup(EnvironmentLookup(), self._lookup)

        while url:
            # resolve variables.
            url = self._interpolator.resolve(url, lookup)

            content_type, stream = self._open_url(url)

            try:
                reader = self._reader or self._get_reader(url, content_type)

                encoding = self._get_encoding(content_type)

                text_reader_cls = codecs.getreader(encoding)

                with text_reader_cls(stream) as text_reader:
                    data = reader.read(text_reader)
            finally:
                stream.close()

            url = data.pop('@next', None)

            to_merge.append(data)

            if url and not isinstance(url, string_types):
                raise ConfigError('@next must be a str')

        data = to_merge[0]

        if not isinstance(data, IgnoreCaseDict):
            raise ConfigError('reader must return an IgnoreCaseDict object')

        if len(to_merge) > 1:
            merge_dict(data, *to_merge[1:])

        self._data = data

    def _get_reader(self, url, content_type):
        """
        Get an appropriated reader based on the url and the content type,
        if not found an `ConfigError` is raised.
        :param str url: The url used to guess the appropriated reader.
        :param str content_type: The content type used to guess the appropriated reader.
        :return abc.Reader: A reader.
        """
        names = []

        if content_type:
            # it handles those formats for content type.
            # text/vnd.yaml
            # text/yaml
            # text/x-yaml

            if ';' in content_type:
                content_type = content_type.split(';')[0]

            if '.' in content_type:
                names.append(content_type.split('.')[-1])
            elif '-' in content_type:
                names.append(content_type.split('-')[-1])
            elif '/' in content_type:
                names.append(content_type.split('/')[-1])

        # it handles a url with file extension.
        # http://example.com/config.json
        path = url.strip().rstrip('/')

        i = path.rfind('/')

        if i > 10:  # > http:// https://
            path = path[i:]

            if '.' in path:
                names.append(path.split('.')[-1])

        for name in names:
            reader_cls = get_reader(name)
            if reader_cls:
                return reader_cls()

        raise ConfigError('Response from %s provided content type %s which is not supported' % (url, content_type))

    def _get_encoding(self, content_type, default='utf-8'):
        """
        Get the encoding from the given content type.
        :param str content_type: The content type from the response.
        :param str default: The default content type.
        :return str: The encoding.
        """
        if not content_type:
            return default

        # e.g: application/json;charset=iso-8859-x

        pairs = content_type.split(';')

        # skip the mime type
        for pair in pairs[1:]:
            kv = pair.split('=')
            if len(kv) != 2:
                continue

            key = kv[0].strip()
            value = kv[1].strip()

            if key == 'charset' and value:
                return value

        return default

    def _open_url(self, url):
        """
        Open the given url and returns its content type and the stream to read it.
        :param url: The url to be opened.
        :return tuple: The content type and the stream to read from.
        """
        response = urlopen(url)
        content_type = response.headers.get('content-type')
        return content_type, response
