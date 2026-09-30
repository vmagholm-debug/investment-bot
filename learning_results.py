"""Separate observed paper results, training fit and prospective diagnostics."""
import math


def finite(value):
    return isinstance(value, (int, float)) and math.isfinite(value)


def learning_results(report):
    trades = report.get('trades', [])
    sales = [t for t in trades if 'SELL' in t.get('action', '')]
    measured = [t for t in sales if finite(t.get('realized_pnl'))]
    realized = sum(t['realized_pnl'] for t in measured) if len(measured) == len(sales) else None
    start, value = report.get('starting_cash'), report.get('total_account_value')
    total = value-start if finite(value) and finite(start) else None
    learning = report.get('learning', {})
    before, after = learning.get('fixed_batch_loss_before'), learning.get('fixed_batch_loss_after')
    change = (after/before-1)*100 if finite(before) and before > 0 and finite(after) else None
    strategies = []
    for strategy in ['mean_reversion', 'momentum', 'trend_following', 'breakout', 'earnings']:
        rows = [t for t in measured if t.get('strategy') == strategy]
        strategies.append({'strategy': strategy, 'sales': len(rows),
                           'wins': sum(t['realized_pnl'] > 0 for t in rows),
                           'realized_pnl': sum(t['realized_pnl'] for t in rows)})
    return {'as_of': report.get('generated_at'), 'total_pnl': total,
            'return_pct': total/start*100 if total is not None and finite(start) and start > 0 else None,
            'realized_pnl': realized, 'unrealized_pnl': total-realized if total is not None and realized is not None else None,
            'sales': len(sales), 'measured_sales': len(measured),
            'winning_sales': sum(t['realized_pnl'] > 0 for t in measured),
            'losing_sales': sum(t['realized_pnl'] < 0 for t in measured),
            'strategies': strategies, 'training_loss_change_pct': change,
            'training_fit': 'worse' if change is not None and change > 0 else 'better' if change is not None and change < 0 else 'unchanged' if change == 0 else 'unavailable',
            'lstm_evaluation': {'status': 'unavailable', 'reason': 'No recorded out-of-sample LSTM performance estimate'},
            'pattern_validation': (report.get('pattern_analysis') or {}).get('validation'),
            'limitations': 'Fake-money results before fees/slippage. Sales are not necessarily independent round trips. Trading rules, not the LSTM score, select entries. Training fit does not measure future profit.'}
