"""Verify each discovered quote currency and convert prices into account USD."""
from datetime import datetime, timezone
import math
import yfinance as yf

class CurrencyConverter:
    def __init__(self):
        self.rates = {'USD': {'rate': 1., 'data_date': None}}
        self.currencies = {}

    def currency(self, ticker):
        if ticker not in self.currencies:
            currency = yf.Ticker(ticker).fast_info['currency']
            if currency == 'GBX':
                currency = 'GBp'
            if not currency:
                raise ValueError(f'{ticker}: missing quote currency')
            self.currencies[ticker] = currency
        return self.currencies[ticker]

    def convert(self, price, quote_currency):
        minor_units = {'GBp': 'GBP', 'ZAc': 'ZAR', 'ILA': 'ILS'}
        scale = .01 if quote_currency in minor_units else 1.
        currency = minor_units.get(quote_currency, quote_currency)
        if currency not in self.rates:
            frame = yf.download(currency + 'USD=X', period='5d', progress=False,
                                auto_adjust=True, multi_level_index=False, timeout=20)
            if frame is None or frame.empty:
                raise ValueError(f'No {currency}/USD exchange rate')
            values = frame['Close'].dropna()
            if values.empty:
                raise ValueError(f'No valid {currency}/USD exchange rate')
            date = values.index[-1]
            if (datetime.now(timezone.utc).date() - date.date()).days > 7:
                raise ValueError(f'Stale {currency}/USD exchange rate')
            rate = float(values.iloc[-1])
            if not math.isfinite(rate) or rate <= 0:
                raise ValueError(f'Invalid {currency}/USD exchange rate')
            self.rates[currency] = {'rate': rate, 'data_date': date.isoformat()}
        metadata = self.rates[currency]
        usd_price = price * scale * metadata['rate']
        if not math.isfinite(usd_price) or usd_price <= 0:
            raise ValueError('Invalid converted price')
        return {'price': usd_price, 'native_price': price, 'quote_currency': quote_currency,
                'quote_unit_scale': scale, 'fx_to_usd': metadata['rate'],
                'fx_date': metadata['data_date']}
