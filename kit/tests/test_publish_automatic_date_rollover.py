from __future__ import annotations
import copy
import json
from pathlib import Path
import pytest
from test_wikidebia_publish import FakeAdapter, make_direct_profile, write_fixture, module


def ready_publisher(tmp_path, monkeypatch, *, count=2, languages=None):
    config,path,_,_=write_fixture(tmp_path,'full_page')
    corpus,manifest_path=make_direct_profile(config,path,tmp_path)
    manifest=json.loads(manifest_path.read_text())
    manifest['translation_status']={'en':'ready'}
    base=[r for r in manifest['pages'] if r['page_id']=='A1']
    registry=json.loads((corpus/'data/registre_debat.json').read_text())
    for i in range(2,count+1):
        for original in base:
            row=copy.deepcopy(original);row['page_id']=f'A{i}';row['canonical_title']+=f' {i}'
            old=corpus/row['file_path'];row['file_path']=row['file_path'].replace('A1.wiki',f'A{i}.wiki')
            (corpus/row['file_path']).write_bytes(old.read_bytes());manifest['pages'].append(row)
        node=copy.deepcopy(registry['graph']['nodes'][0]);node['id']=f'A{i}';node['en']['canonical_title']+=f' {i}'
        registry['graph']['nodes'].append(node)
    (corpus/'data/registre_debat.json').write_text(json.dumps(registry))
    if languages and 'fr' in languages:
        for row in manifest['pages']:
            if row['language']=='fr' and row['page_type']=='argument':
                target=next(r['canonical_title'] for r in manifest['pages'] if r['language']=='en' and r['page_id']==row['page_id'])
                source=corpus/row['file_path']
                source.write_text('{{Argument\n|résumé=Texte.\n|interlangue={{Lien interlangue\n|langue=en\n|page='+target+'\n}}\n|rubriques=Société\n}}\n')
                row['sha256']=module.sha_file(source)
    manifest_path.write_text(json.dumps(manifest))
    config['operation']['languages']=languages or ['en'];config['operation']['page_types']=['argument']
    path.write_text(json.dumps(config))
    clock=['2026-10-21']
    monkeypatch.setattr(module.GenericPublisher,'_current_publication_date',lambda self:clock[0])
    adapter=FakeAdapter();writes=[];original_write=adapter.write_page
    def write(**kwargs):
        revision=original_write(**kwargs);writes.append(kwargs['title'])
        return revision
    adapter.write_page=write
    publisher=module.GenericPublisher(config,adapter,path)
    # Date-rollover tests isolate time/revision guards from the independently
    # tested signed bilingual transaction authorization gate.
    monkeypatch.setattr(module.GenericPublisher, '_assert_paired_translation_authorization', lambda self, plan: None)
    plan=publisher.build_plan()
    return publisher,adapter,clock,writes,plan,path


def test_midnight_during_transfer_refreshes_only_remaining_creations(tmp_path,monkeypatch):
    pub,adapter,clock,writes,plan,_=ready_publisher(tmp_path,monkeypatch)
    before=copy.deepcopy(plan);source_before={r['source_path']:(pub.root/r['source_path']).read_bytes() for r in plan['actions']}
    write=adapter.write_page
    def at_midnight(**kwargs):
        revision=write(**kwargs);clock[0]='2026-10-22';return revision
    adapter.write_page=at_midnight
    counts=pub.publish_with_date_refresh(plan=plan,confirmation=plan['plan_sha256'],rollover_dir=tmp_path/'rollovers')
    assert counts=={'created':2,'updated':0,'skipped':0}
    assert writes==['Title EN','Title EN 2']
    assert '|creation-date=2026-10-21' in adapter.pages[('en','Title EN')][1]
    assert '|creation-date=2026-10-22' in adapter.pages[('en','Title EN 2')][1]
    assert plan==before
    assert all((pub.root/rel).read_bytes()==raw for rel,raw in source_before.items())
    audit_path=next((tmp_path/'rollovers').glob('*/rollover.json'));audit=json.loads(audit_path.read_text())
    assert audit['completed_before_rollover'][0]['page_id']=='A1'
    assert audit['remaining_after_rollover'][0]['page_id']=='A2'
    assert json.loads(audit_path.with_name('previous-plan.json').read_text())==plan
    state=json.loads((tmp_path/'.state/published/demo/en/latest.json').read_text())
    assert len(state['pages'])==2


def test_cli_refreshes_an_old_plan_before_the_first_write(tmp_path,monkeypatch,capsys):
    pub,adapter,clock,writes,plan,path=ready_publisher(tmp_path,monkeypatch)
    original=tmp_path/'plan.json';original.write_text(json.dumps(plan));before=original.read_bytes()
    clock[0]='2026-10-22'
    monkeypatch.setattr(module,'PywikibotAdapter',lambda *args:adapter)
    assert module.main(['--config',str(path),'--mode','publish','--execute',
        '--plan-input',str(original),'--confirm-plan-sha256',plan['plan_sha256']])==0
    output=capsys.readouterr()
    assert json.loads(output.out.splitlines()[-1])=={'created':2,'updated':0,'skipped':0}
    assert 'actualisée automatiquement' in output.err
    assert original.read_bytes()==before
    assert len(list((tmp_path/'publication-date-rollovers').glob('*/rollover.json')))==1
    assert len(writes)==2
    assert all('|creation-date=2026-10-22' in text for _,text in adapter.pages.values())


