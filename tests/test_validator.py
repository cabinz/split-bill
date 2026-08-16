"""Test cases for the validator module."""

import pytest
import pandas as pd
from io import StringIO

from splitbill.loader.validator import (DataValidator, ValidationResult,
                                        ValidationError, Severity)
from splitbill.loader import DataFormat, ExchangeRates
from splitbill.config import DataColumn


class TestValidationError:
    """Test ValidationError class."""
    
    def test_error_with_row_and_column(self):
        error = ValidationError(2, "Amount", "Invalid value", Severity.ERROR)
        assert str(error) == "  ✗ Row 2, Column 'Amount': Invalid value"
    
    def test_error_with_row_only(self):
        error = ValidationError(3, None, "Missing data", Severity.ERROR)
        assert str(error) == "  ✗ Row 3: Missing data"
    
    def test_error_without_row(self):
        error = ValidationError(None, None, "General error", Severity.ERROR)
        assert str(error) == "  ✗ General error"
    
    def test_warning(self):
        warning = ValidationError(5, "Amount", "Zero amount", Severity.WARNING)
        assert str(warning) == "  ⚠ Row 5, Column 'Amount': Zero amount"


class TestValidationResult:
    """Test ValidationResult class."""
    
    def test_add_error(self):
        result = ValidationResult()
        result.add_error(2, "Amount", "Invalid amount")
        
        assert len(result.errors) == 1
        assert result.has_errors()
        assert not result.has_warnings()
    
    def test_add_warning(self):
        result = ValidationResult()
        result.add_warning(3, "Amount", "Zero amount")
        
        assert len(result.warnings) == 1
        assert not result.has_errors()
        assert result.has_warnings()
    
    def test_get_all_issues(self):
        result = ValidationResult()
        result.add_error(2, "Amount", "Invalid")
        result.add_warning(3, "Amount", "Zero")
        
        issues = result.get_all_issues()
        assert len(issues) == 2


