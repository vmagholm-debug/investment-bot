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
from market import CurrencyConverter
from discovery import discover, save_discovery, is_europe
from reporting import write_reports
from themes import analyze_themes
from investment_analysis import analyze as analyze_investment
from research import CompanyResearch
from strategies import StrategyTrading
from patterns import PatternLibrary
from catalogue import assess as assess_catalogue
from watchlist import load_watchlist, include_watchlist, summarize as summarize_watchlist


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


class ContinuousLearner(StrategyTrading, TenPercentMonthlyBot):
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
        self.fx = CurrencyConverter()
        self.learning = {}
        self.discovered_regions = {}
        self.research_reports = {}
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
        details = {}
        steps_before = self.training_steps
        for ticker in self.tickers:
            try:
                new_count = self.update_model(ticker)
                added += new_count
                known = self.fetch_data(ticker)['Target'].dropna()
                details[ticker] = {'new_samples': new_count, 'known_outcomes': len(known),
                                   'target_reached': int(known.sum())}
            except Exception as exc:
                errors[ticker] = str(exc)
        before_scores = {}
        if self.training_steps:
            for ticker in self.tickers:
                if ticker not in errors:
                    try:
                        before_scores[ticker] = self.predict(ticker)['confidence']
                    except ValueError:
                        pass
        # Evaluate the same fixed replay batch before and after the update.
        evaluation = self.buffer[-min(256, len(self.buffer)):]
        def loss_on_fixed_batch():
            if not evaluation:
                return None
            self.model.eval()
            with torch.no_grad():
                x = torch.stack([row[0] for row in evaluation])
                y = torch.tensor([row[1] for row in evaluation]).unsqueeze(1)
                return float(nn.BCELoss()(self.model(x), y).item())
        loss_before = loss_on_fixed_batch()
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
        self.learning = {'new_samples': added, 'samples_by_ticker': details,
                         'steps_this_run': self.training_steps - steps_before,
                         'fixed_batch_loss_before': loss_before,
                         'fixed_batch_loss_after': loss_on_fixed_batch(),
                         'scores_before_update': before_scores,
                         'interpretation': 'Training-fit measurements only; not evidence of future profit or causal market knowledge.'}
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
        research = self.research_reports.get(ticker, {})
        gate = research.get('gate', {'approved': False, 'reason': 'Research not available'})
        reason = 'Diagnostic uncalibrated LSTM score; trading decisions use independent strategy rules'
        return {'ticker': ticker, 'direction': 'DIAGNOSTIC',
                'research_gate': gate, 'reason': reason,
                'confidence': probability, 'accuracy': None,
                'historical_mean_21d_return': float(df['Forward_Return_21d'].dropna().tail(60).mean()),
                'data_date': df.index[-1].isoformat(),
                'timestamp': datetime.now().isoformat()}

    def price_quote(self, ticker, df):
        quote = self.fx.convert(float(df['Close'].iloc[-1]), self.fx.currency(ticker))
        quote['data_date'] = df.index[-1].isoformat()
        quote['region'] = self.discovered_regions.get(ticker, self.last_prices.get(ticker, {}).get('region', 'Europe' if is_europe(ticker) else 'Other'))
        return quote



