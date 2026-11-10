import io
import unittest
from pypdf import PdfReader
from pdf_report import render_pdf, executive_report
from scoring import assess
from test_scoring import HIGH, LOW

class PDFReportTests(unittest.TestCase):
    def records(self):
        return [{'url':'https://high.example/','status':200,'assessment':assess(HIGH)},
                {'url':'https://low.example/','status':200,'assessment':assess(LOW)},
                {'url':'https://unavailable.example/','error':'SECRET_RAW_ERROR'},
                {'url':'https://error-page.example/','status':403,'assessment':assess(HIGH,403)}]
    def test_executive_report_excludes_failures_and_http_error_pages(self):
        report=executive_report({'records':self.records(),'parameters':{'urls':4}})
        self.assertEqual(report['fetched'],2)
        self.assertEqual(report['flagged'],1)
        self.assertEqual(report['coverage'],4)
    def test_pdf_contains_scores_explanations_and_no_error_details(self):
        data=render_pdf({'scan_type':'database','records':self.records(),'parameters':{'cashout_method':'Wire transfer','messages':2,'urls':4,'limit':15}})
        self.assertTrue(data.startswith(b'%PDF-'))
        text='\n'.join(page.extract_text() for page in PdfReader(io.BytesIO(data)).pages)
        for token in ['100/100','0/100','Sensitive-data requests','not probabilities','Wire transfer','AI/template indicators','Scam indicators']:
            self.assertIn(token,text)
        self.assertNotIn('SECRET_RAW_ERROR',text)
        self.assertNotIn('unavailable.example',text)
        self.assertNotIn('error-page.example',text)
    def test_empty_and_partial_reports_are_explicit(self):
        data=render_pdf({'records':[],'complete':False})
        text='\n'.join(p.extract_text() for p in PdfReader(io.BytesIO(data)).pages)
        self.assertIn('PARTIAL REPORT',text)
        self.assertIn('No successfully fetched pages',text)
    def test_long_urls_and_escaped_markup_render(self):
        records=self.records()[:1]*20
        records=[{**r,'url':'https://example.test/'+('longpath'*100)+'?<x>&name=José'} for r in records]
        data=render_pdf({'records':records})
        self.assertGreater(len(PdfReader(io.BytesIO(data)).pages),1)

    def test_report_keeps_high_ai_indicators_separate_from_scam_flags(self):
        page='<meta name="generator" content="Framer">'+LOW+'<p>Our AI offers AI-powered assistance as a content ghostwriter.</p>'
        record={'url':'https://ai-service.example/','status':200,'assessment':assess(page)}
        report=executive_report({'records':[record]})
        self.assertEqual(report['flagged'],0)
        self.assertEqual(report['ai_high'],1)
        text='\n'.join(page.extract_text() for page in PdfReader(io.BytesIO(render_pdf({'records':[record]}))).pages)
        self.assertIn('AI/template indicators: 60/100',text)
        self.assertIn('Scam indicators: 0/100',text)
    def test_old_combined_report_is_not_mislabeled_as_separate_assessment(self):
        old={'url':'https://legacy.example/','status':200,'assessment':{'version':'wordlist-review-v2','score':75,'level':'High'}}
        report=executive_report({'records':[old]})
        self.assertEqual(report['assessed'],0)
        self.assertEqual(report['flagged'],0)