class TestDataValidator:
    """Test DataValidator class."""
    
    @pytest.fixture
    def sample_df(self):
        """Create a sample DataFrame for testing."""
        data = """Creditor,Debtor,Amount,Currency
Alice,Bob,100,USD
Charlie,David,200,EUR
Emily,Frank,300,USD"""
        return pd.read_csv(StringIO(data))
    
    @pytest.fixture
    def data_format(self):
        """Create default DataFormat."""
        return DataFormat()
    
    def test_validate_structure_success(self, sample_df, data_format):
        """Test structure validation with all required columns."""
        validator = DataValidator(sample_df, data_format)
        result = validator.validate()
        assert not result.has_errors()
    
    def test_validate_structure_missing_columns(self, data_format):
        """Test structure validation with missing columns."""
        df = pd.DataFrame({"Creditor": ["Alice"], "Amount": [100]})
        validator = DataValidator(df, data_format)
        result = validator.validate()

        assert result.has_errors()
        assert any("Could not auto-detect" in str(e) for e in result.errors)

    def test_validate_user_specified_wrong_column(self):
        """Test error message when user specifies wrong column name."""
        # Data has "参与人" column, but user specifies "Payee"
        df = pd.DataFrame({
            "Creditor": ["Alice"],
            "参与人": ["Bob"],
            "Amount": [100],
            "Currency": ["USD"]
        })
        # Create DataFormat with user_specified_columns indicating debtor was user-specified
        data_format = DataFormat(
            col_creditor="Creditor",
            col_debtor="Payee",  # Wrong column name
            col_tot_amount="Amount",
            col_currency="Currency",
            user_specified_columns={DataColumn.DEBTOR}
        )
        validator = DataValidator(df, data_format)
        result = validator.validate()

        assert result.has_errors()
        # Should report "Specified column(s) not found" instead of "Could not auto-detect"
        error_msg = str(result.errors[0])
        assert "Specified column(s) not found" in error_msg
        assert "'Payee'" in error_msg
        assert "Available columns" in error_msg

    def test_validate_empty_creditor(self, data_format):
        """Test validation with empty creditor."""
        data = """Creditor,Debtor,Amount,Currency
,Bob,100,USD
Alice,Charlie,200,EUR"""
        df = pd.read_csv(StringIO(data))
        
        validator = DataValidator(df, data_format)
        result = validator.validate()
        
        assert result.has_errors()
        assert any("Creditor cannot be empty" in str(e) for e in result.errors)
    
    def test_validate_empty_debtor(self, data_format):
        """Test validation with empty debtor."""
        data = """Creditor,Debtor,Amount,Currency
Alice,,100,USD
Bob,Charlie,200,EUR"""
        df = pd.read_csv(StringIO(data))
        
        validator = DataValidator(df, data_format)
        result = validator.validate()
        
        assert result.has_errors()
        assert any("did you mean 'all'" in str(e) for e in result.errors)
    
    def test_validate_negative_amount(self, data_format):
        """Test validation with negative amount."""
        data = """Creditor,Debtor,Amount,Currency
Alice,Bob,-100,USD
Charlie,David,200,EUR"""
        df = pd.read_csv(StringIO(data))
        
        validator = DataValidator(df, data_format)
        result = validator.validate()
        
        assert result.has_errors()
        assert any("Amount cannot be negative" in str(e) for e in result.errors)
    
    def test_validate_zero_amount(self, data_format):
        """Test validation with zero amount."""
        data = """Creditor,Debtor,Amount,Currency
Alice,Bob,0,USD
Charlie,David,200,EUR"""
        df = pd.read_csv(StringIO(data))
        
        validator = DataValidator(df, data_format)
        result = validator.validate()
        
        assert result.has_warnings()
        assert any("Amount is 0" in str(w) for w in result.warnings)
    
    def test_validate_invalid_amount(self, data_format):
        """Test validation with non-numeric amount."""
        data = """Creditor,Debtor,Amount,Currency
Alice,Bob,abc,USD
Charlie,David,200,EUR"""
        df = pd.read_csv(StringIO(data))
        
        validator = DataValidator(df, data_format)
        result = validator.validate()
        
        assert result.has_errors()
        assert any("Invalid amount value" in str(e) for e in result.errors)
    
    def test_validate_missing_currency(self, data_format):
        """Test validation with missing currency when exchange rates are provided."""
        data = """Creditor,Debtor,Amount,Currency
Alice,Bob,100,
Charlie,David,200,EUR"""
        df = pd.read_csv(StringIO(data))
        
        exrs = ExchangeRates("USD")
        exrs.add_rate("EUR", "USD", 1.1)
        
        validator = DataValidator(df, data_format, exrs)
        result = validator.validate()
        
        assert result.has_errors()
        assert any("Currency cannot be empty" in str(e) for e in result.errors)
    
    def test_validate_missing_exchange_rate(self, data_format):
        """Test validation with missing exchange rate."""
        data = """Creditor,Debtor,Amount,Currency
Alice,Bob,100,USD
Charlie,David,200,JPY"""
        df = pd.read_csv(StringIO(data))
        
        exrs = ExchangeRates("USD")
        # Not adding JPY/USD rate
        
        validator = DataValidator(df, data_format, exrs)
        result = validator.validate()
        
        assert result.has_errors()
        assert any("has no exchange rate" in str(e) for e in result.errors)
        assert any("Missing exchange rates: JPY/USD" in str(e) for e in result.errors)
    
    def test_validate_multiple_creditors(self, data_format):
        """Test validation with multiple creditors."""
        data = """Creditor,Debtor,Amount,Currency
Alice,Bob,100,USD
"Charlie,David",Emily,200,USD"""
        df = pd.read_csv(StringIO(data))
        
        validator = DataValidator(df, data_format)
        result = validator.validate()
        
        assert result.has_errors()
        assert any("Multiple creditors not supported" in str(e) for e in result.errors)
    
    def test_validate_all_as_creditor(self, data_format):
        """Test validation with 'all' as creditor."""
        data = """Creditor,Debtor,Amount,Currency
all,Bob,100,USD
Alice,Charlie,200,USD"""
        df = pd.read_csv(StringIO(data))
        
        validator = DataValidator(df, data_format)
        result = validator.validate()
        
        assert result.has_errors()
        assert any("'all' cannot be used as creditor" in str(e) for e in result.errors)
    
    def test_validate_all_with_empty_members(self, data_format):
        """Test validation with 'all' when no members exist."""
        data = """Creditor,Debtor,Amount,Currency
all,all,100,USD"""
        df = pd.read_csv(StringIO(data))
        
        validator = DataValidator(df, data_format)
        result = validator.validate()
        
        assert result.has_errors()
        # Should have error for creditor being 'all'
        assert any("'all' cannot be used as creditor" in str(e) for e in result.errors)
    
    def test_validate_empty_member_after_split(self, data_format):
        """Test validation with empty member name after splitting."""
        data = """Creditor,Debtor,Amount,Currency
Alice,"Bob,,Charlie",100,USD"""
        df = pd.read_csv(StringIO(data))
        
        validator = DataValidator(df, data_format)
        result = validator.validate()
        
        assert result.has_errors()
        assert any("Empty member name after splitting" in str(e) for e in result.errors)

    def test_validate_mismatched_name_separator(self, data_format):
        """A suspected delimiter mistake is visible without blocking analysis."""
        data = '''Creditor,Debtor,Amount,Currency
Alice,"Alice, Bob",100,USD'''
        df = pd.read_csv(StringIO(data))
        data_format.separator = ";"

        result = DataValidator(df, data_format).validate()

        assert not result.has_errors()
        assert result.has_warnings()
        finding = next(
            warning for warning in result.warnings
            if "may use ',' as the name separator" in warning.message
        )
        assert finding.row == 2
        assert finding.column == data_format.col_debtor

    def test_validate_empty_name_separator_as_a_finding(self, data_format):
        """An empty separator is a correctable option error, not an exception."""
        df = pd.read_csv(StringIO(
            "Creditor,Debtor,Amount,Currency\nAlice,Bob,100,USD\n"
        ))
        data_format.separator = ""

        result = DataValidator(df, data_format).validate()

        assert result.has_errors()
        assert any("Name separator cannot be empty" in e.message
                   for e in result.errors)
    
    def test_validate_complex_scenario(self, data_format):
        """Test validation with multiple types of errors."""
        data = """Creditor,Debtor,Amount,Currency
Alice,Bob,100,USD
,Charlie,200,EUR
David,,300,JPY
Emily,Frank,-50,USD
George,Helen,0,GBP
Isaac,Jane,abc,USD"""
        df = pd.read_csv(StringIO(data))
        
        exrs = ExchangeRates("USD")
        exrs.add_rate("EUR", "USD", 1.1)
        exrs.add_rate("GBP", "USD", 1.3)
        # Not adding JPY rate
        
        validator = DataValidator(df, data_format, exrs)
        result = validator.validate()
        
        assert result.has_errors()
        assert result.has_warnings()
        
        # Check for various error types
        error_messages = [str(e) for e in result.errors]
        warning_messages = [str(w) for w in result.warnings]
        
        assert any("Creditor cannot be empty" in msg for msg in error_messages)
        assert any("did you mean 'all'" in msg for msg in error_messages)
        assert any("has no exchange rate" in msg for msg in error_messages)
        assert any("Amount cannot be negative" in msg for msg in error_messages)
        assert any("Invalid amount value" in msg for msg in error_messages)
        assert any("Amount is 0" in msg for msg in warning_messages)


