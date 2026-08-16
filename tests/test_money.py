"""`utils.money`: the arithmetic the appendix is checked against.

Plan §9.1. The guarantee is small and absolute -- shares add up to the total they
came from, and the same bill always allocates them the same way. Both halves are
load-bearing: the first is what lets a member verify a column, the second is what
stops two exports of one bill from disagreeing.

The properties are checked over a range of totals rather than a few chosen ones,
because the failure mode here is a total whose cents happen to divide awkwardly, and
picking examples by hand is how you miss exactly those.
"""

import pytest

from splitbill.utils.money import (from_minor, round_money, split_evenly,
                                   to_minor)

# Odd cents, prices, an amount below a cent, and one large enough that float
# addition of its shares is visibly lossy.
TOTALS = [0.0, 0.01, 0.02, 0.03, 0.07, 1.0, 9.99, 10.0, 100.0, 123.45,
          999.99, 1000.0, 37986.31, 0.001]

PARTIES = [1, 2, 3, 4, 5, 6, 7, 11, 13, 100]


class TestSplitEvenlySums:
    """The whole point: no column ever comes up short."""

    @pytest.mark.parametrize("total", TOTALS)
    @pytest.mark.parametrize("n", PARTIES)
    def test_shares_sum_to_the_total(self, total, n):
        shares = split_evenly(total, n)
        assert sum(shares) == pytest.approx(round_money(total), abs=1e-9)

    @pytest.mark.parametrize("total", TOTALS)
    @pytest.mark.parametrize("n", PARTIES)
    def test_in_whole_cents_it_is_exact(self, total, n):
        """Summed as integers there is no tolerance at all -- and this is the form
        the guarantee actually holds in. Float addition of the shares is only
        approximately associative, which is what the `approx` above is for."""
        shares = split_evenly(total, n)
        assert sum(to_minor(s) for s in shares) == to_minor(total)

    @pytest.mark.parametrize("total", TOTALS)
    @pytest.mark.parametrize("n", PARTIES)
    def test_every_share_lands_on_a_cent(self, total, n):
        for share in split_evenly(total, n):
            assert share == round(share, 2)

    @pytest.mark.parametrize("total", TOTALS)
    @pytest.mark.parametrize("n", PARTIES)
    def test_shares_differ_by_at_most_one_cent(self, total, n):
        """An even split, in the only sense available once cents are indivisible."""
        shares = split_evenly(total, n)
        assert to_minor(max(shares)) - to_minor(min(shares)) <= 1


class TestSplitEvenlyIsDeterministic:
    @pytest.mark.parametrize("total", TOTALS)
    def test_same_inputs_give_the_same_shares(self, total):
        assert split_evenly(total, 7) == split_evenly(total, 7)

    def test_the_remainder_goes_to_the_front(self):
        """The order is the contract `loader.ledger` relies on: it maps these onto
        members sorted by name, so which member gains a cent has to be decided here
        and stay decided."""
        assert split_evenly(1.00, 3) == [0.34, 0.33, 0.33]
        assert split_evenly(1.00, 4) == [0.25, 0.25, 0.25, 0.25]
        assert split_evenly(0.05, 3) == [0.02, 0.02, 0.01]

    def test_exactly_the_remainder_many_shares_are_larger(self):
        for n in PARTIES:
            shares = split_evenly(100.0, n)
            _, remainder = divmod(to_minor(100.0), n)
            larger = sum(1 for s in shares if to_minor(s) == to_minor(max(shares)))
            if remainder:
                assert larger == remainder, n


class TestSplitEvenlyEdges:
    def test_one_way_is_the_whole_amount(self):
        assert split_evenly(99.99, 1) == [99.99]

    def test_zero_splits_into_zeros(self):
        assert split_evenly(0.0, 4) == [0.0, 0.0, 0.0, 0.0]

    def test_a_sub_cent_total_gives_one_person_nothing_rather_than_a_fraction(self):
        """0.4¢ rounds to nothing. Everyone getting 0.00 is the honest outcome --
        the alternative is fractions of a cent, which is what 0h removed."""
        assert split_evenly(0.004, 2) == [0.0, 0.0]

    def test_a_single_cent_goes_to_one_person(self):
        assert split_evenly(0.01, 5) == [0.01, 0.0, 0.0, 0.0, 0.0]

    def test_negative_totals_still_sum(self):
        """Not reachable from a validated bill, where amounts are positive. Checked
        anyway: the function has no business silently mangling one, and a refund
        column is an obvious future feature."""
        shares = split_evenly(-1.00, 3)
        assert sum(to_minor(s) for s in shares) == to_minor(-1.00)

    @pytest.mark.parametrize("n", [0, -1])
    def test_splitting_between_nobody_is_an_error(self, n):
        """A record with no debtors is a data problem, and one the validator already
        rejects. Raising here rather than returning `[]` keeps it from turning into a
        silently vanished record if a later caller forgets to check."""
        with pytest.raises(ValueError, match="cannot split"):
            split_evenly(10.0, n)


class TestMinorUnitConversion:
    @pytest.mark.parametrize("amount,expected", [
        (0.0, 0), (0.01, 1), (0.004, 0), (1.0, 100),
        (37986.31, 3798631), (-0.01, -1),
    ])
    def test_to_minor(self, amount, expected):
        assert to_minor(amount) == expected

    def test_rounding_at_the_half_cent_goes_to_even(self):
        """`round` is half-to-even, so 0.005 becomes 0¢ and 0.015 becomes 2¢.

        Kept rather than forced to half-up. A record total only lands exactly on a
        half-cent through currency conversion, so this is rare; and when it does,
        half-to-even is the better of two arbitrary choices, because half-up biases
        every such record upwards while this one does not bias at all.

        Written down because it is surprising, and because the alternative is
        somebody hitting it later and assuming it is a bug.
        """
        assert to_minor(0.005) == 0
        assert to_minor(0.015) == 2
        assert to_minor(0.025) == 2

    def test_truncation_would_lose_a_cent_where_rounding_does_not(self):
        """Why `round` and not `int`. `1.15 * 100` is 114.99999999999999 in binary
        floating point, so truncating it yields 114¢ for an amount a human wrote as
        one dollar fifteen."""
        assert 1.15 * 100 < 115
        assert int(1.15 * 100) == 114
        assert to_minor(1.15) == 115

    @pytest.mark.parametrize("total", TOTALS)
    def test_round_money_is_idempotent(self, total):
        once = round_money(total)
        assert round_money(once) == once

    @pytest.mark.parametrize("minor", [0, 1, 99, 100, 3798631, -1])
    def test_from_minor_inverts_to_minor(self, minor):
        assert to_minor(from_minor(minor)) == minor
