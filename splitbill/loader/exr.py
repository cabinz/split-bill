"""Exchange rates to be used.

For example, the quotation EUR/USD = 1.25 means that 1 euro is exchanged for 1.25 USD.
It is read as "the exchange rate from USD to EUR is 1.25".
In this case, EUR is the base currency and USD is the quote currency (counter currency).

Args:
    base_currency: BASE * EXR = QUOTE
    quote_currency: BASE * EXR = QUOTE
    date: The date to get the exchange rate for. If None, the current date is used.
        The date should be in one of the ISO format, e.g. 'YYYY-MM-DD'.
"""

from collections import defaultdict

class ExchangeRates:
    def __init__(self, std_currency: str = "HKD") -> None:
        self.std_currency = std_currency
        self._rates = defaultdict(dict)
        # Every rate is stored in both directions, so _rates cannot say which way
        # round it was given. The report has to quote the rate that was actually
        # supplied -- somebody checking the arithmetic is looking for the number
        # they typed, not its reciprocal -- so the calls are recorded in order.
        self._registered = []

    def add_rate(self, base_currency: str, quote_currency: str, rate: float) -> None:
        if quote_currency in self._rates[base_currency]:
            raise ValueError(f"The exchange rate {base_currency}/{quote_currency} is already added.")
        self._rates[base_currency][quote_currency] = rate
        self._rates[quote_currency][base_currency] = 1 / rate
        self._registered.append((base_currency, quote_currency, rate))

    def registered(self) -> list:
        """The rates as supplied, in the order they were added."""
        return list(self._registered)
        
    def get_rate(self, base_currency: str, quote_currency: str) -> float:
        if base_currency == quote_currency:
            return 1.0
        if base_currency not in self._rates:
            raise ValueError(f"Exchange rate {base_currency}/{quote_currency} is NOT provided.")
        return self._rates[base_currency][quote_currency]

    def to_std(self, from_currency: str, amount: float) -> float:
        return amount * self.get_rate(from_currency, self.std_currency)
