"""Bounded cross-stock analog research with honest prospective validation.

This is a diagnostic layer, not an additional order generator. Price-shape
similarity does not establish causality or identify earnings announcements.
"""
import json
from pathlib import Path
import numpy as np
import pandas as pd

HORIZONS = (5, 10, 21)
COST = .002  # Illustrative round-trip cost assumption, not the paper ledger.
LIMIT = 50000


def day(value):
    return pd.Timestamp(value).date().isoformat()


def describe(frame):
    if len(frame) < 61:
        raise ValueError('Need 61 observations for pattern context')
    f = frame.tail(61)
    c = f.Close.to_numpy(dtype=float)
    v = f.Volume.to_numpy(dtype=float)
    if not np.isfinite(c).all() or (c <= 0).any() or not np.isfinite(v).all() or (v < 0).any():
        raise ValueError('Invalid price or volume history')
    ret = np.diff(np.log(c))
    vol = max(float(np.std(ret[-20:])), .005)
    # Four consecutive five-bar returns describe shape; fixed scale uses only past volatility.
    shape = [float(np.log(c[-1-i*5] / c[-6-i*5]) / (vol*np.sqrt(5))) for i in range(4)]
    r20, r60 = c[-1]/c[-21]-1, c[-1]/c[0]-1
    ratio = float(v[-1] / max(float(np.mean(v[-21:-1])), 1.))
    vector = shape + [float((c[-1]/np.mean(c[-20:])-1)/(vol*np.sqrt(20))),
                      float((c[-1]/np.mean(c[-50:])-1)/(vol*np.sqrt(50))),
                      float(np.log(max(ratio, .01))), float(np.log(vol/.02))]
    family = ('rebound_after_decline' if r20 < 0 and c[-1] > c[-6] else
              'uptrend' if r20 > 0 and r60 > 0 else
              'downtrend' if r20 < 0 and r60 < 0 else 'mixed')
    return {'vector': vector, 'family': family, 'return_20d': float(r20),
            'return_60d': float(r60), 'daily_volatility': vol, 'volume_ratio': ratio,
            'date': day(frame.index[-1])}


def summarize(matches):
    if not matches:
        return {'count': 0, 'tickers': 0, 'months': 0, 'outcomes': {}}
    outcomes = {}
    for h in HORIZONS:
        x = np.array([r['returns'][str(h)]-COST for r in matches])
        outcomes[str(h)] = {'mean_net_return': float(x.mean()), 'median_net_return': float(np.median(x)),
                            'positive_fraction': float((x > 0).mean()), 'p10_net_return': float(np.quantile(x,.1)),
                            'worst_observed_net_return': float(x.min()),
                            'best_observed_net_return': float(x.max()),
                            'extreme_outcomes': int((np.abs(x) >= 1).sum())}
    return {'count': len(matches), 'tickers': len({r['ticker'] for r in matches}),
            'months': len({r['date'][:7] for r in matches}), 'outcomes': outcomes,
            'worst_interim_close_return': min(r['worst_interim_close_return'] for r in matches)}