def main():
    parser = argparse.ArgumentParser(description='LSTM fake-money bot; no real orders')
    parser.add_argument('--tickers', nargs='+', help='Optional explicit override; default uses live discovery')
    parser.add_argument('--discovery-state', type=Path, default=Path('discovery.json'))
    parser.add_argument('--state', type=Path, default=Path('state.json'))
    parser.add_argument('--checkpoint', type=Path, default=Path('model.pt'))
    parser.add_argument('--output', type=Path, default=Path('reports/latest.json'))
    parser.add_argument('--steps', type=int, default=20)
    args = parser.parse_args()
    if not 1 <= args.steps <= 200:
        parser.error('--steps must be between 1 and 200')
    yf.set_tz_cache_location(str(args.state.parent / '.cache' / 'yfinance'))
    if args.tickers:
        tickers, discovery_report, discovery_state = args.tickers, {'mode': 'explicit CLI override'}, None
    else:
        tickers, discovery_report, discovery_state = discover(args.discovery_state)
    watchlist = load_watchlist()
    tickers = include_watchlist(tickers, watchlist)
    bot = ContinuousLearner(tickers, args.checkpoint, args.steps)
    bot.discovered_regions = {t: d['region_group'] for t, d in discovery_report.get('selected', {}).items()}
    bot.discovered_regions.update({r['ticker']: r['region'] for r in watchlist})
    bot.load_state(args.state)
    bot.tickers = list(dict.fromkeys(tickers + list(bot.portfolio)))
    trade_count_before = len(bot.trade_log)
    errors = bot.learn()
    researcher = CompanyResearch(args.state.parent / '.cache' / 'finbert')
    for ticker in bot.tickers:
        try:
            bot.research_reports[ticker] = researcher.collect(ticker)
        except Exception as exc:
            bot.research_reports[ticker] = {'symbol': ticker, 'errors': {'research': str(exc)},
                                           'gate': {'approved': False, 'reason': 'Research failed: ' + str(exc),
                                                    'categories': {}, 'blockers': ['Research unavailable']}}
    pattern_library = PatternLibrary(args.state.parent / 'patterns.json')
    pattern_report = pattern_library.analyze(bot.data, bot.research_reports)
    pattern_library.save()
    results = bot.run_once(refresh=False)
    bot.save_model()
    bot.save_state(args.state)
    holdings_value = sum(qty * bot.last_prices[ticker]['price']
                         for ticker, qty in bot.portfolio.items())
    report = {'mode': 'Five-strategy paper simulation; fake USD only',
              'generated_at': datetime.now().isoformat(), 'starting_cash': 100000.,
              'remaining_cash': bot.cash, 'holdings_value': holdings_value,
              'total_account_value': bot.cash + holdings_value,
              'profit_loss': bot.cash + holdings_value - 100000.,
              'portfolio': bot.portfolio, 'valuation_prices': bot.last_prices,
              'trades': bot.trade_log, 'new_trades': bot.trade_log[trade_count_before:],
              'results': results, 'training_errors': errors,
              'learning': bot.learning, 'company_research': bot.research_reports,
              'pattern_analysis': pattern_report,
              'long_term_analysis': analyze_themes(bot.research_reports),
              'catalogue_analysis': assess_catalogue(bot.data, bot.research_reports),
              'strategy_policy': 'v1: independent entries; LSTM diagnostic only; research approval; 2% cash per entry; maximum 10 positions; daily exits at -5%, +10%, 21 trading days or strategy exit; no fees/slippage',
              'discovery': discovery_report,
              'watchlist': summarize_watchlist(watchlist, bot.research_reports, results),
              'coverage': {'tickers': bot.tickers,
                           'us': sum(bot.last_prices.get(t, {}).get('region') == 'US' for t in bot.tickers),
                           'europe': sum(is_europe(t) or bot.last_prices.get(t, {}).get('region') == 'Europe' for t in bot.tickers),
                           'other': sum(not is_europe(t) and bot.last_prices.get(t, {}).get('region') not in ('US','Europe') for t in bot.tickers),
                           'scope': 'Live US-first global Yahoo screener: 24 US and 8 international candidates plus user watchlist and existing holdings'},
              'training_steps': bot.training_steps, 'training_loss': bot.last_loss,
              'replay_samples': len(bot.buffer),
              'model_validation': 'Uncalibrated score; no out-of-sample performance estimate'}
    report['investment_analysis'] = analyze_investment(report)
    rendered = json.dumps(report, indent=2, allow_nan=False)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered + '\n')
    write_reports(report, args.output.parent)
    if discovery_state is not None:
        save_discovery(args.discovery_state, discovery_state)
    print(rendered, flush=True)
    return 1 if errors or any('error' in result for result in results) else 0


if __name__ == '__main__':
    raise SystemExit(main())
