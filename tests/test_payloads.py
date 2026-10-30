import unittest

from tradenet.payloads import Item, decode, encode


class PayloadTests(unittest.TestCase):
    def test_useful_items_only_no_filler(self):
        items = [Item("trade", b"T1"), Item("neighbors", b"K7OR")]
        blob = encode(items)
        self.assertEqual(blob, b"TN1\x01\x00\x02T1\x03\x00\x04K7OR")
        self.assertEqual(decode(blob), items)

    def test_size_budget_and_empty_items_rejected(self):
        with self.assertRaises(ValueError):
            encode([Item("status", b"alive")], max_bytes=5)
        with self.assertRaises(ValueError):
            encode([Item("status", b"")])


if __name__ == "__main__":
    unittest.main()
