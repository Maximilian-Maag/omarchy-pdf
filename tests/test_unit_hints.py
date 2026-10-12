"""Unit tests: pdf/hints — label generation and matching."""
import pathlib
import sys
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from pdf import hints  # noqa: E402

A = hints.ALPHABET


class LabelLengthCase(unittest.TestCase):
    def test_single_char_floor(self):
        self.assertEqual(hints.label_length(1), 1)

    def test_zero_is_one(self):
        self.assertEqual(hints.label_length(0), 1)

    def test_negative_is_one(self):
        self.assertEqual(hints.label_length(-5), 1)

    def test_exactly_alphabet_is_one(self):
        self.assertEqual(hints.label_length(len(A)), 1)

    def test_one_over_alphabet_is_two(self):
        self.assertEqual(hints.label_length(len(A) + 1), 2)

    def test_quadratic_capacity_is_two(self):
        self.assertEqual(hints.label_length(len(A) ** 2), 2)

    def test_over_quadratic_is_three(self):
        self.assertEqual(hints.label_length(len(A) ** 2 + 1), 3)


class LabelForCase(unittest.TestCase):
    def test_first(self):
        self.assertEqual(hints.label_for(0, 1), A[0])

    def test_second(self):
        self.assertEqual(hints.label_for(1, 1), A[1])

    def test_two_char_carry(self):
        # the FIRST character is the high-order digit, so typing it narrows a group
        self.assertEqual(hints.label_for(1, 2), A[0] + A[1])
        # index len(A) wraps the low digit back to A[0]
        self.assertEqual(hints.label_for(len(A), 2), A[1] + A[0])


class GenerateCase(unittest.TestCase):
    def test_count(self):
        self.assertEqual(len(hints.generate_labels(7)), 7)

    def test_distinct(self):
        labels = hints.generate_labels(40)
        self.assertEqual(len(set(labels)), 40)

    def test_uniform_length(self):
        labels = hints.generate_labels(40)
        self.assertTrue(all(len(x) == 2 for x in labels))

    def test_short_is_single_char(self):
        labels = hints.generate_labels(len(A))
        self.assertTrue(all(len(x) == 1 for x in labels))


class MatchCase(unittest.TestCase):
    def setUp(self):
        self.labels = hints.generate_labels(4)   # 'a' 's' 'd' 'f'

    def test_all_when_empty(self):
        self.assertEqual(hints.matching(self.labels, ""), [0, 1, 2, 3])

    def test_narrows(self):
        self.assertEqual(hints.matching(self.labels, "s"), [1])

    def test_unique_match(self):
        self.assertEqual(hints.unique_match(self.labels, "d"), 2)

    def test_unique_match_missing(self):
        self.assertEqual(hints.unique_match(self.labels, "z"), -1)

    def test_complete_when_single(self):
        self.assertTrue(hints.is_complete(self.labels, "s"))

    def test_not_complete_when_ambiguous(self):
        labels = hints.generate_labels(len(A) + 1)   # all 2-char, share prefixes
        self.assertFalse(hints.is_complete(labels, labels[0][0]))

    def test_complete_when_full_label(self):
        labels = hints.generate_labels(len(A) + 1)
        self.assertTrue(hints.is_complete(labels, labels[0]))


if __name__ == "__main__":
    unittest.main()
