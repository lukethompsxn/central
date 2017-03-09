"""
Utility module
"""

import os


def get_file_ext(filename):
    """
    Get the extension from the given filename.
    :param str filename: The filename.
    :return str: The extension.
    """
    return os.path.splitext(filename)[1].strip('.')


def merge_properties(dst, src):
    """
    Merge the given src dict into dst dict.
    """
    if len(dst) == 0:
        dst.update(src)
        return

    for key in src.keys():
        dst_value = dst.get(key)
        src_value = src.get(key)

        if src_value is None or dst_value is None:
            dst[key] = src_value

        elif type(src_value) != type(dst_value):
            continue

        elif type(dst_value) == dict:
            merge_properties(dst_value, src_value)

        else:
            dst[key] = src_value


class EventHandler(object):
    """
    A simple event handling class, which manages callbacks to be executed.

    :param after_add_func: The func called after adding a new callback.
    :param after_remove_func: The func called after removing a callback.
    """
    def __init__(self, after_add_func=None, after_remove_func=None):
        if after_add_func and not callable(after_add_func):
            raise TypeError('after_add_func must be callable object')

        if after_remove_func and not callable(after_remove_func):
            raise TypeError('after_remove_func must be callable object')

        self._after_add_func = after_add_func
        self._after_remove_func = after_remove_func
        self._callbacks = []

    def __call__(self, *args):
        """
        Execute all callbacks.

        Execute all connected callbacks in the order of addition,
        passing the sender of the EventHandler as first argument and the
        optional args as second, third, ... argument to them.
        """
        return [callback(*args) for callback in self._callbacks]

    def __len__(self):
        """
        Get the amount of callbacks connected to the EventHandler.
        """
        return len(self._callbacks)

    def __getitem__(self, index):
        """
        Get a callback by index.
        :param int index: The index of the callback.
        :return: The callback found.
        """
        return self._callbacks[index]

    def add(self, callback):
        """
        Add a callback to the EventHandler.
        :param callback: The callback to be added.
        """
        if not callable(callback):
            raise TypeError("callback must be callable")

        self._callbacks.append(callback)

        if self._after_add_func:
            self._after_add_func()

    def remove(self, callback):
        """
        Remove a callback from the EventHandler.
        :param callback: The callback to be added.
        """
        if not callable(callback):
            raise TypeError("callback must be callable")

        self._callbacks.remove(callback)

        if self._after_remove_func:
            self._after_remove_func()


class Version(object):
    """
    A simple class to manage incremental version of data.

    :param int number: The initial version number.
    """
    def __init__(self, number=0):
        self._number = number
        self._changed = EventHandler()

    @property
    def changed(self):
        """
        Get the changed event handler.
        :return EventHandler: The changed event handler.
        """
        return self._changed

    @property
    def number(self):
        """
        Get the version number.
        :return int: The version number.
        """
        return self._number

    @number.setter
    def number(self, value):
        """
        Set the version number.
        :param int value: The version number.
        """
        self._number = value
        self._changed()

    def __str__(self):
        """
        Get the version number as string.
        :return str: The version number as string.
        """
        return str(self._number)

    def __repr__(self):
        """
        Get a friendly version number.
        :return str: The friendly string number.
        """
        return 'Version(%s)' % str(self._number)