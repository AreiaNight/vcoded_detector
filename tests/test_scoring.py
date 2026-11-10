import unittest
from scoring import assess

HIGH = '''<html><body><h1>Urgent: verify your account immediately!!!</h1>
<p>Enter your password to confirm your identity and keep access to your account.</p>
<p>Send money using a gift card to claim your prize and complete the process.</p></body></html>'''
LOW = '''<html><body><p>Our library is open from nine until five on weekdays. Browse the catalogue and contact our staff for information about borrowing books and attending community events.</p></body></html>'''

class ScoringTests(unittest.TestCase):
    def test_high_priority_is_explainable_and_bounded(self):
        a=assess(HIGH)
        self.assertEqual(a['score'],100)
        self.assertEqual(a['score'],sum(f['points'] for f in a['factors']))
        self.assertEqual(a['level'],'High')
        self.assertTrue(a['flagged'])
        self.assertLessEqual(assess(HIGH*10)['score'],100)
    def test_generic_tokens_now_contribute_small_wordlist_score(self):
        a=assess(LOW.replace('Our library','Our token token token library'))
        self.assertEqual(a['scam']['score'],0)
        self.assertEqual(a['ai_template']['wordlist_points'],2)
        self.assertEqual(a['level'],'Low')
    def test_styles_alone_do_not_establish_fraud(self):
        text='<p>THIS IS A REPEATED MESSAGE WITH SOME CAPITAL LETTERS!!!</p>'*3
        self.assertEqual(assess(text)['scam']['score'],0)
        self.assertEqual(assess(text)['ai_template']['score'],15)
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
        self.assertEqual((moderate['score'],moderate['level']),(20,'Moderate'))


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
        self.assertEqual(a['ai_template']['wordlist_points'],11)
        self.assertEqual(a['scam']['score'],0)
        self.assertFalse(a['flagged'])
    def test_repeating_token_does_not_multiply_wordlist_score(self):
        self.assertEqual(assess(LOW+'<script>token token token token</script>')['ai_template']['wordlist_points'],2)
    def test_metadata_does_not_become_a_crawler_signal(self):
        from crawler import load_signals
        entries=load_signals()
        self.assertIn('enter your password',entries)
        self.assertIn('token',entries)
        self.assertFalse(any(e.startswith('#') or e.startswith('[Sensitive') for e in entries))
    def test_literal_matches_have_word_boundaries(self):
        a=assess(LOW+'<p>tokenizer and tokenization documentation</p>')
        self.assertEqual(a['score'],0)


class IndependentAssessmentTests(unittest.TestCase):
    def test_ai_service_and_builder_metadata_do_not_raise_scam_score(self):
        page='<html><head><meta name="generator" content="Framer release"></head><body>'+LOW+'<p>Our AI offers AI-powered assistance for your content ghostwriter workflow.</p></body></html>'
        a=assess(page)
        self.assertEqual(a['ai_template']['score'],60)
        self.assertEqual(a['ai_template']['level'],'High')
        self.assertFalse(a['ai_template']['flagged'])
        self.assertEqual(a['scam']['score'],0)
        self.assertFalse(a['scam']['flagged'])
        self.assertEqual(a['score'],a['scam']['score'])
    def test_high_scam_score_does_not_manufacture_ai_authorship(self):
        a=assess(HIGH)
        self.assertEqual(a['scam']['score'],100)
        self.assertEqual(a['ai_template']['score'],5)
        self.assertTrue(a['scam']['flagged'])
    def test_generator_must_be_metadata_not_a_casual_brand_mention(self):
        a=assess(LOW+'<p>This tutorial discusses Framer and Webflow.</p>')
        self.assertEqual(a['ai_template']['score'],0)
    def test_each_axis_has_independent_insufficient_content_state(self):
        a=assess('<html><head><meta name="generator" content="Framer"></head><body>Hi</body></html>')
        self.assertEqual(a['ai_template']['score'],30)
        self.assertIsNone(a['scam']['score'])
    def test_unavailable_page_never_has_a_score_on_either_axis(self):
        a=assess(HIGH,403)
        for profile in ['scam','ai_template']:
            self.assertIsNone(a[profile]['score'])
    def test_custom_profile_can_be_set_explicitly(self):
        from pathlib import Path
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'words.txt'
            path.write_text('[Custom AI | 40 | text | 40 | ai_template]\ncommunity events\n')
            a=assess(LOW,wordlist_path=path)
            self.assertEqual(a['ai_template']['score'],40)
            self.assertEqual(a['scam']['score'],0)
