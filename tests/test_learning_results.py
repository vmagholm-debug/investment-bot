import unittest
from learning_results import learning_results

class LearningResultsTests(unittest.TestCase):
    def test_losses_are_not_reported_as_improvements(self):
        r=learning_results({'starting_cash':100,'total_account_value':95,'learning':{'fixed_batch_loss_before':.4,'fixed_batch_loss_after':.43},'trades':[]})
        self.assertEqual(r['training_fit'],'worse')
        self.assertAlmostEqual(r['training_loss_change_pct'],7.5)
        self.assertEqual(r['total_pnl'],-5)
        self.assertEqual(r['unrealized_pnl'],-5)
        self.assertEqual(r['sales'],0)
        self.assertEqual(r['lstm_evaluation']['status'],'unavailable')
    def test_missing_sale_results_are_unknown_not_zero(self):
        r=learning_results({'trades':[{'action':'PAPER SELL'}]})
        self.assertIsNone(r['realized_pnl'])
    def test_realized_and_unrealized_are_separate(self):
        r=learning_results({'starting_cash':100,'total_account_value':110,'trades':[{'action':'PAPER SELL','strategy':'momentum','realized_pnl':4}]})
        self.assertEqual(r['realized_pnl'],4)
        self.assertEqual(r['unrealized_pnl'],6)
        self.assertEqual(r['winning_sales'],1)
