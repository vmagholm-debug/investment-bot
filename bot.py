import yfinance as yf
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import accuracy_score
import time
import json
from pathlib import Path
import argparse
from datetime import datetime, timedelta

class TenPercentMonthlyBot:
    def __init__(self, tickers, min_monthly_return=0.10, api_key=None):
        self.tickers = tickers
        self.min_monthly_return = min_monthly_return
        self.api_key = api_key
        self.models = {}
        self.accuracy_scores = {}
        self.portfolio = {}
        self.cash = 100000.0
        self.trade_log = []
        self.lookback_days = 730
        self.prediction_horizon = 21
        self.min_confidence = 0.80
        self.min_accuracy = 0.75
        self.leverage = 1.0
        self.data = {}
        self.features = ['SMA_5', 'SMA_20', 'SMA_50', 'SMA_200', 'RSI', 'Volatility',
                         'Volume_Change', 'MACD', 'ATR', 'Momentum', 'Return']
        self.last_purchase_dates = {}
        self.last_prices = {}

    def load_state(self, path):
        if not path.exists():
            return
        state = json.loads(path.read_text())
        if state.get('version') != 1:
            raise ValueError('Unsupported paper account state')
        cash = float(state['cash'])
        portfolio = {k: float(v) for k, v in state['portfolio'].items()}
        if not np.isfinite(cash) or cash < 0 or any(
                not np.isfinite(v) or v < 0 for v in portfolio.values()):
            raise ValueError('Invalid paper account balances')
        self.cash = cash
        self.portfolio = portfolio
        self.trade_log = state['trade_log']
        self.last_purchase_dates = state['last_purchase_dates']
        self.last_prices = state['last_prices']

    def save_state(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps({
            'version': 1, 'cash': self.cash, 'portfolio': self.portfolio,
            'trade_log': self.trade_log, 'last_purchase_dates': self.last_purchase_dates,
            'last_prices': self.last_prices}, indent=2, allow_nan=False) + '\n')
        temporary.replace(path)

    def fetch_data(self, ticker):
        if ticker in self.data:
            return self.data[ticker]
        end = datetime.now()
        start = end - timedelta(days=self.lookback_days)
        df = yf.download(ticker, start=start, end=end, progress=False,
                         auto_adjust=True, multi_level_index=False, timeout=20)
        if df is None or df.empty:
            raise ValueError(f"No data for {ticker}")
        df['Return'] = df['Close'].pct_change(fill_method=None)
        df['SMA_5'] = df['Close'].rolling(5).mean()
        df['SMA_20'] = df['Close'].rolling(20).mean()
        df['SMA_50'] = df['Close'].rolling(50).mean()
        df['SMA_200'] = df['Close'].rolling(200).mean()
        df['EMA_12'] = df['Close'].ewm(span=12).mean()
        df['EMA_26'] = df['Close'].ewm(span=26).mean()
        df['MACD'] = df['EMA_12'] - df['EMA_26']
        df['RSI'] = self.compute_rsi(df['Close'], 14)
        df['Volatility'] = df['Return'].rolling(20).std()
        df['Volume_Change'] = df['Volume'].pct_change(fill_method=None)
        df['ATR'] = self.compute_atr(df, 14)
        df['Momentum'] = df['Close'] - df['Close'].shift(21)
        df['Forward_Return_21d'] = df['Close'].shift(-self.prediction_horizon) / df['Close'] - 1
        df['Target'] = (df['Forward_Return_21d'] >= self.min_monthly_return).astype(float)
        df.loc[df['Forward_Return_21d'].isna(), 'Target'] = np.nan
        df.replace([np.inf, -np.inf], np.nan, inplace=True)
        # Preserve the most recent rows for inference; they have no future labels.
        df.dropna(subset=self.features, inplace=True)
        if df.empty:
            raise ValueError(f"Insufficient feature history for {ticker}")
        self.data[ticker] = df
        return df

    def compute_rsi(self, series, period=14):
        delta = series.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)
        avg_gain = gain.rolling(window=period).mean()
        avg_loss = loss.rolling(window=period).mean()
        rs = avg_gain / (avg_loss + 1e-9)
        return 100 - (100 / (1 + rs))

    def compute_atr(self, df, period=14):
        high_low = df['High'] - df['Low']
        high_close = (df['High'] - df['Close'].shift()).abs()
        low_close = (df['Low'] - df['Close'].shift()).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        return tr.rolling(period).mean()

    def train_model(self, ticker):
        df = self.fetch_data(ticker).dropna(subset=['Target'])
        features = ['SMA_5', 'SMA_20', 'SMA_50', 'SMA_200', 'RSI', 'Volatility',
                    'Volume_Change', 'MACD', 'ATR', 'Momentum', 'Return']
        X = df[features].values
        y = df['Target'].values
        split = int(len(df) * 0.8)
        # Purge overlapping future labels across the chronological split.
        train_end = split - self.prediction_horizon
        if train_end < 30 or len(df) - split < 10:
            raise ValueError(f"Insufficient labeled history for {ticker}")
        X_train, X_test = X[:train_end], X[split:]
        y_train, y_test = y[:train_end], y[split:]
        if len(np.unique(y_train)) < 2:
            raise ValueError(f"Training history for {ticker} has only one target class")
        model = GradientBoostingClassifier(n_estimators=800, max_depth=6, learning_rate=0.03, random_state=42)
        model.fit(X_train, y_train)
        preds = model.predict(X_test)
        acc = accuracy_score(y_test, preds)
        self.models[ticker] = model
        self.accuracy_scores[ticker] = acc
        # Score on the holdout first, then fit all known labels for today's signal.
        model.fit(X, y)
        return acc

    def predict(self, ticker):
        if ticker not in self.models:
            self.train_model(ticker)
        df = self.fetch_data(ticker)
        features = ['SMA_5', 'SMA_20', 'SMA_50', 'SMA_200', 'RSI', 'Volatility',
                    'Volume_Change', 'MACD', 'ATR', 'Momentum', 'Return']
        latest = df[features].iloc[-1].values.reshape(1, -1)
        model = self.models[ticker]
        proba = model.predict_proba(latest)[0]
        confidence = float(proba[1])
        historical_monthly = float(df['Forward_Return_21d'].dropna().tail(60).mean())
        return {
            'ticker': ticker,
            'direction': 'BUY' if confidence >= self.min_confidence else 'HOLD',
            'confidence': confidence,
            'accuracy': self.accuracy_scores.get(ticker, 0.0),
            'historical_mean_21d_return': historical_monthly,
            'data_date': df.index[-1].isoformat(),
            'timestamp': datetime.now().isoformat()
        }

    def advise(self, signal):
        if signal['confidence'] < self.min_confidence:
            return None
        if signal['accuracy'] < self.min_accuracy:
            return None
        if signal['historical_mean_21d_return'] < self.min_monthly_return:
            return None
        if signal['direction'] != 'BUY':
            return None
        # At most 10% of remaining fake cash per purchase, no borrowing.
        base = self.cash * 0.10
        position = min(base * self.leverage, self.cash)
        if position < 1:
            return None
        return {
            'ticker': signal['ticker'],
            'action': 'PAPER BUY',
            'amount': position,
            'confidence': signal['confidence'],
            'accuracy': signal['accuracy'],
            'historical_mean_21d_return': signal['historical_mean_21d_return']
        }

    def execute(self, order, price):
        if order is None:
            return
        if not np.isfinite(price) or price <= 0:
            raise ValueError('Invalid paper trade price')
        if not 0 < order['amount'] <= self.cash:
            raise ValueError('Paper order exceeds available cash')
        ticker = order['ticker']
        qty = order['amount'] / price
        self.portfolio[ticker] = self.portfolio.get(ticker, 0) + qty
        self.cash -= order['amount']
        self.last_purchase_dates[ticker] = self.data[ticker].index[-1].isoformat()
        self.trade_log.append({
            'time': datetime.now().isoformat(),
            'ticker': ticker,
            'action': 'PAPER BUY',
            'qty': qty,
            'price': price,
            'amount': order['amount'],
            'currency': 'USD',
            'quote': self.last_prices.get(ticker, {}),
            'reason': order.get('reason', 'Configured signal filters passed'),
            'research_gate': order.get('research_gate'),
            'confidence': order['confidence'],
            'accuracy': order['accuracy'],
            'historical_mean_21d_return': order['historical_mean_21d_return']
        })

    def price_quote(self, ticker, df):
        return {'price': float(df['Close'].iloc[-1]),
                'data_date': df.index[-1].isoformat()}

    def run_once(self, refresh=True):
        if refresh:
            self.data.clear()
        self.models.clear()
        self.accuracy_scores.clear()
        advice = []
        for ticker in self.tickers:
            try:
                df = self.fetch_data(ticker)
                self.last_prices[ticker] = self.price_quote(ticker, df)
                sig = self.predict(ticker)
                order = self.advise(sig)
                if self.last_purchase_dates.get(ticker) == sig['data_date']:
                    advice.append({**sig, 'action': 'NO TRADE',
                                   'reason': 'Already purchased on this price date'})
                    continue
                if order:
                    price = self.last_prices[ticker]['price']
                    self.execute(order, price)
                    advice.append(order)
                else:
                    advice.append({**sig, 'action': 'NO TRADE', 'reason': sig.get('reason', 'One or more configured filters were not met')})
            except Exception as e:
                advice.append({'ticker': ticker, 'error': str(e)})
        return advice

    def run_forever(self, interval_seconds=86400):
        while True:
            self.run_once()
            time.sleep(interval_seconds)

