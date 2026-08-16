"""Graph data structure for lending flows."""

from .utils.logger import get_logger

from copy import deepcopy
import pandas as pd
from typing import List, Tuple, Dict
from collections import defaultdict
import math

logger = get_logger(__name__)

ABS_TOL = 1e-02


def is_equal(fp1, fp2):
    return math.isclose(fp1, fp2, abs_tol=ABS_TOL)


def is_zero(flt):
    return is_equal(flt, 0.0)


class LendingGraph:
    """A direct weighted graph, where weights are the lending flows."""

    def __init__(self, log=logger) -> None:
        self._adj_lt = defaultdict(lambda: defaultdict(float))
        self.net_out_flow = defaultdict(float)
        self.log = logger

    def vis(self) -> str:
        s = ""
        for creditor in self._adj_lt.keys():
            for debtor, amount in self._adj_lt[creditor].items():
                s += f"{creditor} --{amount:.2f}--> {debtor}\n"
        return s.strip()

    def get_nodes(self) -> List[str]:
        lt = set(self._adj_lt.keys())
        for creditor in self._adj_lt.keys():
            lt.update(list(self._adj_lt[creditor].keys()))
        return sorted(lt)

    def add_edge(self, creditor, debtor, amount) -> None:
        assert (
            creditor != debtor
        ), f"creditor and debtor ({creditor}) should not be the same one!"
        self._adj_lt[creditor][debtor] += amount
        self.net_out_flow[creditor] += amount
        self.net_out_flow[debtor] -= amount
        if is_zero(self._adj_lt[creditor][debtor]):
            self.remove_edge(creditor, debtor)

    def has_edge(self, creditor, debtor) -> bool:
        return creditor in self._adj_lt and debtor in self._adj_lt[creditor]

    def get_edge(self, creditor, debtor) -> float:
        assert self.has_edge(creditor, debtor)
        return self._adj_lt[creditor][debtor]

    def get_edges(self, creditor) -> List[Tuple]:
        return self._adj_lt[creditor]

    def num_edges(self) -> int:
        return sum(len(self._adj_lt[creditor]) for creditor in self._adj_lt)

    def get_flow(self, creditor, debtor) -> float:
        return self._adj_lt[creditor][debtor] if self.has_edge(creditor, debtor) else 0.0

    def remove_edge(self, creditor, debtor) -> float:
        amount = self.get_edge(creditor, debtor)
        self._adj_lt[creditor].pop(debtor, None)
        self.net_out_flow[creditor] -= amount
        self.net_out_flow[debtor] += amount
        return amount

    def get_childs(self, node) -> List[str]:
        return list(self._adj_lt[node].keys()) if node in self._adj_lt else []

    def dump(
        self,
        col_creditor: str = "Creditor",
        col_debtor: str = "Debtor",
        col_amount: str = "Amount",
        precision: int = 2,
    ) -> pd.DataFrame:
        # Create an empty DataFrame
        data_types = {
            col_creditor: "object",  # 'object' is typically used for strings
            col_debtor: "object",
            col_amount: "float64",  # 'float64' for floating point numbers
        }
        df = pd.DataFrame(columns=data_types.keys()).astype(data_types)

        for creditor in self._adj_lt:
            for debtor in self._adj_lt[creditor]:
                amount = round(self.get_flow(creditor, debtor), precision)
                new_row = pd.DataFrame(
                    [[creditor, debtor, amount]], columns=df.columns)
                df = pd.concat([df, new_row], ignore_index=True)

        return df


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


if __name__ == "__main__":
    pass