class TestIntegration:
    """Integration tests for validation with real data."""
    
    def test_validate_sample_data_without_exchange_rates(self):
        """Test validation of sample data without exchange rates."""
        data = """Creditor,Debtor,Amount,Currency
Alice,Bob,100000,KRW
Bob,all,50000,KRW
Charlie,David,200000,KRW"""
        df = pd.read_csv(StringIO(data))
        
        exrs = ExchangeRates("HKD")
        # Not providing KRW/HKD rate
        
        validator = DataValidator(df, DataFormat(), exrs)
        result = validator.validate()
        
        assert result.has_errors()
        assert any("KRW" in str(e) and "HKD" in str(e) for e in result.errors)
    
    def test_validate_sample_data_with_exchange_rates(self):
        """Test validation of sample data with proper exchange rates."""
        data = """Creditor,Debtor,Amount,Currency
Alice,Bob,100000,KRW
Bob,all,50000,KRW
Charlie,David,200000,KRW"""
        df = pd.read_csv(StringIO(data))
        
        exrs = ExchangeRates("HKD")
        exrs.add_rate("KRW", "HKD", 0.0057715)
        
        validator = DataValidator(df, DataFormat(), exrs)
        result = validator.validate()
        
        assert not result.has_errors()
        assert not result.has_warnings()
