import unittest

from xiaomiao_bot.core.message_delivery_stats import build_message_delivery_stats


class MessageDeliveryStatsTests(unittest.TestCase):
    def test_build_stats_for_messages(self) -> None:
        stats = build_message_delivery_stats(["abc", "de"])

        self.assertEqual(stats.chunk_count, 2)
        self.assertEqual(stats.total_chars, 5)
        self.assertEqual(stats.max_chunk_chars, 3)

    def test_build_stats_for_empty_messages(self) -> None:
        stats = build_message_delivery_stats([])

        self.assertEqual(stats.chunk_count, 0)
        self.assertEqual(stats.total_chars, 0)
        self.assertEqual(stats.max_chunk_chars, 0)


if __name__ == "__main__":
    unittest.main()
