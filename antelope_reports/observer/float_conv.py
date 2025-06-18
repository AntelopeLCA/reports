import locale
import logging

locale.setlocale(locale.LC_ALL, locale.getdefaultlocale())


def try_float(thing):
    """
    fail loudly: fallback to atof, but raise exception if that fails
    :param thing:
    :return:
    """
    try:
        value = float(thing)
    except ValueError:
        value = locale.atof(thing)
    return value


def to_float(thing):
    """
    fail silently: catch exceptions and return 0.0 if they arise
    :param thing:
    :return:
    """
    try:
        return try_float(thing)
    except ValueError:
        logging.warning('float value error "%s" - using 0.0' % thing)
        return 0.0
    except TypeError:
        logging.warning('float type error %s (%s) - using 0.0' % (thing, type(thing)))
        return 0.0
