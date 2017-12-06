# Licensed under a 3-clause BSD style license - see LICENSE.rst
"""
VOSI mixins
"""
from __future__ import (
    absolute_import, division, print_function, unicode_literals)

from functools import partial
from itertools import chain
import requests

from astropy.utils.decorators import lazyproperty

from .exceptions import DALServiceError
from ..io import vosi
from ..utils.url import url_sibling

__all__ = ['AvailabilityMixin', 'CapabilityMixin']


class VOSITables(object):
    """
    This class encapsulates access to the VOSITables using a given Endpoint.
    Access to table names is like accessing dictionary keys. using iterator
    syntax or `keys()`
    """
    def __init__(self, vosi_tables, endpoint_url):
        self._vosi_tables = vosi_tables
        self._endpoint_url = endpoint_url
        self._cache = {}

    def __len__(self):
        return self._vosi_tables.ntables

    def __getitem__(self, key):
        return self._get_table(key)

    def __iter__(self):
        return self.keys()

    def _get_table(self, name):
        if name in self._cache:
            return self._cache[name]

        table = self._vosi_tables.get_table_by_name(name)

        if not table.columns and not table.foreignkeys:
            tables_url = '{}/{}'.format(self._endpoint_url, name)
            response = requests.get(tables_url, stream=True)

            try:
                response.raise_for_status()
            except requests.RequestException as ex:
                raise DALServiceError.from_except(ex, tables_url)

            # requests doesn't decode the content by default
            response.raw.read = partial(response.raw.read, decode_content=True)

            table = vosi.parse_tables(response.raw.read).get_first_table()
            self._cache[name] = table

        return table

    def keys(self):
        """
        Iterates over the keys (table names).
        """
        for table in self._vosi_tables.iter_tables():
            yield table.name

    def values(self):
        """
        Iterates over the values (tables).
        Gathers missing values from endpoint if necessary.
        """
        for name in self.keys():
            yield self._get_table(name)

    def items(self):
        """
        Iterates over keys and values (table names and tables).
        Gathers missing values from endpoint if necessary.
        """
        for name in self.keys():
            yield (name, self._get_table(name))


class AvailabilityMixin(object):
    """
    Mixing for VOSI availability
    """
    _availability = None

    @property
    def availability(self):
        """
        Service Availability as a
        :py:class:`~pyvo.io.vosi.availability.Availability` object
        """
        if self._availability is None:
            avail_url = '{0}/availability'.format(self.baseurl)

            response = requests.get(avail_url, stream=True)

            try:
                response.raise_for_status()
            except requests.RequestException as ex:
                raise DALServiceError.from_except(ex, avail_url)

            # requests doesn't decode the content by default
            response.raw.read = partial(response.raw.read, decode_content=True)

            self._availability = vosi.parse_availability(response.raw.read)
        return self._availability

    @property
    def available(self):
        """
        True if the service is available, False otherwise
        """
        return self.availability.available

    @property
    def up_since(self):
        """
        datetime the service was started
        """
        return self.availability.upsince


class CapabilityMixin(object):
    """
    Mixing for VOSI capability
    """
    _capabilities = None

    @lazyproperty
    def capabilities(self):
        """
        Returns capabilities as a
        py:class:`~pyvo.io.vosi.availability.Availability` object
        """
        capa_urls = [
            '{0}/capabilities'.format(self.baseurl),
            url_sibling(self.baseurl, 'capabilities')
        ]

        for capa_url in capa_urls:
            try:
                response = requests.get(capa_url, stream=True)
                response.raise_for_status()
                break
            except requests.RequestException:
                continue
        else:
            raise DALServiceError("No working capabilities endpoint provided")

        # requests doesn't decode the content by default
        response.raw.read = partial(response.raw.read, decode_content=True)

        return vosi.parse_capabilities(response.raw.read, capa_url)


class TablesMixin(CapabilityMixin):
    """
    Mixin for VOSI tables
    """

    @lazyproperty
    def tables(self):
        try:
            interfaces = next(
                _ for _ in self.capabilities if _.standardid.startswith(
                    'ivo://ivoa.net/std/VOSI#tables')
            ).interfaces
            accessurls = chain.from_iterable(_.accessurls for _ in interfaces)
            tables_urls = (_.value for _ in accessurls)
        except StopIteration:
            tables_urls = [
                '{0}/tables'.format(self.baseurl),
                url_sibling(self.baseurl, 'tables')
            ]

        for tables_url in tables_urls:
            try:
                response = requests.get(tables_url, stream=True)
                response.raise_for_status()
                break
            except requests.RequestException:
                continue
        else:
            raise DALServiceError("No working tables endpoint provided")

        # requests doesn't decode the content by default
        response.raw.read = partial(response.raw.read, decode_content=True)

        return VOSITables(
            vosi.parse_tables(response.raw.read), tables_url)
