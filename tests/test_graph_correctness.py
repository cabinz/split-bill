"""Test cases to ensure graph simplification correctness and no participant loses money."""

import pytest
import math
from collections import defaultdict
from splitbill.settle.graph import LendingGraph, is_zero, ABS_TOL
from splitbill.settle.simplify import simplest_equiv, check_equiv


class TestGraphCorrectness:
    """Test that the graph simplification algorithm preserves correctness."""
    
    def test_net_cash_flow_preservation(self):
        """Test that net cash flows are preserved after simplification."""
        # Create a complex lending graph
        g = LendingGraph()
        
        # Alice paid 300 for everyone
        g.add_edge("Alice", "Bob", 100)
        g.add_edge("Alice", "Charlie", 100)
        g.add_edge("Alice", "David", 100)
        
        # Bob paid 200 for Alice and Charlie
        g.add_edge("Bob", "Alice", 100)
        g.add_edge("Bob", "Charlie", 100)
        
        # Charlie paid 100 for David
        g.add_edge("Charlie", "David", 100)
        
        # Store original net flows
        original_net_flows = dict(g.net_out_flow)
        
        # Simplify the graph
        simplified = simplest_equiv(g)
        
        # Check that net flows are preserved
        for person in original_net_flows:
            assert math.isclose(
                original_net_flows[person], 
                simplified.net_out_flow[person],
                abs_tol=ABS_TOL
            ), f"{person}'s net flow changed from {original_net_flows[person]} to {simplified.net_out_flow[person]}"
        
        # Verify using built-in check
        assert check_equiv(g, simplified), "Graphs are not equivalent"
    
    def test_no_participant_loses_money(self):
        """Test that no participant ends up with negative balance after simplification."""
        g = LendingGraph()
        
        # Complex scenario with multiple transactions
        g.add_edge("Alice", "Bob", 500)
        g.add_edge("Alice", "Charlie", 300)
        g.add_edge("Bob", "Charlie", 200)
        g.add_edge("Charlie", "Alice", 100)
        g.add_edge("David", "Alice", 400)
        g.add_edge("David", "Bob", 100)
        
        # Calculate who owes or is owed money (positive = owed, negative = owes)
        original_balances = dict(g.net_out_flow)
        
        # Simplify
        simplified = simplest_equiv(g)
        simplified_balances = dict(simplified.net_out_flow)
        
        # Verify balances are preserved
        for person in original_balances:
            assert math.isclose(
                original_balances[person],
                simplified_balances[person],
                abs_tol=ABS_TOL
            ), f"{person}'s balance changed"
            
        # Verify the sum of all balances is zero (closed system)
        total_original = sum(original_balances.values())
        total_simplified = sum(simplified_balances.values())
        
        assert is_zero(total_original), f"Original balances don't sum to zero: {total_original}"
        assert is_zero(total_simplified), f"Simplified balances don't sum to zero: {total_simplified}"
    
    def test_empty_graph(self):
        """Test that empty graph remains empty after simplification."""
        g = LendingGraph()
        simplified = simplest_equiv(g)
        
        assert len(simplified.get_nodes()) == 0
        assert simplified.num_edges() == 0
    
    def test_single_transaction(self):
        """Test graph with single transaction."""
        g = LendingGraph()
        g.add_edge("Alice", "Bob", 100)
        
        simplified = simplest_equiv(g)
        
        # Should remain the same
        assert simplified.num_edges() == 1
        assert simplified.get_flow("Alice", "Bob") == 100
        assert simplified.net_out_flow["Alice"] == 100
        assert simplified.net_out_flow["Bob"] == -100
    
    def test_circular_debt_cancellation(self):
        """Test that circular debts are properly cancelled."""
        g = LendingGraph()
        
        # Create a circular debt: A->B->C->A
        g.add_edge("Alice", "Bob", 100)
        g.add_edge("Bob", "Charlie", 100)
        g.add_edge("Charlie", "Alice", 100)
        
        simplified = simplest_equiv(g)
        
        # All debts should cancel out
        assert simplified.num_edges() == 0
        for person in ["Alice", "Bob", "Charlie"]:
            assert is_zero(simplified.net_out_flow[person])
    
    def test_partial_circular_debt(self):
        """Test circular debt with additional transactions."""
        g = LendingGraph()
        
        # Circular debt with extra
        g.add_edge("Alice", "Bob", 150)  # Alice owes Bob 150
        g.add_edge("Bob", "Charlie", 100)  # Bob owes Charlie 100
        g.add_edge("Charlie", "Alice", 100)  # Charlie owes Alice 100
        
        simplified = simplest_equiv(g)
        
        # After cancellation, only Alice->Bob 50 should remain
        assert simplified.num_edges() == 1
        assert simplified.get_flow("Alice", "Bob") == 50
        
        # Verify net flows
        assert simplified.net_out_flow["Alice"] == 50
        assert simplified.net_out_flow["Bob"] == -50
        assert is_zero(simplified.net_out_flow["Charlie"])
    
    def test_complex_multi_party_scenario(self):
        """Test complex scenario with many participants."""
        g = LendingGraph()
        
        # Trip expenses scenario
        # Alice paid for hotel (shared by all 4)
        g.add_edge("Alice", "Bob", 250)
        g.add_edge("Alice", "Charlie", 250)
        g.add_edge("Alice", "David", 250)
        
        # Bob paid for meals (shared by Alice, Bob, Charlie)
        g.add_edge("Bob", "Alice", 100)
        g.add_edge("Bob", "Charlie", 100)
        
        # Charlie paid for transport (shared by all 4)
        g.add_edge("Charlie", "Alice", 50)
        g.add_edge("Charlie", "Bob", 50)
        g.add_edge("Charlie", "David", 50)
        
        # David paid for activities (shared by Bob and David)
        g.add_edge("David", "Bob", 75)
        
        # Calculate expected net flows
        expected_net = {
            "Alice": 250 + 250 + 250 - 100 - 50,  # 600
            "Bob": -250 + 100 + 100 - 50 - 75,  # -175
            "Charlie": -250 - 100 + 50 + 50 + 50,  # -200
            "David": -250 - 50 + 75  # -225
        }
        
        # Verify original graph
        for person, expected in expected_net.items():
            assert math.isclose(
                g.net_out_flow[person], 
                expected,
                abs_tol=ABS_TOL
            ), f"{person}'s original net flow is incorrect"
        
        # Simplify
        simplified = simplest_equiv(g)
        
        # Verify simplified graph preserves net flows
        for person, expected in expected_net.items():
            assert math.isclose(
                simplified.net_out_flow[person],
                expected,
                abs_tol=ABS_TOL
            ), f"{person}'s simplified net flow is incorrect"
        
        # Verify it's actually simplified (fewer edges)
        assert simplified.num_edges() <= g.num_edges()
        
        # Verify sum is zero
        assert is_zero(sum(simplified.net_out_flow.values()))
    
    def test_ensure_minimum_transactions(self):
        """Test that simplification actually minimizes transactions."""
        g = LendingGraph()
        
        # Create a scenario that can be simplified
        # Everyone owes Alice, but with different amounts
        g.add_edge("Alice", "Bob", 100)
        g.add_edge("Alice", "Charlie", 200)
        g.add_edge("Alice", "David", 150)
        
        # Bob also owes Charlie
        g.add_edge("Bob", "Charlie", 50)
        
        # Charlie owes David
        g.add_edge("Charlie", "David", 75)
        
        original_edges = g.num_edges()  # Should be 5
        simplified = simplest_equiv(g)
        simplified_edges = simplified.num_edges()
        
        # Simplified should have fewer or equal edges
        assert simplified_edges <= original_edges
        
        # Verify correctness
        assert check_equiv(g, simplified)
    
    def test_zero_sum_verification(self):
        """Test that the total system always sums to zero."""
        test_cases = [
            # Simple case
            [("Alice", "Bob", 100)],
            # Multiple creditors
            [("Alice", "Bob", 100), ("Charlie", "Bob", 50)],
            # Complex network
            [
                ("Alice", "Bob", 100),
                ("Bob", "Charlie", 50),
                ("Charlie", "David", 25),
                ("David", "Alice", 75),
                ("Emily", "Frank", 200),
                ("Frank", "Alice", 100)
            ]
        ]
        
        for edges in test_cases:
            g = LendingGraph()
            for creditor, debtor, amount in edges:
                g.add_edge(creditor, debtor, amount)
            
            # Original graph sum
            original_sum = sum(g.net_out_flow.values())
            assert is_zero(original_sum), f"Original graph doesn't sum to zero: {original_sum}"
            
            # Simplified graph sum
            simplified = simplest_equiv(g)
            simplified_sum = sum(simplified.net_out_flow.values())
            assert is_zero(simplified_sum), f"Simplified graph doesn't sum to zero: {simplified_sum}"
    
    def test_precision_handling(self):
        """Test that floating point precision is handled correctly."""
        g = LendingGraph()
        
        # Add transactions with decimal values
        g.add_edge("Alice", "Bob", 33.33)
        g.add_edge("Alice", "Charlie", 33.33)
        g.add_edge("Alice", "David", 33.34)  # Total: 100.00
        
        g.add_edge("Bob", "Alice", 25.00)
        g.add_edge("Charlie", "Alice", 25.00)
        g.add_edge("David", "Alice", 25.00)
        
        simplified = simplest_equiv(g)
        
        # Check equivalence
        assert check_equiv(g, simplified)
        
        # Verify that small rounding errors are handled
        total = sum(simplified.net_out_flow.values())
        assert abs(total) < ABS_TOL, f"Total is not close to zero: {total}"
    
    def test_large_amounts(self):
        """Test with large monetary amounts."""
        g = LendingGraph()
        
        # Large amounts
        g.add_edge("Company_A", "Company_B", 1000000)
        g.add_edge("Company_B", "Company_C", 500000)
        g.add_edge("Company_C", "Company_A", 250000)
        
        simplified = simplest_equiv(g)
        
        # Verify correctness
        assert check_equiv(g, simplified)
        
        # Verify net flows
        assert simplified.net_out_flow["Company_A"] == 1000000 - 250000
        assert simplified.net_out_flow["Company_B"] == -1000000 + 500000
        assert simplified.net_out_flow["Company_C"] == -500000 + 250000


class TestErrorConditions:
    """Test error conditions and edge cases."""
    
    def test_self_lending_prevention(self):
        """Test that self-lending is prevented."""
        g = LendingGraph()
        
        with pytest.raises(AssertionError, match="should not be the same"):
            g.add_edge("Alice", "Alice", 100)
    
    def test_negative_amount_cancellation(self):
        """Test that negative amounts work as cancellation."""
        g = LendingGraph()
        
        # Add a debt
        g.add_edge("Alice", "Bob", 100)
        assert g.get_flow("Alice", "Bob") == 100
        
        # Cancel it with negative amount
        g.add_edge("Alice", "Bob", -100)
        assert g.get_flow("Alice", "Bob") == 0
        assert not g.has_edge("Alice", "Bob")
    
    def test_mutual_debt_cancellation(self):
        """Test mutual debts are handled correctly."""
        g = LendingGraph()
        
        # Alice owes Bob 100
        g.add_edge("Alice", "Bob", 100)
        # Bob owes Alice 60
        g.add_edge("Bob", "Alice", 60)
        
        simplified = simplest_equiv(g)
        
        # Should result in Alice owing Bob 40
        assert simplified.num_edges() == 1
        assert simplified.get_flow("Alice", "Bob") == 40