import unittest

from xiaomiao_bot.core.ttl_cache import TimedValueCache


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class TimedValueCacheTests(unittest.TestCase):
    def test_get_reuses_value_until_ttl_expires(self) -> None:
        clock = FakeClock()
        cache: TimedValueCache[int] = TimedValueCache(ttl_seconds=5.0, clock=clock)
        calls = 0

        def load() -> int:
            nonlocal calls
            calls += 1
            return calls

        self.assertEqual(cache.get(load), 1)
        clock.now = 4.0
        self.assertEqual(cache.get(load), 1)
        clock.now = 5.0
        self.assertEqual(cache.get(load), 2)

    def test_clear_forces_reload(self) -> None:
        cache: TimedValueCache[int] = TimedValueCache(ttl_seconds=30.0)
        calls = 0

        def load() -> int:
            nonlocal calls
            calls += 1
            return calls

        self.assertEqual(cache.get(load), 1)
        cache.clear()
        self.assertEqual(cache.get(load), 2)


if __name__ == "__main__":
    unittest.main()
