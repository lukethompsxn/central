"""
S3 config implementation.
"""

import codecs
import io

from .core import BaseDataConfig
from .. import abc
from ..compat import string_types
from ..exceptions import ConfigError, LibraryRequiredError
from ..readers import get_reader
from ..utils import get_file_ext, Transformer

try:
    import boto3
except:
    boto3 = None


__all__ = [
    'S3Config',
]


MSG_NO_BOTO3 = """
You need to install the boto3 library to use the S3Config. See https://boto3.readthedocs.io
"""


class S3Config(BaseDataConfig):
    """
    A S3 configuration based on `BaseDataConfig`.

    The library boto3 must be installed.

    Example usage:

    .. code-block:: python

        import boto3

        from configd.config.s3 import S3Config

        s3 = boto3.resource('s3')

        config = S3Config(s3, 'bucket name', 'config.json')
        config.load()

        value = config.get('key')

    :param client: The boto S3 resource.
    :param str bucket_name: The S3 bucket name.
    :param str filename: The file name to be read.
    :param abc.Reader reader: The reader used to read the file content as a dict,
        if None a reader based on file name is going to be used.
    """

    def __init__(self, client, bucket_name, filename, reader=None):
        if boto3 is None:
            raise LibraryRequiredError('boto3', 'https://pypi.python.org/pypi/boto3')

        super(S3Config, self).__init__()

        if client is None:
            raise TypeError('client cannot be None')

        if bucket_name is None or not isinstance(bucket_name, string_types):
            raise TypeError('bucket_name must be a str')

        if filename is None or not isinstance(filename, string_types):
            raise TypeError('filename must be a str')

        if reader is not None and not isinstance(reader, abc.Reader):
            raise TypeError('reader must be an abc.Reader')

        self._client = client
        self._bucket_name = bucket_name
        self._filename = filename
        self._reader = reader
        self._transformer = Transformer()

    @property
    def bucket_name(self):
        """
        Get the bucket name.
        :return str: The bucket name.
        """
        return self._bucket_name

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
        Load the file from AWS S3.
        """
        data = {}

        self._read(self._filename, data)

        self._data = data

    def _read(self, filename, data):
        """
        Read a given filename from S3 and merge the content with the given data.
        Recursively load any url referenced by an @next property in the response.

        :param str filename: The filename to be read.
        :param dict data: The data to merged on.
        """
        reader = self._reader or self._get_reader(filename)

        with self._read_file(filename) as stream:
            text_reader_cls = codecs.getreader('utf-8')

            with text_reader_cls(stream) as text_reader:
                new_data = reader.read(text_reader)

        next_filename = new_data.pop('@next', None)

        self._transformer.transform(data, new_data)

        if next_filename:
            if not isinstance(next_filename, string_types):
                raise ConfigError('@next must be a str')

            next_filename = self._interpolator.resolve(next_filename, self.lookup)
            self._read(next_filename, data)

    def _read_file(self, filename):
        """
        Read the given file from AWS S3.
        :param str filename: The filename to be read.
        :return: The stream to read the file content.
        """
        obj = self._client.Object(self._bucket_name, filename)

        stream = io.BytesIO()

        obj.download_fileobj(stream)

        # move the pointer to the beginning of the stream.
        stream.seek(0, 0)

        return stream

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