def test_multiple_midnights_do_not_duplicate_pages_or_counts(tmp_path,monkeypatch):
    pub,adapter,clock,writes,plan,_=ready_publisher(tmp_path,monkeypatch,count=3)
    write=adapter.write_page
    def next_day(**kwargs):
        revision=write(**kwargs);clock[0]=f'2026-10-{21+len(writes):02d}';return revision
    adapter.write_page=next_day
    counts=pub.publish_with_date_refresh(plan=plan,confirmation=plan['plan_sha256'],rollover_dir=tmp_path/'rollovers')
    assert counts=={'created':3,'updated':0,'skipped':0}
    assert len(set(writes))==len(writes)==3
    assert len(list((tmp_path/'rollovers').glob('*/rollover.json')))==2


@pytest.mark.parametrize('changed',['source','config','human_revision','tags'])
def test_midnight_never_waives_an_independent_blocker(tmp_path,monkeypatch,changed):
    pub,adapter,clock,writes,plan,path=ready_publisher(tmp_path,monkeypatch)
    write=adapter.write_page
    def drift(**kwargs):
        revision=write(**kwargs);clock[0]='2026-10-22'
        if changed=='source':
            (pub.root/plan['actions'][1]['source_path']).write_text('Changed source')
        elif changed=='config':
            path.write_text(path.read_text()+'\n')
        elif changed=='human_revision':
            key=('en',kwargs['title']);remote=adapter.pages[key][1]+'Human edit'
            adapter.pages[key]=(999,remote)
            adapter.revisions[999]={'parent_id':revision,'user':'Another user','text':remote}
        else:
            adapter.available_change_tags=lambda:set()
        return revision
    adapter.write_page=drift
    with pytest.raises(module.PublicationError):
        pub.publish_with_date_refresh(plan=plan,confirmation=plan['plan_sha256'],rollover_dir=tmp_path/'rollovers')
    assert len(writes)==1
    assert ('en','Title EN 2') not in adapter.pages


def test_clock_moving_backwards_is_not_automatically_authorized(tmp_path,monkeypatch):
    pub,adapter,clock,writes,plan,_=ready_publisher(tmp_path,monkeypatch)
    clock[0]='2026-10-20'
    with pytest.raises(module.PublicationError,match='non croissant'):
        pub.publish_with_date_refresh(plan=plan,confirmation=plan['plan_sha256'])
    assert not writes


def test_filtered_publication_keeps_its_scope_during_rollover(tmp_path,monkeypatch):
    pub,adapter,clock,writes,plan,_=ready_publisher(tmp_path,monkeypatch)
    clock[0]='2026-10-22'
    counts=pub.publish_with_date_refresh(plan=plan,confirmation=plan['plan_sha256'],page_id='A2')
    assert writes==['Title EN 2']
    assert counts=={'created':1,'updated':0,'skipped':0}


def test_resuming_on_another_day_preserves_each_original_creation_date(tmp_path,monkeypatch):
    pub,adapter,clock,writes,plan,_=ready_publisher(tmp_path,monkeypatch)
    write=adapter.write_page
    def at_midnight(**kwargs):
        revision=write(**kwargs);clock[0]='2026-10-22';return revision
    adapter.write_page=at_midnight
    pub.publish_with_date_refresh(plan=plan,confirmation=plan['plan_sha256'])
    before=copy.deepcopy(adapter.pages)
    clock[0]='2026-10-23'
    pub.publication_date=clock[0]
    resume=pub.build_plan()
    assert [a['publication_creation_date'] for a in resume['actions']]==['2026-10-21','2026-10-22']
    counts=pub.publish_with_date_refresh(plan=resume,confirmation=resume['plan_sha256'])
    assert counts=={'created':0,'updated':0,'skipped':2}
    assert adapter.pages==before
    assert len(writes)==2


def test_mixed_publication_does_not_rewrite_completed_french_pages(tmp_path,monkeypatch):
    pub,adapter,clock,writes,plan,_=ready_publisher(tmp_path,monkeypatch,languages=['fr','en'])
    write=adapter.write_page
    def at_midnight(**kwargs):
        revision=write(**kwargs)
        if kwargs['title']=='Title EN':
            clock[0]='2026-10-22'
        return revision
    adapter.write_page=at_midnight
    counts=pub.publish_with_date_refresh(plan=plan,confirmation=plan['plan_sha256'])
    assert counts=={'created':4,'updated':0,'skipped':0}
    assert len(writes)==len(set(writes))==4
    for action in plan['actions']:
        if action['language']=='fr':
            assert adapter.pages[('fr',action['title'])][1]==(pub.root/action['source_path']).read_text()