class PatternLibrary:
    def __init__(self, path):
        self.path = Path(path)
        self.state = json.loads(self.path.read_text()) if self.path.exists() else {'version': 1, 'records': [], 'forecasts': []}
        if self.state.get('version') != 1:
            raise ValueError('Unsupported pattern library version')

    def update(self, frames):
        rows = {(r['ticker'], r['date']): r for r in self.state['records']}
        added = 0
        for ticker, frame in frames.items():
            # Stable calendar-month sampling reduces repeated near-identical windows.
            seen_months = set()
            for end in range(60, len(frame)-21):
                date = day(frame.index[end])
                month = date[:7]
                if month in seen_months:
                    continue
                seen_months.add(month)
                context = describe(frame.iloc[:end+1])
                close = float(frame.Close.iloc[end])
                returns = {str(h): float(frame.Close.iloc[end+h]/close-1) for h in HORIZONS}
                key = (ticker, date)
                added += key not in rows
                rows[key] = {**context, 'ticker': ticker, 'label_end': day(frame.index[end+21]),
                             'returns': returns,
                             'worst_interim_close_return': float(frame.Close.iloc[end+1:end+22].min()/close-1)}
        self.state['records'] = sorted(rows.values(), key=lambda r:(r['date'],r['ticker']))[-LIMIT:]
        return added

    def compare(self, ticker, context):
        # All future outcomes of matches must predate the query; do not leak labels.
        eligible = [r for r in self.state['records'] if r['ticker'] != ticker and r['label_end'] < context['date']]
        candidates = []
        for row in eligible:
            if row['family'] != context['family']:
                continue
            distance = float(np.sqrt(np.mean((np.array(row['vector'])-context['vector'])**2)))
            if distance <= .75:
                candidates.append((distance, row))
        selected, intervals = [], {}
        for distance, row in sorted(candidates,key=lambda p:(p[0],p[1]['date'],p[1]['ticker'])):
            spans = intervals.setdefault(row['ticker'], [])
            if any(not(row['label_end'] < a or row['date'] > b) for a,b in spans):
                continue
            spans.append((row['date'],row['label_end']))
            selected.append({**row, 'distance': distance})
            if len(selected) == 60:
                break
        stats = summarize(selected)
        baseline = summarize(eligible)
        enough = stats['count'] >= 20 and stats['tickers'] >= 5 and stats['months'] >= 8
        verdict = ('insufficient_evidence' if not enough else
                   'extreme_outcomes_require_review' if any(v['extreme_outcomes'] for v in stats['outcomes'].values()) else
                   'historically_positive_unvalidated' if stats['outcomes']['21']['median_net_return'] > 0 else
                   'historically_nonpositive')
        return {'context': context, 'matches': stats, 'baseline': baseline, 'assessment': verdict,
                'examples': [{k:r[k] for k in ['ticker','date','label_end','distance','returns','worst_interim_close_return']} for r in selected[:5]],
                'eligible_records': len(eligible)}

    def mature(self, frames):
        for forecast in self.state['forecasts']:
            if 'actual_net_return' in forecast or forecast['ticker'] not in frames:
                continue
            frame = frames[forecast['ticker']]
            # Real prospective check: enter at the first daily close AFTER issuance day.
            after = frame.loc[[day(d) > forecast['issued_date'] for d in frame.index]]
            if len(after) < 22:
                continue
            forecast['entry_date'] = day(after.index[0])
            forecast['outcome_date'] = day(after.index[21])
            forecast['actual_net_return'] = float(after.Close.iloc[21]/after.Close.iloc[0]-1-COST)

    def validation(self):
        settled = [f for f in self.state['forecasts'] if 'actual_net_return' in f]
        if not settled:
            return {'settled': 0, 'pending': len(self.state['forecasts']), 'status': 'No prospective outcomes yet'}
        error = [abs(f['predicted_net_return']-f['actual_net_return']) for f in settled]
        baseline_error = [abs(f['baseline_prediction']-f['actual_net_return']) for f in settled]
        return {'settled': len(settled), 'pending': len(self.state['forecasts'])-len(settled),
                'forecast_statistic': 'Median net return; baseline is unconditional historical median',
                'mean_absolute_error': float(np.mean(error)), 'baseline_mean_absolute_error': float(np.mean(baseline_error)),
                'issuance_months': len({f['issued_date'][:7] for f in settled}),
                'status': 'Prospective diagnostic only; correlated outcomes and changing coverage prevent a calibrated reliability claim'}

    def analyze(self, frames, research, now=None):
        now = pd.Timestamp(now or pd.Timestamp.now(tz='UTC'))
        errors, valid = {}, {}
        for ticker, frame in frames.items():
            try:
                context = describe(frame)
                age = (now.date()-pd.Timestamp(context['date']).date()).days
                if not 0 <= age <= 7:
                    raise ValueError('Stale/future price date')
                valid[ticker] = frame
            except Exception as exc:
                errors[ticker] = str(exc)
        added = self.update(valid)
        self.mature(valid)
        results = {}
        for ticker, frame in valid.items():
            result = self.compare(ticker,describe(frame))
            gate = research.get(ticker,{}).get('gate',{})
            result['current_research'] = gate
            result['combined_assessment'] = ('research_blocks_purchase' if not gate.get('approved') else result['assessment'])
            results[ticker] = result
            # At most one active, nonoverlapping prospective forecast per ticker.
            previous = [f for f in self.state['forecasts'] if f['ticker'] == ticker]
            if result['matches']['count'] and not any('actual_net_return' not in f or f.get('outcome_date','') >= result['context']['date'] for f in previous):
                self.state['forecasts'].append({'ticker': ticker, 'issued_date': day(now),
                                               'asof_date': result['context']['date'], 'family':result['context']['family'],
                                               'predicted_net_return': result['matches']['outcomes']['21']['median_net_return'],
                                               'baseline_prediction':result['baseline']['outcomes']['21']['median_net_return']})
        return {'version': 1, 'new_records': added, 'stored_records': len(self.state['records']),
                'stored_tickers': len({r['ticker'] for r in self.state['records']}),
                'validation': self.validation(), 'results':results, 'errors':errors,
                'policy': 'Cross-stock analogs, maximum RMS distance 0.75, 60 neighbors, 20 matches/5 companies/8 months for descriptive support. Never a trade trigger or a calibrated probability.',
                'limitations': 'Selected surviving equities, roughly two years of retrieved history; no exhaustive market coverage. Local-currency adjusted-close returns, illustrative 0.2% round-trip cost. Cross-stock outcomes remain correlated. Baseline includes all eligible historical snapshots, not a tradable index. Absolute outcomes >=100% are flagged and retained; mean returns can be dominated by genuine jumps or data errors. Current fundamentals/news are not known historical facts. Price shapes cannot identify report reactions without dated historical earnings. No validated causal or profitability claim.'}

    def save(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        temporary=self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps(self.state,allow_nan=False)+'\n')
        temporary.replace(self.path)
