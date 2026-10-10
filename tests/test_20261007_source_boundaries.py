"""Source-owned changes cannot inherit a background platform or predicate."""
from datetime import datetime, timezone
from pathlib import Path
import json
import unittest
from test_relevance_rules import load_module, article_for
import test_p4_pure_json_batch as prior

GROUPS = {
 'launch':['7a34f5d772d601ca8473d98e','b77bbae31d3d3da128fb5c89','b72297f6f468531789303444','10ec639b1e07565f0cf46f41','fd1da8fcf15c05c9a58e08e0'],
 'public':['618fb0dde88064834e502ab4','8e25d63a8a98aa290265d1b5','442293f7bfa36f0d3fcd35a4','a1677aa8c2e1eb82dc171ac7','e664b70397d8537dc5b080c3'],
 'touch':['4c164240b1e71e11ccca37d7','2ac83bb3a15656a81138d9b8','55cfe384e62fe7063b3efd01'],
 'screen':['99a16ce730fc552515f9545e'],
 'submission':['a5443ece3ab0eb14d3ae436e','f0e8e09acc006f7d49547c49','e33b196db966b5a61fa95c8c'],
 'messages':['3634f031a01f3b481c004088','a896f97c3c5d0a522a75bf74'],
 'logo':['5be2d2a464b89daaf5d6a33a','eaff668f00da8e549fdfac78','7ee11e57cd9a19d3e53e6317'],
 'lg':['6107f724b76427aa8a2f2520','4d216e026d58e0e142462f75','561289cf253ccfad39b47711','1ad3bc211a7423eda1fef878','9acc016d9ac595e370fda020','7fb9468548e1b8865c08d2ad'],
 'rc':['6382c6654c9da76f71cd764b','bb832c9e8f779a353ea87292'],
 'pdf':['eb5c60c5f91387cd7d4f19b3','321b188b1556f83d2bc72bac'],
 'discoloration':['3d7e276a41e42c4fb73db2f2','c4feaf493312f3adac5e2606'],
 'auction':['6443cc2a55967cf8a4e37d0c','efb1d9f58600de97ad7ee6c1'],
 'earnings':['ebf29c7e9372ad76ae8fc7ab','f4e6533b338ffdfd039f3776','aefac7b95cbe4dbcd64e0ab2','f1ae77a8ee0ef1b5f05e12bd'],
 'choir':['44042c9455adff81447c6ada','c35932bb8d4d484c3eb9eb75'],
}
class SourceBoundaryTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.m=load_module();cls.rows=json.loads((Path(__file__).parent/'fixtures/20261007_source_boundaries.json').read_text());cls.sources={s.name:s for s in cls.m.build_sources(datetime(2026,10,7,tzinfo=timezone.utc))}
 source_articles=prior.PureJsonBatchTests.source_articles
 cluster_sources=prior.PureJsonBatchTests.cluster_sources
 source_ids=staticmethod(prior.PureJsonBatchTests.source_ids)
 def assert_group(self,name,category):
  ids=GROUPS[name]
  for order in (ids,ids[::-1]):
   events,data=self.cluster_sources(*order)
   self.assertEqual(len(events),1,[(e.title,e.relevance_tier) for e in events])
   self.assertEqual(self.source_ids(events[0]),set(ids))
   self.assertEqual((events[0].category,events[0].relevance_tier),(category,'strong'))
 def test_launch_campaign_is_not_a_public_beta(self):
  events,_=self.cluster_sources(*GROUPS['launch'],*GROUPS['public'])
  self.assertEqual({frozenset(self.source_ids(e)) for e in events},{frozenset(GROUPS['launch']),frozenset(GROUPS['public'])})
 def test_touch_disclosure_is_not_screen_time(self):
  events,_=self.cluster_sources(*GROUPS['touch'],*GROUPS['screen'])
  self.assertEqual({frozenset(self.source_ids(e)) for e in events},{frozenset(GROUPS['touch']),frozenset(GROUPS['screen'])})
  self.assertTrue(all(e.category=='software_systems' for e in events))
 def test_generic_distribution_compatibility_stays_weak(self):
  events,_=self.cluster_sources('ed9a5a209ffc5d74d62e33e9')
  self.assertTrue(all(e.relevance_tier=='weak' for e in events))
 def test_independent_app_support_is_not_apple_os_support(self):
  for sid in ['a4f943428bb23d9beea80381','c335bb80d95362a20063d77c']:
   events,_=self.cluster_sources(sid);self.assertTrue(all(e.relevance_tier=='weak' for e in events))
 def test_competitor_owns_its_sales_not_nearby_iphone(self):
  for sid in ['1c705319a7b9e9d3f93e3a65','d3e9de45edd17eebc04397d8']:
   events,_=self.cluster_sources(sid);self.assertTrue(all(e.relevance_tier=='weak' for e in events))
 def test_apple_price_prediction_is_not_an_announced_change(self):
  events,_=self.cluster_sources('8fc219613554d72c9a0f8d89');self.assertTrue(all(e.relevance_tier=='weak' for e in events))
 def test_app_submission_owns_software_category(self): self.assert_group('submission','software_systems')
 def test_messages_controls_reconcile(self): self.assert_group('messages','software_systems')
 def test_wordmark_reconciles(self): self.assert_group('logo','software_systems')
 def test_explicit_codevelopment_is_not_compatibility(self): self.assert_group('lg','hardware_products')
 def test_current_rc_is_not_recap(self): self.assert_group('rc','software_systems')
 def test_pdf_disclosure_is_software(self): self.assert_group('pdf','software_systems')
 def test_current_device_complaints_keep_uncertainty(self): self.assert_group('discoloration','hardware_products')
 def test_current_auction_is_not_historical_biography(self): self.assert_group('auction','hardware_products')
 def test_earnings_announcement_keeps_company_category(self): self.assert_group('earnings','hardware_products')
 def test_apple_content_announcement_not_actor_profile(self): self.assert_group('choir','software_systems')
 def test_quantified_longitudinal_measurement_is_not_upgrade_advice(self):
  events,_=self.cluster_sources('8d67325cc03271bf0d638264');self.assertEqual((events[0].relevance_tier,events[0].category),('strong','hardware_products'))
 def test_current_storage_design_is_not_personal_buying_advice(self):
  events,_=self.cluster_sources('7412b9e6760db33062cb7939');self.assertEqual((events[0].relevance_tier,events[0].category),('strong','hardware_products'))
 def test_old_quota_in_current_report_does_not_become_a_new_event(self):
  events,_=self.cluster_sources('7c60e50f144b3b408ee55e0d');self.assertEqual(len(events),1);self.assertNotIn('Yesterday we reported',events[0].title)

 def test_code_bundle_does_not_become_hardware_roadmaps(self):
  articles=self.source_articles('bea59588dcfafe1bc961a1b5')
  self.assertGreaterEqual(len(articles),3)
  self.assertTrue(all(self.m.article_reconciliation_profile(a).category_hint=='software_systems' for a in articles))
  self.assertTrue(all('roadmap' not in a.title.lower() for a in articles))
 def test_surround_code_reports_group_as_software(self):
  events,_=self.cluster_sources('8e3b51d097c240e31f69fd52','c5826381ab0cbeeec5d8ec7c','3cbdb8f232ed90a95bb60e7d')
  self.assertEqual(len(events),1)
  self.assertEqual(events[0].category,'software_systems')
 def test_version_inventory_is_not_one_listed_logo(self):
  events,_=self.cluster_sources('edba1f8bc1bac879994e086a',*GROUPS['logo'])
  self.assertEqual(len(events),2)
  inventory=next(e for e in events if 'edba1f8bc1bac879994e086a' in self.source_ids(e))
  self.assertEqual(self.source_ids(inventory),{'edba1f8bc1bac879994e086a'})

 def evidence(self,title,paragraphs):
  from apple_news_core.models import ArticleEvidence,EvidenceUnit
  return ArticleEvidence('boundary-test','MacRumors','https://example.com/boundary',title,paragraphs[0],'news',tuple(EvidenceUnit(str(i),'p',text,'body',i) for i,text in enumerate(paragraphs)))
 def test_code_projection_preserves_unassigned_hardware_forecast(self):
  e=self.evidence('Apple TV and HomePod features discovered in code',[
   'A researcher found references in tvOS 29.3 code to Apple Intelligence for Apple TV.',
   'New HomeKit code shows nearby home accessories controls in the Dynamic Island.',
   'Apple may launch a new HomePod next month with a different chip.'])
  projections,remaining,excluded=self.m.project_article_evidence(e)
  self.assertEqual(len(projections),2)
  self.m.validate_evidence_dispositions(e,projections,remaining,excluded)
  self.assertTrue(any(span[0]=='2' for span in remaining))
  self.assertFalse(any('next month' in p.summary for p in projections))
 def test_code_versions_do_not_cross_merge(self):
  from apple_news_core.event_matcher import identity_pair_decision
  def claim(v):
   e=self.evidence('Apple TV code discovery',['Researchers found Apple Intelligence references in tvOS '+v+' code for Apple TV.'])
   return self.m.project_article_evidence(e)[0][0].claim
  self.assertEqual(identity_pair_decision(claim('29.3'),claim('29.4')),'conflict')
 def test_denied_code_discovery_stays_unassigned(self):
  from apple_news_core.event_identity import bind_home_software_claims
  e=self.evidence('Apple TV code discovery denied',['Researchers found no new code for Apple Intelligence in tvOS 29.3 for Apple TV.'])
  self.assertFalse(bind_home_software_claims(e))
 def test_historical_code_cannot_create_current_claim(self):
  from apple_news_core.event_identity import bind_home_software_claims
  e=self.evidence('HomePod features revisited',['Last year researchers discovered code linking Siri to a HomePod surround system.'])
  self.assertFalse(bind_home_software_claims(e))
 def test_release_features_do_not_replace_release(self):
  from apple_news_core.event_identity import bind_home_software_claims
  e=self.evidence('Apple releases tvOS 29.3 beta 2',['Researchers found code for Apple Intelligence in tvOS 29.3 for Apple TV.'])
  self.assertFalse(bind_home_software_claims(e))
 def test_storage_change_requires_apple_owned_affirmative_fact(self):
  from apple_news_core.event_identity import bind_storage_design_claim
  for sentence in [
   'With the new Mac mini, Acme has soldered the SSD to its own expansion board.',
   'With the new Mac mini, Apple has not soldered the SSD to the logic board.',
   'If Apple has soldered the SSD in the latest generation of Mac mini, owners may lose upgrades.']:
   with self.subTest(sentence=sentence):
    self.assertIsNone(bind_storage_design_claim(self.evidence('Apple removed Mac mini storage upgrades',[sentence])))
 def test_separate_auction_windows_do_not_merge(self):
  events=self.m.cluster_articles([article_for(self.m,'苹果一号电脑罕见拍卖','苹果一号正在邦瀚斯拍卖行进行线上拍卖，竞价日期为'+d+'。') for d in ['11月4日至14日','12月4日至14日']])
  self.assertEqual(len(events),2)

 def test_teardown_model_scope_and_publisher_reconcile(self):
  events,_=self.cluster_sources('e063cea21905ec09639ab9d0','3cfaeb1a3eefc5763fbdabea','ccaedc09498c7c9c4db2c0a1')
  self.assertEqual(len(events),1)
 def test_discarded_memory_plan_keeps_report_owner(self):
  events,_=self.cluster_sources('19d4b5cb14721fdd269109d0','ca4ee8a88bf73197db3553d0','5fa432f4b9c979de5aa1f9f6')
  self.assertEqual(len(events),1)
 def test_arcade_announcement_and_access_reconcile(self):
  events,_=self.cluster_sources('951ce864ed7360a40757543a','f36ee6fefe53b64e4f8a0791')
  self.assertEqual(len(events),1)
 def test_equity_transaction_is_company_news(self):
  events,_=self.cluster_sources('7a5b446ab5ef1b84c2ec6a61')
  self.assertEqual(events[0].category,'hardware_products')
 def test_device_sensor_patent_ruling_is_hardware(self):
  events,_=self.cluster_sources('1294698ee68eaf36b96d5612','edc8297133c7eb7288d756c6','746b667a442a01d339b7a0fd')
  self.assertEqual(len(events),1)
  self.assertEqual(events[0].category,'hardware_products')
 def test_first_party_app_support_is_not_third_party_compatibility(self):
  for app in ['TestFlight','App Store Connect']:
   with self.subTest(app=app):
    a=article_for(self.m,app+' 4.0 drops support for iOS 16','Apple updated its '+app+' app today. The application now requires iOS 17.')
    self.assertEqual(self.m.article_reconciliation_profile(a).relevance_tier,'strong')
 def test_code_discovery_needs_current_assertion(self):
  from apple_news_core.event_identity import bind_home_software_claims
  for sentence in ['Researchers did not discover Apple Intelligence references in tvOS 29.3 code for Apple TV.',
                   'In 2024, researchers discovered Apple Intelligence references in tvOS 29.3 code for Apple TV.',
                   'Researchers might discover Apple Intelligence references in tvOS 29.3 code for Apple TV.']:
   with self.subTest(sentence=sentence):
    self.assertFalse(bind_home_software_claims(self.evidence('Apple TV code discovery',[sentence])))
 def test_adjacent_code_version_owns_its_discovery(self):
  from apple_news_core.event_matcher import identity_pair_decision
  def claim(v):
   e=self.evidence('Apple TV code discovery',['Researchers examined tvOS '+v+' code for Apple TV.',
    'They found new Apple Intelligence references in the tvOS code.'])
   return self.m.project_article_evidence(e)[0][0].claim
  self.assertEqual(identity_pair_decision(claim('29.3'),claim('29.4')),'conflict')
 def test_storage_rejected_claim_cannot_bypass_binding(self):
  for sentence in ['If Apple has soldered the SSD in the latest generation of Mac mini, owners may lose upgrades.',
                   'On the new Mac mini, Acme storage is now soldered to its expansion board.']:
   a=article_for(self.m,'Apple removed Mac mini storage upgrades',sentence)
   self.assertFalse(any('storage-replaceability-change' in key for key in self.m.article_reconciliation_profile(a).event_keys))
 def test_third_party_partnership_does_not_acquire_apple_owner(self):
  a=article_for(self.m,'Acme smart home thermostat now works with Apple Home','Acme says its new thermostat was developed in partnership with LG. It now works with Apple Home through Matter.')
  p=self.m.article_reconciliation_profile(a)
  self.assertEqual(p.relevance_tier,'weak')
  self.assertFalse(any('apple:home-codevelopment' in key for key in p.event_keys))
 def test_passive_absence_does_not_assert_positive_code_discovery(self):
  from apple_news_core.event_identity import bind_home_software_claims
  for text in ['No Apple Intelligence references were found in tvOS 29.3 code for Apple TV.',
               'Researchers found that tvOS 29.3 code does not contain Apple Intelligence references for Apple TV.']:
   with self.subTest(text=text):
    self.assertFalse(bind_home_software_claims(self.evidence('Apple TV code discovery',[text])))
 def test_unrelated_app_support_cannot_supply_a_code_version(self):
  e=self.evidence('Apple TV code discovery',['Acme Player adds support for tvOS 29.3 on Apple TV.',
   'Separately, researchers found new Apple Intelligence references in the latest tvOS code.'])
  projections,remaining,excluded=self.m.project_article_evidence(e)
  self.m.validate_evidence_dispositions(e,projections,remaining,excluded)
  self.assertFalse(projections[0].claim.qualifiers)
  self.assertFalse(any('Acme' in f for f in projections[0].key_facts))
  self.assertTrue(any(span[0]=='0' for span in remaining))
 def test_major_code_versions_still_conflict(self):
  from apple_news_core.event_matcher import identity_pair_decision
  claims=[self.m.project_article_evidence(self.evidence('Apple TV code discovery',[
   'Researchers found new Apple Intelligence references in tvOS '+v+' code for Apple TV.']))[0][0].claim for v in ['29','30']]
  self.assertEqual(identity_pair_decision(*claims),'conflict')

 def test_same_sentence_explicit_version_does_not_need_inheritance_verb(self):
  from apple_news_core.event_matcher import identity_pair_decision
  claims=[self.m.project_article_evidence(self.evidence('Apple TV code discovery',[
   'The tvOS '+v+' code contains new Apple Intelligence references for Apple TV.']))[0][0].claim for v in ['29.3','30.1']]
  self.assertEqual(identity_pair_decision(*claims),'conflict')
 def test_same_paragraph_transition_resets_code_context(self):
  e=self.evidence('Apple TV code discovery',['Researchers examined tvOS 29.3 code for Apple TV. Separately, researchers found new Apple Intelligence references in the latest tvOS code.'])
  projections,remaining,excluded=self.m.project_article_evidence(e)
  self.m.validate_evidence_dispositions(e,projections,remaining,excluded)
  self.assertFalse(projections[0].claim.qualifiers)
  self.assertNotIn('29.3',projections[0].summary)

 def test_payment_restoration_keeps_actor_stage_and_local_region(self):
  base=article_for(self.m,'Apple restores App Store card payments in India','Apple has restored credit card payments for App Store and iCloud subscriptions in India.')
  for title,lead in [
   ('Apple may restore App Store card payments in India','Apple may restore credit card payments for App Store and iCloud subscriptions in India.'),
   ('India bank restores cards used for Apple services','Acme Bank restored credit cards for users in India, including cards used to pay Apple App Store subscriptions.'),
   ('Apple restores App Store and iCloud card payments','Apple has restored credit card payments for App Store and iCloud subscriptions. The report discusses RBI rules in India as background.'),
   ('Apple restores card payments in the App Store','Apple has restored credit card payments in the App Store and for iCloud subscriptions. The report discusses RBI rules in India as background.'),
   ('Apple tests App Store card payments in India','Apple is testing restored credit card payments for App Store and iCloud subscriptions in India.'),
   ('Apple restores App Store payments in the UK','Apple has restored credit card payments for App Store and iCloud subscriptions in the UK.')]:
   other=article_for(self.m,title,lead)
   for ordered in ([base,other],[other,base]):
    with self.subTest(title=title): self.assertEqual(len(self.m.cluster_articles(ordered)),2)
 def test_film_schedule_does_not_cross_a_semicolon(self):
  from apple_news_core.event_reconciler import _content_work_assertion
  self.assertNotEqual(_content_work_assertion('Apple TV film news','Apple TV is to screen River House; Sian Heder also discussed her follow-up Being Heumann.'),('being-heumann','premiere-schedule'))
  self.assertEqual(_content_work_assertion('Apple TV film news',"Apple TV is to screen Sian Heder's follow-up Being Heumann; Doctor Who is mentioned only as cast background."),('being-heumann','premiere-schedule'))

 def test_same_equity_sale_keeps_both_languages_and_source_prices(self):
  ids=['2d26c1cf123bf95639f997a1','7a5b446ab5ef1b84c2ec6a61']
  for ordered in (ids,ids[::-1]):
   events,_=self.cluster_sources(*ordered)
   self.assertEqual(len(events),1)
   self.assertEqual((events[0].relevance_tier,events[0].category),('strong','hardware_products'))
   self.assertEqual(self.source_ids(events[0]),set(ids))
 def test_equity_sales_keep_transaction_date_and_actor(self):
  from apple_news_core.event_identity import source_current_report_frame
  for title,lead in [('Tim Cook may sell Apple shares','Apple executive chair Tim Cook may sell Apple shares on October 4.'),('Tim Cook sold Apple shares last year','Apple executive chair Tim Cook sold Apple shares last year on October 2.')]:
   self.assertIsNone(source_current_report_frame(title,lead,()))
  for lead in ['Apple executive chair Tim Cook sold Apple shares on October 2 under a trading plan adopted in May.','Apple executive chair Tim Cook sold Apple shares on May 2.']:
   self.assertIsNotNone(source_current_report_frame('Tim Cook sold Apple shares',lead,()))
  articles=[article_for(self.m,'Tim Cook sold Apple shares','Apple executive chair Tim Cook sold Apple shares on October '+day+'.') for day in ['2','4']]
  self.assertEqual(len(self.m.cluster_articles(articles)),2)
