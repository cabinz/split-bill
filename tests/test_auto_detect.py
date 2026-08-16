"""Test auto-detection of column names."""

import pytest
import pandas as pd
import tempfile
import os
from pathlib import Path
from splitbill.loader import ColumnBinding, DataFormat
from splitbill.config import (
    CREDITOR_ALIASES, DEBTOR_ALIASES, AMOUNT_ALIASES, CURRENCY_ALIASES,
    CATEGORY_ALIASES,
    DataColumn
)


class TestAutoDetection:
    """Test cases for column name auto-detection."""
    
    def test_detect_payer_payee_columns(self):
        """Test auto-detection of Payer/Payee columns."""
        # Create DataFrame with Payer/Payee columns
        df = pd.DataFrame({
            "Payer": ["Alice", "Bob"],
            "Payee": ["Bob", "Charlie"],
            "Amount": [100, 50],
            "Currency": ["USD", "USD"]
        })
        
        # Test auto-detection
        detected = DataFormat.auto_detect_column(df.columns.tolist(), CREDITOR_ALIASES)
        assert detected == "Payer"
        
        detected = DataFormat.auto_detect_column(df.columns.tolist(), DEBTOR_ALIASES)
        assert detected == "Payee"
    
    def test_detect_creditor_debtor_columns(self):
        """Test auto-detection of Creditor/Debtor columns."""
        df = pd.DataFrame({
            "Creditor": ["Alice", "Bob"],
            "Debtor": ["Bob", "Charlie"],
            "Amount": [100, 50],
            "Currency": ["USD", "USD"]
        })
        
        detected = DataFormat.auto_detect_column(df.columns.tolist(), CREDITOR_ALIASES)
        assert detected == "Creditor"
        
        detected = DataFormat.auto_detect_column(df.columns.tolist(), DEBTOR_ALIASES)
        assert detected == "Debtor"
    
    def test_case_insensitive_detection(self):
        """Test that detection is case-insensitive."""
        # Test with uppercase
        df = pd.DataFrame({
            "PAYER": ["Alice"],
            "PAYEE": ["Bob"],
            "AMOUNT": [100],
            "CURRENCY": ["USD"]
        })
        
        detected = DataFormat.auto_detect_column(df.columns.tolist(), CREDITOR_ALIASES)
        assert detected == "PAYER"
        
        # Test with lowercase
        df = pd.DataFrame({
            "payer": ["Alice"],
            "payee": ["Bob"],
            "amount": [100],
            "currency": ["USD"]
        })
        
        detected = DataFormat.auto_detect_column(df.columns.tolist(), CREDITOR_ALIASES)
        assert detected == "payer"
        
        # Test with mixed case
        df = pd.DataFrame({
            "PaYeR": ["Alice"],
            "PaYeE": ["Bob"],
            "AmOuNt": [100],
            "CuRrEnCy": ["USD"]
        })
        
        detected = DataFormat.auto_detect_column(df.columns.tolist(), CREDITOR_ALIASES)
        assert detected == "PaYeR"
    
    def test_mixed_columns_detection(self):
        """Test detection when mixing Payer with Debtor (not Payee)."""
        df = pd.DataFrame({
            "Payer": ["Alice"],
            "Debtor": ["Bob"],  # Mixed: Payer + Debtor
            "Amount": [100],
            "Currency": ["USD"]
        })
        
        detected = DataFormat.auto_detect_column(df.columns.tolist(), CREDITOR_ALIASES)
        assert detected == "Payer"
        
        detected = DataFormat.auto_detect_column(df.columns.tolist(), DEBTOR_ALIASES)
        assert detected == "Debtor"
    
    def test_no_match_returns_none(self):
        """Test that None is returned when no matching column is found."""
        df = pd.DataFrame({
            "Sender": ["Alice"],      # Not in CREDITOR_ALIASES
            "Receiver": ["Bob"],      # Not in DEBTOR_ALIASES
            "Price": [100],           # Not in AMOUNT_ALIASES
            "Money": ["USD"]          # Not in CURRENCY_ALIASES
        })

        detected = DataFormat.auto_detect_column(df.columns.tolist(), CREDITOR_ALIASES)
        assert detected is None

        detected = DataFormat.auto_detect_column(df.columns.tolist(), DEBTOR_ALIASES)
        assert detected is None
    
    def test_priority_order(self):
        """Test that aliases are checked in priority order."""
        # When both Creditor and Payer exist, Creditor should be selected (first in list)
        df = pd.DataFrame({
            "Creditor": ["Alice"],
            "Payer": ["Bob"],
            "Debtor": ["Charlie"],
            "Amount": [100],
        })
        
        detected = DataFormat.auto_detect_column(df.columns.tolist(), CREDITOR_ALIASES)
        assert detected == "Creditor"  # Should pick Creditor over Payer
        
        # When both Debtor and Payee exist, Debtor should be selected (first in list)
        df = pd.DataFrame({
            "Debtor": ["Alice"],
            "Payee": ["Bob"],
            "Amount": [100],
        })
        
        detected = DataFormat.auto_detect_column(df.columns.tolist(), DEBTOR_ALIASES)
        assert detected == "Debtor"  # Should pick Debtor over Payee

    def test_category_aliases_are_auto_detected(self):
        df = pd.DataFrame({
            "付款人": ["Alice"],
            "参与人": ["Bob"],
            "金额": [100],
            "分类": ["餐饮"],
        })

        detected = DataFormat.auto_detect_column(
            df.columns.tolist(), CATEGORY_ALIASES)

        assert detected == "分类"

    def test_optional_category_can_be_overridden_or_disabled(self):
        from argparse import Namespace

        args = Namespace(
            col_creditor=None,
            col_debtor=None,
            col_tot_amount=None,
            col_currency=None,
            separator=",",
            all_selector="all",
        )
        df = pd.DataFrame({
            "Creditor": ["Alice"],
            "Debtor": ["Bob"],
            "Amount": [100],
            "Type": ["wrong guess"],
            "Spending bucket": ["Food"],
        })

        overridden = DataFormat.from_args_with_auto_detect(
            args, df, descriptive_overrides={"category": "Spending bucket"})
        disabled = DataFormat.from_args_with_auto_detect(
            args, df, descriptive_overrides={"category": None})

        assert overridden.col_category == "Spending bucket"
        assert overridden.bindings["category"] == ColumnBinding(
            "Spending bucket", auto=False)
        assert disabled.col_category is None
        assert disabled.bindings["category"] == ColumnBinding(None, auto=False)
    
    def test_from_args_with_auto_detect(self):
        """Test the from_args_with_auto_detect method."""
        from argparse import Namespace

        # Create mock args with None values (not user-specified)
        args = Namespace(
            col_creditor=None,      # Not specified, should auto-detect
            col_debtor=None,        # Not specified, should auto-detect
            col_tot_amount=None,    # Not specified, should auto-detect
            col_currency=None,      # Not specified, should auto-detect
            separator=",",
            all_selector="all"
        )

        # Create DataFrame with Payer/Payee columns
        df = pd.DataFrame({
            "Payer": ["Alice"],
            "Payee": ["Bob"],
            "Amount": [100],
            "Currency": ["USD"]
        })

        # Test auto-detection
        data_format = DataFormat.from_args_with_auto_detect(args, df)

        # Should detect Payer and Payee
        assert data_format.col_creditor == "Payer"
        assert data_format.col_debtor == "Payee"
        assert data_format.col_tot_amount == "Amount"
        assert data_format.col_currency == "Currency"
        # None of these should be marked as user-specified
        assert len(data_format.user_specified_columns) == 0
    
    def test_user_override_takes_precedence(self):
        """Test that user-specified columns override auto-detection."""
        from argparse import Namespace

        # Create mock args with user-specified values
        args = Namespace(
            col_creditor="From",      # User-specified
            col_debtor="To",          # User-specified
            col_tot_amount="Value",   # User-specified
            col_currency="Curr",      # User-specified
            separator=",",
            all_selector="all"
        )

        # Create DataFrame with Payer/Payee columns (which would normally be detected)
        df = pd.DataFrame({
            "Payer": ["Alice"],
            "Payee": ["Bob"],
            "From": ["Charlie"],
            "To": ["David"],
            "Amount": [100],
            "Value": [200],
            "Currency": ["USD"],
            "Curr": ["EUR"]
        })

        # Test that user-specified values take precedence
        data_format = DataFormat.from_args_with_auto_detect(args, df)

        # Should use user-specified columns, not auto-detected ones
        assert data_format.col_creditor == "From"
        assert data_format.col_debtor == "To"
        assert data_format.col_tot_amount == "Value"
        assert data_format.col_currency == "Curr"
        # All should be marked as user-specified
        assert data_format.user_specified_columns == {
            DataColumn.CREDITOR, DataColumn.DEBTOR, DataColumn.AMOUNT, DataColumn.CURRENCY
        }
