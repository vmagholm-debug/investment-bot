"""Literature taxonomy and explicitly limited observable features; no order votes."""
import hashlib
import json
from pathlib import Path
import numpy as np

CATALOGUE = json.loads(Path(__file__).with_name('anomaly_catalogue.json').read_text())
SPEC = {
    'version': 'catalogue-v1', 'catalogue_sha256': CATALOGUE['source_sha256'],
    'momentum': 'close[t-21]/close[t-252]-1, 253 observations',
    'reversal': 'negative trailing 21-bar return', 'near_high': 'close/max(close[-252:])',
    'max_return': 'max daily simple return over last 21 bars',
    'volatility': 'sample standard deviation of 60 daily log returns * sqrt(252)',
    'cost_scenarios': [0., .002, .005, .01], 'hypothesis_family_count': 94,
    'signal_parameters': 'Fixed; no parameter search or auto-promotion',
    'prerequisites': ['point_in_time_data', 'survivorship_and_delistings', 'realistic_execution_costs',
                      'untouched_out_of_sample', 'risk_adjusted_benchmark', 'multiple_testing_control',
                      'international_or_temporal_replication']}
PROTOCOL_ID = hashlib.sha256(json.dumps(SPEC,sort_keys=True).encode() +
                             Path(__file__).read_bytes() +
                             Path(__file__).with_name('patterns.py').read_bytes()).hexdigest()[:16]


def features(frame, research):
    available = {}
    def add(id, values, limitation):
        clean={k:float(v) for k,v in values.items() if v is not None and np.isfinite(v)}
        if clean:
            available[id]={'status':'observed_feature','values':clean,'limitation':limitation}
    c=frame.Close.astype(float)
    if not np.isfinite(c).all() or (c<=0).any():
        raise ValueError('Invalid prices for catalogue features')
    if len(c)>=253:
        add('P1',{'momentum_12_minus_1':c.iloc[-22]/c.iloc[-253]-1},'Raw past return, not a replicated long-short factor; latest 21 bars excluded. Research horizon 3–12 months, not a 21-day alpha claim.')
    if len(c)>=252:
        add('P5',{'price_to_252day_high':c.iloc[-1]/c.tail(252).max()},'Momentum-related; not an independent confirmation of momentum.')
    if len(c)>=22:
        returns=c.pct_change().tail(21)
        add('P2',{'reversal_21d':-(c.iloc[-1]/c.iloc[-22]-1)},'Liquidity/spread can create apparent reversal; raw feature only.')
        add('P6',{'max_daily_return_21d':returns.max()},'Lottery-risk context, not a short order; borrowing costs unavailable.')
        if 'High' in frame:
            add('T2',{'close_to_prior20_high':c.iloc[-1]/frame.High.iloc[-21:-1].max()-1},'Breakout distance; fixed 20-bar rule, no optimized thresholds.')
        if 'Volume' in frame:
            add('L3',{'relative_volume_20d':frame.Volume.iloc[-1]/max(frame.Volume.iloc[-21:-1].mean(),1)},'Relative share volume, not signed buying pressure or shares-outstanding turnover.')
        if 'Open' in frame and (frame.Open.tail(21)>0).all():
            opens=frame.Open.tail(21)
            add('P7',{'overnight_21d':np.prod(opens.to_numpy()/c.shift(1).tail(21).to_numpy())-1,
                      'intraday_21d':np.prod(c.tail(21).to_numpy()/opens.to_numpy())-1},'Adjusted daily OHLC decomposition; no intraday order-flow inference.')
    if len(c)>=61:
        add('T1',{'sma20_to_sma50':c.tail(20).mean()/c.tail(50).mean()-1},'Correlated with momentum and breakout; does not count as another independent vote.')
        logret=np.log(c).diff()
        add('V1',{'volatility_60d_annualized':logret.tail(60).std()*np.sqrt(252)},'Risk characteristic, not proof of higher return; no replicated low-volatility portfolio.')
        prior=logret.iloc[-60:-20].std()
        add('V4',{'vol20_to_prior40':logret.tail(20).std()/prior if prior>0 else None},'Volatility state only: expansion predicts no particular price direction.')
        add('T6',{'rsi14':frame.RSI.iloc[-1] if 'RSI' in frame else None},'Weak catalogue evidence; shares the same price data as other technical metrics.')
    info=research.get('fundamentals',{})
    pb=info.get('priceToBook');pe=info.get('trailingPE')
    add('F1',{'book_to_price':1/pb if pb and pb>0 else None},'Current provider snapshot only; not historical point-in-time HML or a valuation conclusion.')
    add('F2',{'earnings_yield':1/pe if pe and pe>0 else None},'Current provider P/E inverse only; cash-flow/sales yields not inferred across currencies.')
    f=research.get('financials',{})
    if f.get('fresh'):
        add('F7',{'quarter_net_margin':f.get('net_margin')},'Partial quality proxy; no ROIC/stability composite. Fiscal period is not publication date.')
    event=research.get('earnings',{}).get('latest_report') or {}
    add('E1',{'latest_raw_eps_surprise':event.get('surprise_fraction')},'Raw reported surprise, not standardized SUE, historical consensus or a PEAD replication.')
    add('S2',{'current_news_sentiment':research.get('news_mean_sentiment')},'Fixed English FinBERT on headlines/summaries; not historical market-wide sentiment or independent confirmation of an earnings story.')
    return available


def assess(frames,research):
    results={}; errors={}
    for ticker,frame in frames.items():
        try:
            result=features(frame,research.get(ticker,{}))
            results[ticker]={'features':result,'observed_at':research.get(ticker,{}).get('observed_at'),
                             'price_date':frame.index[-1].isoformat(),
                             'unavailable_ids':[r['id'] for r in CATALOGUE['families'] if r['id'] not in result]}
        except Exception as exc:
            errors[ticker]=str(exc)
    counts={}
    for row in CATALOGUE['families']:
        counts[row['implementation']]=counts.get(row['implementation'],0)+1
    return {'protocol_id':PROTOCOL_ID,'specification':SPEC,'catalogue_families':94,
            'implementation_counts':counts,'evidence_attribution':'User-provided document synthesis, not independently replicated alpha',
            'deployment':'diagnostic_only','validation_status':'not_validated',
            'prerequisites':{k:'not_demonstrated' for k in SPEC['prerequisites']},
            'results':results,'errors':errors,
            'independence_rule':'Do not sum raw metrics or literature labels into confidence. Related price rules share information. Behavior/risk regularities are not directional alpha.',
            'source_registry':'anomaly_catalogue.json'}
