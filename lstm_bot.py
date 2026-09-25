"""Bounded daily LSTM learning and persistent fake-money purchases."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import random

import numpy as np
import torch
from torch import nn
import yfinance as yf

from bot import TenPercentMonthlyBot


class LSTMModel(nn.Module):
    def __init__(self, input_size=10, hidden_size=128, num_layers=2, dropout=.2):
        super().__init__()
        self.lstm = nn.LSTM(input_size, hidden_size, num_layers,
                            batch_first=True, dropout=dropout)
        self.fc = nn.Sequential(nn.Linear(hidden_size, 64), nn.ReLU(),
                                nn.Dropout(dropout), nn.Linear(64, 1), nn.Sigmoid())

    def forward(self, x):
        output, _ = self.lstm(x)
        return self.fc(output[:, -1, :])


class ContinuousLearner(TenPercentMonthlyBot):
    def __init__(self, tickers, checkpoint=Path('model.pt'), steps=20):
        super().__init__(tickers)
        torch.set_num_threads(2)
        torch.manual_seed(42)
        random.seed(42)
        self.features.remove('SMA_200')
        self.seq_len = 30
        self.checkpoint = Path(checkpoint)
        self.steps = steps
        self.model = LSTMModel()  # CPU works on standard free GitHub runners.
        self.optimizer = torch.optim.Adam(self.model.parameters(), lr=1e-4)
        self.buffer = []
        self.seen = set()
        self.training_steps = 0
        self.last_loss = None
        if self.checkpoint.exists():
            saved = torch.load(self.checkpoint, map_location='cpu', weights_only=True)
            if saved['version'] != 1:
                raise ValueError('Unsupported model checkpoint')
            self.model.load_state_dict(saved['model'])
            self.optimizer.load_state_dict(saved['optimizer'])
            self.buffer = saved['buffer']
            self.seen = set(saved['seen'])
            self.training_steps = saved['training_steps']
            self.last_loss = saved['last_loss']

    @staticmethod
    def normalize(sequence):
        # Each window uses only its own past observations, with no fitted scaler
        # that can drift out of sync with persisted model/replay tensors.
        sequence = np.asarray(sequence, dtype=np.float32)
        return (sequence - sequence.mean(axis=0)) / np.maximum(sequence.std(axis=0), 1e-6)

    def update_model(self, ticker):
        df = self.fetch_data(ticker)
        features = df[self.features].to_numpy()
        added = 0
        for end in range(self.seq_len - 1, len(df)):
            key = ticker + ':' + df.index[end].isoformat()
            target = df['Target'].iloc[end]
            if np.isnan(target) or key in self.seen:
                continue
            sequence = self.normalize(features[end - self.seq_len + 1:end + 1])
            self.buffer.append((torch.from_numpy(sequence), float(target)))
            self.seen.add(key)
            added += 1
        self.buffer = self.buffer[-20000:]
        return added

    def learn(self):
        errors = {}
        added = 0
        for ticker in self.tickers:
            try:
                added += self.update_model(ticker)
            except Exception as exc:
                errors[ticker] = str(exc)
        # Avoid training over and over on the same data when manually rerun.
        if added and len(self.buffer) >= 64:
            self.model.train()
            loss_fn = nn.BCELoss()
            for _ in range(self.steps):
                batch = random.sample(self.buffer, min(64, len(self.buffer)))
                states = torch.stack([entry[0] for entry in batch])
                targets = torch.tensor([entry[1] for entry in batch]).unsqueeze(1)
                self.optimizer.zero_grad()
                loss = loss_fn(self.model(states), targets)
                if not torch.isfinite(loss):
                    raise ValueError('Non-finite training loss')
                loss.backward()
                nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)
                self.optimizer.step()
                self.training_steps += 1
                self.last_loss = float(loss.item())
        return errors

    def save_model(self):
        self.checkpoint.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.checkpoint.with_suffix('.tmp')
        torch.save({'version': 1, 'model': self.model.state_dict(),
                    'optimizer': self.optimizer.state_dict(), 'buffer': self.buffer,
                    'seen': sorted(self.seen), 'training_steps': self.training_steps,
                    'last_loss': self.last_loss}, temporary)
        temporary.replace(self.checkpoint)

    def predict(self, ticker):
        df = self.fetch_data(ticker)
        if self.training_steps == 0 or len(df) < self.seq_len:
            raise ValueError('Not enough labeled history to train the LSTM yet')
        sequence = self.normalize(df[self.features].tail(self.seq_len).to_numpy())
        self.model.eval()
        with torch.no_grad():
            probability = float(self.model(torch.from_numpy(sequence).unsqueeze(0)).item())
        return {'ticker': ticker, 'direction': 'BUY' if probability > .8 else 'HOLD',
                'confidence': probability, 'accuracy': None,
                'historical_mean_21d_return': float(df['Forward_Return_21d'].dropna().tail(60).mean()),
                'data_date': df.index[-1].isoformat(),
                'timestamp': datetime.now().isoformat()}

    def advise(self, signal):
        # The supplied LSTM uses a >0.8 score filter. No unmeasured accuracy claim.
        amount = self.cash * .1
        if signal['direction'] != 'BUY' or amount < 1:
            return None
        return {**signal, 'action': 'PAPER BUY', 'amount': amount}


def main():
    parser = argparse.ArgumentParser(description='LSTM fake-money bot; no real orders')
    parser.add_argument('--tickers', nargs='+', default=[
        'TQQQ', 'SOXL', 'UPRO', 'SPXL', 'TECL', 'FNGU', 'LABU', 'YINN', 'UDOW', 'NAIL'])
    parser.add_argument('--state', type=Path, default=Path('state.json'))
    parser.add_argument('--checkpoint', type=Path, default=Path('model.pt'))
    parser.add_argument('--output', type=Path, default=Path('reports/latest.json'))
    parser.add_argument('--steps', type=int, default=20)
    args = parser.parse_args()
    if not 1 <= args.steps <= 200:
        parser.error('--steps must be between 1 and 200')
    yf.set_tz_cache_location(str(args.state.parent / '.cache' / 'yfinance'))
    bot = ContinuousLearner(args.tickers, args.checkpoint, args.steps)
    bot.load_state(args.state)
    bot.tickers = list(dict.fromkeys(args.tickers + list(bot.portfolio)))
    errors = bot.learn()
    results = bot.run_once()
    bot.save_model()
    bot.save_state(args.state)
    holdings_value = sum(qty * bot.last_prices[ticker]['price']
                         for ticker, qty in bot.portfolio.items())
    report = {'mode': 'LSTM paper simulation; fake USD only',
              'generated_at': datetime.now().isoformat(), 'starting_cash': 100000.,
              'remaining_cash': bot.cash, 'holdings_value': holdings_value,
              'total_account_value': bot.cash + holdings_value,
              'profit_loss': bot.cash + holdings_value - 100000.,
              'portfolio': bot.portfolio, 'valuation_prices': bot.last_prices,
              'trades': bot.trade_log, 'results': results, 'training_errors': errors,
              'training_steps': bot.training_steps, 'training_loss': bot.last_loss,
              'replay_samples': len(bot.buffer),
              'model_validation': 'Uncalibrated score; no out-of-sample performance estimate'}
    rendered = json.dumps(report, indent=2, allow_nan=False)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered + '\n')
    print(rendered, flush=True)
    return 1 if errors or any('error' in result for result in results) else 0


if __name__ == '__main__':
    raise SystemExit(main())
