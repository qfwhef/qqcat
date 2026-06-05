import unittest

from xiaomiao_bot.core.async_blocking import run_blocking


class AsyncBlockingTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_blocking_returns_function_result(self) -> None:
        result = await run_blocking(lambda value: value + 1, 4)

        self.assertEqual(result, 5)

    async def test_run_blocking_propagates_exceptions(self) -> None:
        def fail() -> None:
            raise RuntimeError("boom")

        with self.assertRaisesRegex(RuntimeError, "boom"):
            await run_blocking(fail)


if __name__ == "__main__":
    unittest.main()
