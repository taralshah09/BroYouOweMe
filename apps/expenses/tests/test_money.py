from decimal import Decimal, localcontext

from django.test import SimpleTestCase

from apps.expenses.services.money import (
    MAX_PAISE,
    allocate_equal,
    paise_to_rupees,
    rupees_to_paise,
)


class MoneyTests(SimpleTestCase):
    def test_exact_conversion_and_round_trip(self):
        for value, expected in [(1200, 120000), ("0.01", 1), ("1200.50", 120050),
                                (Decimal("12.30"), 1230), ("-0.01", -1), ("0", 0)]:
            with self.subTest(value=value):
                self.assertEqual(rupees_to_paise(value), expected)
                self.assertEqual(rupees_to_paise(paise_to_rupees(expected)), expected)

    def test_rejects_lossy_or_invalid_input(self):
        for value in [0.1, True, None, "1.001", "NaN", "Infinity", "1e2", "", " 1.00", "1,000"]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                rupees_to_paise(value)

    def test_bigint_boundary_without_decimal_context_rounding(self):
        with localcontext() as context:
            context.prec = 3
            self.assertEqual(rupees_to_paise(paise_to_rupees(MAX_PAISE)), MAX_PAISE)
        with self.assertRaises(ValueError):
            rupees_to_paise("92233720368547758.08")
        for value in [True, 1.0, MAX_PAISE + 1]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                paise_to_rupees(value)

    def test_remainder_is_assigned_by_ascending_user_id(self):
        self.assertEqual(allocate_equal(100, [9, 2, 5]), {2: 34, 5: 33, 9: 33})
        self.assertEqual(allocate_equal(120000, [3, 1, 2]), {1: 40000, 2: 40000, 3: 40000})

    def test_conservation_for_small_totals_and_discounts(self):
        for total in range(-101, 102):
            for count in range(1, 10):
                shares = allocate_equal(total, reversed(range(1, count + 1)))
                self.assertEqual(sum(shares.values()), total)
                self.assertLessEqual(max(shares.values()) - min(shares.values()), 1)
        self.assertEqual(allocate_equal(-100, [3, 1, 2]), {1: -33, 2: -33, 3: -34})
        self.assertEqual(allocate_equal(1, [2, 1]), {1: 1, 2: 0})

    def test_rejects_invalid_participants_and_totals(self):
        for participants in [[], [1, 1], [0], [-1], [True], ["1"]]:
            with self.subTest(participants=participants), self.assertRaises(ValueError):
                allocate_equal(100, participants)
        with self.assertRaises(ValueError):
            allocate_equal(1.0, [1])