if __name__ == "__main__":
    tickers = ["TQQQ", "SOXL", "UPRO", "SPXL", "TECL", "FNGU", "LABU", "YINN", "UDOW", "NAIL"]
    parser = argparse.ArgumentParser(description='One-shot experimental paper-trading report')
    parser.add_argument('--tickers', nargs='+', default=tickers)
    parser.add_argument('--output', default='reports/latest.json')
    parser.add_argument('--state', default='state.json')
    args = parser.parse_args()
    yf.set_tz_cache_location(str(Path(args.state).parent / '.cache' / 'yfinance'))
    bot = TenPercentMonthlyBot(args.tickers, min_monthly_return=0.10)
    bot.load_state(Path(args.state))
    # Continue valuing existing holdings even if the configured ticker list changes.
    bot.tickers = list(dict.fromkeys(args.tickers + list(bot.portfolio)))
    advice = bot.run_once()
    bot.save_state(Path(args.state))
    holdings_value = sum(qty * bot.last_prices[ticker]['price']
                         for ticker, qty in bot.portfolio.items())
    report = {'mode': 'persistent paper simulation; fake USD only',
              'generated_at': datetime.now().isoformat(),
              'starting_cash': 100000.0, 'remaining_cash': bot.cash,
              'holdings_value': holdings_value,
              'total_account_value': bot.cash + holdings_value,
              'profit_loss': bot.cash + holdings_value - 100000.0,
              'valuation_prices': bot.last_prices,
              'results': advice, 'portfolio': bot.portfolio, 'trades': bot.trade_log}
    rendered = json.dumps(report, indent=2, allow_nan=False)
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(rendered + '\n')
    print(rendered, flush=True)
    raise SystemExit(1 if any('error' in result for result in advice) else 0)
