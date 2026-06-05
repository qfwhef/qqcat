import unittest

from xiaomiao_bot.core.text_splitting import split_text_chunks


class TextSplittingTests(unittest.TestCase):
    def test_split_preserves_original_text_and_respects_limit(self) -> None:
        text = "第一段内容\n\n第二段内容比较长\n第三段"

        chunks = split_text_chunks(text, max_chars=8)

        self.assertEqual("".join(chunks), text)
        self.assertTrue(all(0 < len(chunk) <= 8 for chunk in chunks))

    def test_split_hard_cuts_text_without_boundaries(self) -> None:
        chunks = split_text_chunks("abcdefghij", max_chars=4)

        self.assertEqual(chunks, ["abcd", "efgh", "ij"])

    def test_split_empty_text_returns_no_chunks(self) -> None:
        self.assertEqual(split_text_chunks("", max_chars=4), [])

    def test_split_rejects_non_positive_limit(self) -> None:
        with self.assertRaises(ValueError):
            split_text_chunks("abc", max_chars=0)


if __name__ == "__main__":
    unittest.main()
