import copy
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import pandas as pd
import numpy as np
from miljon_signals import validate, load_feed, candidates, entry_check
from lstm_bot import ContinuousLearner
from publish_miljon_signals import merge


def fixture():
    now = datetime.now(timezone.utc)
    # Keep publication safely before the most recent complete business-day bar.
    dates = pd.bdate_range(end=pd.Timestamp(now).normalize() - pd.Timedelta(days=1), periods=90)
    pub = dates[-1].to_pydatetime() - timedelta(days=1)
    row = dict(id='miljon-1', ticker='TEST', company='Test', exchange='NMS', quote_currency='USD',
               source_url='https://example.com/issuer-release', source_status='checked',
               source_checked_at=pub.isoformat(), published_at=pub.isoformat(),
               expires_at=(pub+timedelta(days=7)).isoformat(), status='BEVAKA', bias='positive',
               thesis='New order', risk='Dilution risk')
    frame = pd.DataFrame({'Close':np.linspace(1,2,90),'High':np.linspace(1,2,90)*1.001,
                          'Volume':200000.,'RSI':55.},index=dates)
    quote = dict(price=2.,quote_currency='USD',quote_unit_scale=1.,fx_to_usd=1.,data_date=dates[-1].isoformat())
    research = {'instrument':dict(symbol='TEST',exchange='NMS',currency='USD',quote_type='EQUITY'),
                'gate':dict(approved=True,reason='Pass')}
    return now,row,frame,quote,research


class MiljonTests(unittest.TestCase):
    def test_validation_expiry_and_fail_closed(self):
        now,row,*_ = fixture()
        doc = dict(version=1,updated_at=now.isoformat(),signals=[row])
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'feed.json';p.write_text(json.dumps(doc))
            self.assertEqual(candidates(load_feed(p,now)),['TEST'])
            self.assertEqual(candidates(load_feed(p,now+timedelta(days=8))),[])
            doc['signals'].append(copy.deepcopy(row));p.write_text(json.dumps(doc))
            self.assertTrue(load_feed(p,now)['errors'])
            self.assertEqual(candidates(load_feed(p,now)),[])
        row['expires_at']=(now+timedelta(days=30)).isoformat()
        with self.assertRaises(ValueError):validate(doc)

    def test_penny_liquidity_units_source_and_identity(self):
        now,row,frame,quote,research=fixture()
        def check(r=row,q=quote,f=frame,e=research,trades=[]):
            return entry_check([r],q,f,e,100000.,trades,now)
        approved=check();self.assertTrue(approved['approved']);self.assertEqual(approved['amount'],1000.)
        self.assertTrue(approved['penny_stock_proxy'])
        for field,value in [('bias','negative'),('source_status','unverified')]:
            bad={**row,field:value};self.assertFalse(check(r=bad)['approved'])
        self.assertFalse(check(trades=[{'action':'PAPER BUY','miljon_signal_ids':['miljon-1']}])['approved'])
        self.assertFalse(check(e={})['approved'])
        self.assertFalse(check(q={**quote,'quote_currency':'GBP'})['approved'])
        thin=frame.copy();thin['Volume']=10.;self.assertFalse(check(f=thin)['approved'])
        # Pence turnover must not be overstated 100-fold.
        pence=frame.copy();pence['Close']*=100
        q={**quote,'quote_currency':'GBp','quote_unit_scale':.01}
        e={**research,'instrument':{**research['instrument'],'currency':'GBp'}}
        r={**row,'quote_currency':'GBp'}
        self.assertAlmostEqual(check(r,q,pence,e)['median_turnover_usd'],approved['median_turnover_usd'])
        future={**row,'published_at':now.isoformat(),'source_checked_at':now.isoformat()}
        self.assertFalse(check(r=future)['approved'])

    def test_paper_execution_and_exit_survive_bad_feed(self):
        now,row,frame,quote,research=fixture()
        with tempfile.TemporaryDirectory() as tmp:
            bot=ContinuousLearner(['TEST'],Path(tmp)/'model.pt')
            bot.data['TEST']=frame;bot.miljon_signals={'TEST':[row]};bot.research_reports['TEST']=research
            with patch.object(bot,'price_quote',return_value=quote),patch.object(bot,'predict',return_value={'confidence':.1}):
                bot.run_once(False)
                self.assertEqual(len(bot.trade_log),1)
                self.assertEqual(bot.trade_log[0]['amount'],1000.)
                self.assertEqual(bot.trade_log[0]['miljon_signal_ids'],['miljon-1'])
                bot.save_state(Path(tmp)/'state.json');bot.load_state(Path(tmp)/'state.json')
                bot.run_once(False);self.assertEqual(len(bot.trade_log),1)
                # Expired/rejected lead must not stop existing position risk exit.
                bot.miljon_signals['TEST'][0]['bias']='negative'
                bot.trade_log[0]['quote']={**quote,'data_date':frame.index[-30].isoformat()}
                bot.run_once(False)
                self.assertEqual(bot.trade_log[-1]['action'],'PAPER SELL')
                self.assertEqual(bot.trade_log[-1]['miljon_signal_ids'],['miljon-1'])

    def test_publisher_is_idempotent_and_preserves_other_rows(self):
        now,row,*_=fixture()
        current=dict(version=1,updated_at=now.isoformat(),signals=[row])
        self.assertIsNone(merge(current,copy.deepcopy(current),now))
        new={**row,'id':'miljon-2','ticker':'SECOND'}
        batch={**current,'signals':[new]}
        self.assertEqual(len(merge(current,batch,now)['signals']),2)
        with self.assertRaises(ValueError):merge(current,{**current,'signals':[{**row,'ticker':'WRONG'}]},now)
