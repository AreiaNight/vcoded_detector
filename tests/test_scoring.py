import unittest
from scoring import assess

HIGH = '''<html><body><h1>Urgent: verify your account immediately!!!</h1>
<p>Enter your password to confirm your identity and keep access to your account.</p>
<p>Send money using a gift card to claim your prize and complete the process.</p></body></html>'''
LOW = '''<html><body><p>Our library is open from nine until five on weekdays. Browse the catalogue and contact our staff for information about borrowing books and attending community events.</p></body></html>'''

class ScoringTests(unittest.TestCase):
    def test_high_priority_is_explainable_and_bounded(self):
        a=assess(HIGH)
        self.assertEqual(a['score'],75)
        self.assertEqual(a['score'],sum(f['points'] for f in a['factors']))
        self.assertEqual(a['level'],'High')
        self.assertTrue(a['flagged'])
        self.assertLessEqual(assess(HIGH*10)['score'],100)
    def test_generic_tokens_now_contribute_small_wordlist_score(self):
        a=assess(LOW.replace('Our library','Our token token token library'))
        self.assertEqual(a['score'],2)
        self.assertEqual(a['wordlist_points'],2)
        self.assertEqual(a['level'],'Low')
    def test_styles_alone_do_not_establish_fraud(self):
        text='<p>THIS IS A REPEATED MESSAGE WITH SOME CAPITAL LETTERS!!!</p>'*3
        self.assertEqual(assess(text)['score'],15)
        self.assertFalse(assess(text)['flagged'])
    def test_safety_advice_and_script_content_are_not_scored(self):
        html=LOW+'<p>Never share your password with anyone. Do not send money using a gift card.</p>'
        html+='<script>Enter your password immediately; send money using a gift card</script>'
        self.assertEqual(assess(html)['score'],0)
    def test_unavailable_short_or_unsupported_pages_have_no_score(self):
        for a in [assess(HIGH,404),assess('Hello'),assess(HIGH,200,'application/pdf')]:
            self.assertIsNone(a['score']); self.assertEqual(a['level'],'Not assessed')
    def test_spanish_signals(self):
        a=assess('<p>Urgente: verifica tu cuenta. Ingresa tu contraseña para confirmar el acceso. Envía dinero mediante una tarjeta de regalo para continuar con el proceso.</p>')
        self.assertGreaterEqual(a['score'],50)
    def test_band_boundaries(self):
        moderate=assess('<p>Urgent: act now and read the latest announcement about our upcoming community meeting this weekend.</p>')
        self.assertEqual((moderate['score'],moderate['level']),(15,'Low'))


class WordlistIntegrationTests(unittest.TestCase):
    def test_editing_wordlist_changes_score_without_editing_code(self):
        from pathlib import Path
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'wordlist.txt'
            path.write_text('[Custom phrase | 40 | text | 40]\ncommunity events\n')
            a=assess(LOW,wordlist_path=path)
            self.assertEqual(a['score'],40)
            self.assertEqual(a['factors'][0]['entries'],['community events'])
            path.write_text('[Custom phrase | 40 | text | 40]\nnot present\n')
            self.assertEqual(assess(LOW,wordlist_path=path)['score'],0)
    def test_source_markers_and_emoji_influence_score_but_are_capped(self):
        page=LOW+'<!-- Fake Error Message --><script>const token = 1; // Floating embers</script><p>😀 😃 😄 😁 😆 😅</p>'
        a=assess(page)
        self.assertEqual(a['wordlist_points'],11)
        self.assertEqual(a['score'],11)
        self.assertFalse(a['flagged'])
    def test_repeating_token_does_not_multiply_wordlist_score(self):
        self.assertEqual(assess(LOW+'<script>token token token token</script>')['wordlist_points'],2)
    def test_metadata_does_not_become_a_crawler_signal(self):
        from crawler import load_signals
        entries=load_signals()
        self.assertIn('enter your password',entries)
        self.assertIn('token',entries)
        self.assertFalse(any(e.startswith('#') or e.startswith('[Sensitive') for e in entries))
    def test_literal_matches_have_word_boundaries(self):
        a=assess(LOW+'<p>tokenizer and tokenization documentation</p>')
        self.assertEqual(a['score'],0)
