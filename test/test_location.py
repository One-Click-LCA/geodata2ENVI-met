# coding=utf-8
"""core.location with a fake requests module (no network)."""

import unittest

from .plugin_env import import_plugin_module


class FakeResponse:
    def __init__(self, data, status=200):
        self.status_code = status
        self._data = data

    def json(self):
        return self._data


class FakeRequests:
    def __init__(self, data=None, error=None):
        self.data = data
        self.error = error
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params))
        if self.error:
            raise self.error
        return FakeResponse(self.data)


class LocationTest(unittest.TestCase):

    def setUp(self):
        self.location = import_plugin_module('core.location')
        self.location._cache.clear()

    def test_standard_time_not_summer_time(self):
        sydney = FakeRequests({'gmtOffset': 11, 'rawOffset': 10, 'dstOffset': 10, 'timezoneId': 'Australia/Sydney'})
        self.assertEqual(self.location.standard_time_offset(-33.87, 151.21, sydney), (10.0, None))
        self.assertTrue(sydney.calls[0][0].startswith('https://'))

    def test_answers_are_cached(self):
        fake = FakeRequests({'rawOffset': 1})
        self.location.standard_time_offset(52.5, 13.4, fake)
        self.location.standard_time_offset(52.5, 13.4, fake)
        self.assertEqual(len(fake.calls), 1)

    def test_fallback_is_reported(self):
        offline = FakeRequests(error=OSError('offline'))
        offset, problem = self.location.standard_time_offset(48.0, 11.6, offline)
        self.assertEqual(offset, 1.0)
        self.assertIn('could not be reached', problem)
        limit = FakeRequests({'status': {'message': 'limit exceeded', 'value': 18}})
        offset, problem = self.location.standard_time_offset(48.0, -3.0, limit)
        self.assertEqual((offset, problem), (0.0, 'GeoNames gave no time zone'))

    def test_elevation(self):
        self.assertEqual(self.location.elevation(48.0, 11.6, FakeRequests({'srtm1': 520})), 520)
        self.assertEqual(self.location.elevation(52.3, 4.6, FakeRequests({'srtm1': -4})), -4)   # below sea level
        self.assertIsNone(self.location.elevation(54.0, 5.0, FakeRequests({'srtm1': -32768})))
        self.assertIsNone(self.location.elevation(1.0, 1.0, FakeRequests(error=TimeoutError())))


if __name__ == '__main__':
    unittest.main()
