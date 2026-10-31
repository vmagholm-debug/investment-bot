import copy
import tempfile
import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from unittest.mock import patch
from supply_demand.agent import initialize,validate_state,session_bars,aggregate,zones,signal,stop_level,manage,run,iso,POLICY,coverage_check
from supply_demand.store import pull,push,APIError

D=datetime(2026,10,30,13,30,tzinfo=timezone.utc)
def bar(start=D,o=100,h=101,l=99,c=100):
 return dict(start=iso(start),end=iso(start+timedelta(minutes=5)),open=o,high=h,low=l,close=c,volume=100)
def rows(*bs):return session_bars(list(bs),'QQQ',D+timedelta(hours=6))
def pending(side='LONG'):
 return dict(created_at=iso(D+timedelta(minutes=1)),side=side,stop=95 if side=='LONG' else 105,zone={'id':'z1'},anchors=[],signal_bar_end=iso(D))
def position(side='LONG'):
 return dict(side=side,entry=100,qty=10,entry_cost=1,stop=95 if side=='LONG' else 105,target=110 if side=='LONG' else 90,zone_id='z0',entry_at=iso(D),last_checked=None)

class SupplyDemandTests(unittest.TestCase):
 def test_session_anchored_complete_windows(self):
  bs=rows(*(bar(D+timedelta(minutes=5*i)) for i in range(49)))
  self.assertEqual(len(aggregate(bs,1)),4);self.assertEqual(len(aggregate(bs,4)),1)
  self.assertEqual(aggregate(bs,4)[0]['start'],iso(D))
  del bs[3];self.assertEqual(aggregate(bs,4),[])
 def test_future_and_out_of_session_bars_excluded(self):
  self.assertEqual(session_bars([bar(D-timedelta(hours=1)),bar(D)],'QQQ',D+timedelta(minutes=4)),[])
 def test_departure_is_required_and_not_known_early(self):
  cs=[dict(start=iso(D+timedelta(hours=i)),end=iso(D+timedelta(hours=i+1)),open=100,high=101,low=99,close=100) for i in range(16)]
  cs[-2].update(high=100.4,low=99.6);self.assertEqual(zones(cs,1,'QQQ'),[])
  cs[-1].update(open=100,high=105,low=99.9,close=104)
  z=zones(cs,1,'QQQ')[0];self.assertEqual(z['side'],'LONG');self.assertEqual(z['formed_at'],cs[-1]['end'])
  self.assertFalse(signal(rows(bar()),z,D+timedelta(minutes=5)))
 def test_first_touch_after_formation_can_confirm(self):
  z=dict(formed_at=iso(D),low=99,high=100,side='LONG')
  self.assertTrue(signal(rows(bar(o=99.5,h=101,l=99.2,c=100.5)),z,D+timedelta(minutes=5)))
 def test_second_touch_is_not_fresh(self):
  z=dict(formed_at=iso(D),low=99,high=100,side='LONG')
  self.assertFalse(signal(rows(bar(o=99.5,h=100,l=99.2,c=99.6),bar(D+timedelta(minutes=5),o=99.7,h=101,l=99.4,c=100.5)),z,D+timedelta(minutes=10)))
 def test_outer_structural_stops_ignore_future_anchor(self):
  h=[dict(end=iso(D),low=98,high=104),dict(end=iso(D+timedelta(hours=1)),low=50,high=150)];four=[dict(end=iso(D),low=95,high=108)]
  self.assertEqual(stop_level('LONG',h,four,D)[0],95);self.assertEqual(stop_level('SHORT',h,four,D)[0],108)
  with self.assertRaises(ValueError):stop_level('LONG',h,[],D)
 def test_pending_does_not_fill_decision_or_earlier_bar(self):
  s=initialize(D);a=s['accounts']['QQQ'];a['pending']=pending()
  manage(s,'QQQ',rows(bar(o=90,h=100,l=89,c=99),bar(D+timedelta(minutes=5))),D+timedelta(minutes=10))
  self.assertEqual(s['trades'][0]['time'],iso(D+timedelta(minutes=5)));self.assertEqual(s['trades'][0]['price'],100)
  self.assertEqual(s['trades'][0]['action'],'PAPER_LONG');self.assertIsNotNone(a['position'])
  n=len(s['trades']);manage(s,'QQQ',rows(bar(),bar(D+timedelta(minutes=5))),D+timedelta(minutes=11));self.assertEqual(len(s['trades']),n)
 def test_long_gap_loss_and_cash_agree(self):
  s=initialize(D);a=s['accounts']['QQQ'];a.update(position=position(),cash=98999.)
  manage(s,'QQQ',rows(bar(o=90,h=92,l=88,c=91)),D+timedelta(minutes=5));t=s['trades'][0]
  self.assertEqual(t['price'],90);self.assertAlmostEqual(t['realized_pnl'],-101.9);self.assertAlmostEqual(a['cash'],100000+t['realized_pnl'])
 def test_short_gap_loss_and_cash_agree(self):
  s=initialize(D);a=s['accounts']['QQQ'];a.update(position=position('SHORT'),cash=100999.)
  manage(s,'QQQ',rows(bar(o=110,h=112,l=108,c=111)),D+timedelta(minutes=5));t=s['trades'][0]
  self.assertEqual(t['action'],'PAPER_COVER_SHORT');self.assertAlmostEqual(t['realized_pnl'],-102.1);self.assertAlmostEqual(a['cash'],100000+t['realized_pnl'])
 def test_stop_precedes_target_when_both_touched(self):
  s=initialize(D);s['accounts']['QQQ'].update(position=position(),cash=98999.)
  manage(s,'QQQ',rows(bar(h=111,l=94)),D+timedelta(minutes=5));self.assertEqual(s['trades'][0]['price'],95)
 def test_history_gap_blocks_without_partial_account_changes(self):
  s=initialize(D);s['accounts']['QQQ'].update(position=position(),cash=98999.);before=copy.deepcopy(s['accounts']['QQQ'])
  r=run(s,{'QQQ':[bar(D+timedelta(minutes=5))],'EXS1.DE':{'error':'unavailable'}},D+timedelta(minutes=10))
  self.assertIn('gap',r['errors']['QQQ']);self.assertEqual(s['accounts']['QQQ'],before);self.assertEqual(s['trades'],[])
 def test_one_market_failure_does_not_block_other(self):
  s=initialize(D);r=run(s,{'QQQ':{'error':'provider unavailable'},'EXS1.DE':[bar()]},D+timedelta(minutes=5))
  self.assertEqual(set(r['errors']),{'QQQ'});self.assertEqual(r['markets']['EXS1.DE']['net_equity'],100000)
 def test_state_corruption_and_insolvency_block(self):
  s=initialize(D);s['accounts']['QQQ']['position']=position('BAD')
  with self.assertRaises(ValueError):validate_state(s)
  s=initialize(D);s['accounts']['QQQ'].update(cash=0,pending=pending())
  with self.assertRaises(ValueError):manage(s,'QQQ',rows(bar(),bar(D+timedelta(minutes=5))),D+timedelta(minutes=10))
 def test_missing_permanent_state_never_silently_resets(self):
  with tempfile.TemporaryDirectory() as p,patch('supply_demand.store.api',side_effect=APIError('HTTP 404')):
   with self.assertRaises(ValueError):pull('a/b',p)
   self.assertFalse((Path(p)/'state.json').exists())
 def test_existing_branch_cannot_be_initialized_again(self):
  with tempfile.TemporaryDirectory() as p,patch('supply_demand.store.api',return_value={'object':{'sha':'abc'}}):
   with self.assertRaises(ValueError):pull('a/b',p,bootstrap=True)
 def test_currency_and_policy_are_persistent(self):
  s=initialize(D);s['accounts']['EXS1.DE']['currency']='USD'
  with self.assertRaises(ValueError):validate_state(s)

 def test_missing_session_tail_or_next_open_blocks_execution(self):
  end=D+timedelta(hours=6,minutes=30)
  monday=datetime(2026,11,2,14,30,tzinfo=timezone.utc)
  for bs in ([bar(end-timedelta(minutes=10)),bar(monday)],
             [bar(end-timedelta(minutes=5)),bar(monday+timedelta(minutes=5))]):
   cleaned=session_bars(bs,'QQQ',monday+timedelta(minutes=10))
   with self.assertRaisesRegex(ValueError,'gap'):coverage_check(cleaned,cleaned[0]['end'],'QQQ')

 def test_missing_entire_session_blocks_execution(self):
  thursday=datetime(2026,10,29,19,55,tzinfo=timezone.utc)
  monday=datetime(2026,11,2,14,30,tzinfo=timezone.utc)
  bs=session_bars([bar(thursday),bar(monday)],'QQQ',monday+timedelta(minutes=5))
  with self.assertRaisesRegex(ValueError,'gap'):coverage_check(bs,bs[0]['end'],'QQQ')

 def test_holiday_and_early_close_do_not_create_false_gaps(self):
  wednesday=datetime(2026,11,25,20,55,tzinfo=timezone.utc)
  friday=datetime(2026,11,27,14,30,tzinfo=timezone.utc)
  bs=session_bars([bar(wednesday)]+[bar(friday+timedelta(minutes=5*i)) for i in range(43)],'QQQ',friday+timedelta(hours=4))
  self.assertEqual(len(bs),43) # 42 Friday bars, 13:00 ET early close; Thanksgiving absent.
  coverage_check(bs,bs[0]['end'],'QQQ')

 def test_stale_head_prevents_publication(self):
  import json
  with tempfile.TemporaryDirectory() as directory:
   p=Path(directory);(p/'state.json').write_text(json.dumps(initialize(D)))
   (p/'remote.json').write_text(json.dumps(dict(branch_exists=True,expected_head='old',base_tree='tree')))
   with patch('supply_demand.store.api',return_value={'object':{'sha':'new'}}) as api:
    with self.assertRaisesRegex(ValueError,'Concurrent'):push('a/b',p)
    self.assertEqual(api.call_count,1)

 def test_non_404_error_cannot_initialize(self):
  with tempfile.TemporaryDirectory() as p,patch('supply_demand.store.api',side_effect=APIError('HTTP 403')):
   with self.assertRaises(APIError):pull('a/b',p,bootstrap=True)
   self.assertFalse((Path(p)/'state.json').exists())

 def test_missing_zone_history_cannot_claim_first_retest(self):
  s=initialize(D)
  z=dict(id='gap-zone',formed_at=iso(D),side='LONG',low=99,high=100,timeframe_hours=1)
  latest=bar(D+timedelta(minutes=10),o=99.5,h=101,l=99.2,c=100.5)
  with patch('supply_demand.agent.zones',return_value=[z]):
   r=run(s,{'QQQ':[bar(D,o=102,h=103,l=101,c=102),latest],'EXS1.DE':{'error':'missing'}},D+timedelta(minutes=15))
  self.assertIn('gap',r['errors']['QQQ']);self.assertIsNone(s['accounts']['QQQ']['pending'])
  s=initialize(D);s['policy']=dict(POLICY,risk_fraction=.01)
  with self.assertRaises(ValueError):validate_state(s)

if __name__=='__main__':unittest.main()
