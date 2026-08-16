"""Reduce a lending graph to the fewest transfers that settle it.

`simplest_equiv` is the core of the tool: it discards who lent to whom, keeps
only each member's net, and re-pairs those nets into as few transfers as
possible. That re-pairing is why a settlement can name a counterparty a member
never lent to or borrowed from, and why the report has to show the lending edges
alongside it.

Split out of graph.py in plan step 0d. The data structure and the algorithm over
it had no reason to share a module: this half is the only part that needs to stay
free of pandas, and keeping them apart is what lets the algorithm be tested
without a loader anywhere in sight.
"""

from ..utils.logger import get_logger
from .graph import LendingGraph, is_equal, is_zero

from copy import deepcopy
from collections import defaultdict

logger = get_logger(__name__)


def check_equiv(g1: LendingGraph, g2: LendingGraph) -> bool:
    # Get all nodes that have non-zero net flow in either graph
    all_nodes = set(g1.net_out_flow.keys()) | set(g2.net_out_flow.keys())
    
    for node in all_nodes:
        flow1 = g1.net_out_flow.get(node, 0.0)
        flow2 = g2.net_out_flow.get(node, 0.0)
        if not is_equal(flow1, flow2):
            return False
    return True


def simplest_equiv(g: LendingGraph, log=logger) -> LendingGraph:
    # Question modeling:
    # Given two set of nodes (creditors and debtors), each of them corresponds to a value (amount).
    # Sum of values of in the two sets are guaranteed to be the same.
    # Construct a weighted graph with LEAST number of edges connecting nodes from two different sets.
    # The sum of the weights of all edges connecting to a node should be equal to the node value.

    # Algorithm: DP

    # def _status_tag(creditors, debtors) -> str:
    #     tag = ""
    #     for node in sorted(creditors):
    #         tag += f"L({node}:{creditors[node]}),"
    #     for node in sorted(debtors):
    #         tag += f"D({node}:{debtors[node]}),"
    #     return tag

    # def _update_memo(tag: str, res: LendingGraph, memo: Dict) -> None:
    #     if tag not in memo:
    #         memo[tag] = res
    #     else:
    #         if memo[tag].num_edges() > res.num_edges():
    #             memo[tag] = res

    def _dict_all_zero(dt) -> bool:
        for val in dt.values():
            if not is_zero(val):
                return False
        return True

    def _dp(
        creditors: defaultdict,
        debtors: defaultdict,
        cur_g: LendingGraph,
        # memo: Dict,
        ans: LendingGraph = None,
    ) -> LendingGraph:

        log.debug("=" * 20)
        log.debug("LEDNERS: ", creditors)
        log.debug("DEBTORS: ", debtors)
        log.debug("CUR_G:")
        log.debug(cur_g.vis())
        log.debug("ANS: ")
        if ans is not None:
            log.debug(ans.vis())

        # tag = _status_tag(creditors, debtors)

        if _dict_all_zero(creditors) and _dict_all_zero(debtors):
            log.debug("Last layer of recursion.")
            return (
                deepcopy(cur_g)
                if ans is None or cur_g.num_edges() < ans.num_edges()
                else ans
            )

        for ldr in creditors.keys():
            amount_ldr = creditors[ldr]
            if is_zero(amount_ldr):
                continue

            for dbr in debtors.keys():
                amount_dbr = debtors[dbr]
                if is_zero(amount_dbr):
                    continue

                amount = min(amount_ldr, amount_dbr)

                creditors[ldr] -= amount
                debtors[dbr] -= amount
                cur_g.add_edge(ldr, dbr, amount)

                ans = _dp(creditors, debtors, cur_g, ans)
                # if dp_ans != ans:
                #     ans = dp_ans
                # _update_memo(tag, cur_g)

                creditors[ldr] += amount
                debtors[dbr] += amount
                cur_g.add_edge(ldr, dbr, -amount)

        return ans

    creditors, debtors = defaultdict(float), defaultdict(float)
    for node, net_out in g.net_out_flow.items():
        if net_out > 0:
            creditors[node] = net_out
        elif net_out < 0:
            debtors[node] = -net_out

    equiv_g = _dp(creditors, debtors, LendingGraph())

    assert check_equiv(
        g, equiv_g
    ), f"G.NET_OUT = {g.net_out_flow}; EQ.NET_OUT = {equiv_g.net_out_flow}"

    return equiv_g
