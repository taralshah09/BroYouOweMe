from collections import defaultdict
from itertools import product

from django.test import SimpleTestCase

from apps.settlements.services import minimum_transfers


class SimplificationTests(SimpleTestCase):
    def verify(self, nets, count):
        transfers = minimum_transfers(nets)
        self.assertEqual(len(transfers), count)
        actual = defaultdict(int)
        for debtor, creditor, amount in transfers:
            self.assertGreater(amount, 0)
            self.assertLess(nets[debtor], 0)
            self.assertGreater(nets[creditor], 0)
            actual[debtor] -= amount
            actual[creditor] += amount
        self.assertEqual({k: v for k, v in actual.items() if v}, {k: v for k, v in nets.items() if v})
        self.assertEqual(transfers, minimum_transfers(nets))

    def test_empty_cycles_and_uneven_totals(self):
        self.verify({}, 0)
        self.verify({1: 0, 2: 0, 3: 0}, 0)
        self.verify({1: -101, 2: -99, 3: 200}, 2)
        self.verify({1: -500, 2: 300, 3: 200}, 2)

    def test_exact_search_beats_largest_first_greedy(self):
        self.verify({1: -800, 2: -700, 3: -500, 4: 1000, 5: 800, 6: 200}, 4)

    def test_exhaustive_small_cases_against_zero_sum_partition_oracle(self):
        def max_components(values):
            if not values:
                return 0
            best = 0
            for mask in range(1, 1 << len(values), 2):
                if sum(v for i, v in enumerate(values) if mask & (1 << i)) == 0:
                    remaining = tuple(v for i, v in enumerate(values) if not mask & (1 << i))
                    best = max(best, 1 + max_components(remaining))
            return best

        for prefix in product((-2, -1, 0, 1, 2), repeat=4):
            values = tuple(v for v in (*prefix, -sum(prefix)) if v)
            self.verify(dict(enumerate(values)), len(values) - max_components(values))

    def test_invalid_nets(self):
        for nets in [{1: 1}, {1: -1.0, 2: 1}, {1: True, 2: -1}]:
            with self.assertRaises(ValueError):
                minimum_transfers(nets)
