import copy
import json
from pathlib import Path
import pytest
import wikidebia_final_publication as final
from wikidebia_translation_review import _validate_argument, TranslationReviewError


def decision():
    return dict(owner_approved=True,decision='explicit_user_request',allow_proposed_change=True,
                page_id='A0007',language='en',title='Existing title',observed_revision_id=12,
                observed_sha256='old',proposed_sha256='new',
                instruction='For this debate, update the previously discussed English pages and their quotations.')


def test_first_publication_keeps_default_collision_guard_and_accepts_only_exact_approved_update():
    d=decision();row=dict(language='en',page_id='A0007',title='Existing title',expected_revision_id=12,old_sha256='old',new_sha256='new')
    plan={'operations':{'update':[row]}}
    with pytest.raises(final.FinalPublicationError):final._assert_safe_update_plan(plan,full=True)
    final._assert_safe_update_plan(plan,full=True,approved_updates={'A0007':d})
    for field,value in [('expected_revision_id',13),('old_sha256','changed'),('new_sha256','changed'),('title','Other title')]:
        bad=copy.deepcopy(plan);bad['operations']['update'][0][field]=value
        with pytest.raises(final.FinalPublicationError):final._assert_safe_update_plan(bad,full=True,approved_updates={'A0007':d})
    with pytest.raises(final.FinalPublicationError):final._assert_safe_update_plan(plan,full=False,approved_updates={'A0007':d})


def test_english_update_plan_is_pinned_to_owner_decision_and_current_revision():
    d=decision();row=dict(language='en',page_id='A0007',title='Existing title',operation='update',remote_revision_id=12,remote_sha256='old',desired_sha256='new')
    plan={'actions':[row]}
    with pytest.raises(final.FinalPublicationError):final._assert_safe_english_plan(plan)
    final._assert_safe_english_plan(plan,{'A0007':d})
    for field,value in [('owner_approved',False),('instruction',''),('decision','pending')]:
        bad={**d,field:value}
        with pytest.raises(final.FinalPublicationError):final._assert_safe_english_plan(plan,{'A0007':bad})


def test_manifest_approval_does_not_allow_a_new_page_to_overwrite_an_existing_one(tmp_path: Path):
    (tmp_path/'page.wiki').write_text('{{Argument|summary=Reviewed text}}')
    row=dict(language='en',page_id='A0007',canonical_title='Existing title',page_origin='preexisting',file_path='page.wiki',existing_english_update=decision())
    (tmp_path/'manifest.json').write_text(json.dumps({'pages':[row]}))
    assert final._approved_english_updates(tmp_path)['A0007']['proposed_sha256']
    row['page_origin']='new';(tmp_path/'manifest.json').write_text(json.dumps({'pages':[row]}))
    with pytest.raises(final.FinalPublicationError):final._approved_english_updates(tmp_path)


def test_manifest_approval_uses_exact_audited_successor_revision(tmp_path: Path):
    (tmp_path/'page.wiki').write_text('{{Argument|summary=Reviewed text}}')
    d = decision()
    d.update(observed_sha256='a' * 64, successor_revision={
        'owner_approved': True, 'predecessor_revision_id': 12, 'predecessor_sha256': 'a' * 64,
        'observed_revision_id': 13, 'observed_sha256': 'b' * 64, 'delta_policy': 'whitespace_only',
        'verification_receipt_sha256': 'c' * 64,
        'instruction': 'Accept the audited whitespace-only successor revision for final publication.',
    })
    row=dict(language='en',page_id='A0007',canonical_title='Existing title',page_origin='preexisting',file_path='page.wiki',existing_english_update=d)
    (tmp_path/'manifest.json').write_text(json.dumps({'pages':[row]}))
    approved = final._approved_english_updates(tmp_path)['A0007']
    assert approved['observed_revision_id'] == 13
    assert approved['observed_sha256'] == 'b' * 64


def test_existing_quote_parameter_rename_is_not_a_citation_deletion():
    from wikidebia_update import top_level_parameter_deletions,assert_citation_change_authorized,UpdateError
    quote='{{Quote|quote=The same complete quotation|article=Original article|link=https://example.org}}'
    before='{{Argument|citations='+quote+'}}';after='{{Argument|quotes='+quote+'}}'
    assert top_level_parameter_deletions(before,after,'en','argument')==[]
    assert_citation_change_authorized(before,after)
    with pytest.raises(UpdateError):assert_citation_change_authorized(before,after.replace('complete quotation','shortened'))


def test_global_preflight_rejects_changed_owner_approved_revision():
    class Adapter:
        def open_language(self,*args):pass
        def close_language(self):pass
        def assert_identity(self,*args):pass
        def available_change_tags(self):return {'chatgpt','translated-fr'}
        def user_rights(self):return {'edit','createpage'}
        def read_page(self,title):return True,13,'current text'
    row=dict(language='en',page_id='A0007',title='Existing title',operation='update',remote_revision_id=12,remote_sha256=final.sha_text('current text'))
    with pytest.raises(final.FinalPublicationError):final._remote_snapshot_for_english(Adapter(),{'actions':[row]},'ChatGPT')


def test_final_publication_plans_never_delete_pages_retired_from_the_work(monkeypatch, tmp_path: Path):
    modes=[]
    class Planner:
        def __init__(self,*args):pass
        def build_plan(self,*,mode):
            modes.append(mode)
            return {'operations':{},'plan_sha256':f'plan-{len(modes)}'}
    class Publisher:
        def __init__(self,*args):pass
        def build_plan(self):return {'actions':[],'plan_sha256':'en-plan'}
    counter=iter(('safety-update-config.json','french-update-config.json'))
    def update_config(project_root,debate_id,release_copy,state_dir,languages,name):
        path=state_dir/next(counter);path.write_text('{}')
        return path,{}
    def english_config(project_root,debate_id,release_copy,state_dir):
        path=state_dir/'english-publication-config.json';path.write_text('{}')
        return path,{}
    monkeypatch.setattr(final,'RemoteUpdatePlanner',Planner)
    monkeypatch.setattr(final,'GenericPublisher',Publisher)
    monkeypatch.setattr(final,'build_adapter',lambda *args:object())
    monkeypatch.setattr(final,'_update_config',update_config)
    monkeypatch.setattr(final,'_english_config',english_config)
    monkeypatch.setattr(final,'_approved_english_updates',lambda *args:{})
    monkeypatch.setattr(final,'_assert_safe_update_plan',lambda *args,**kwargs:None)
    monkeypatch.setattr(final,'_assert_safe_english_plan',lambda *args,**kwargs:None)
    final._load_or_build_plans(tmp_path,'debate','work',tmp_path/'release',tmp_path)
    assert modes==['no_delete','no_delete']
