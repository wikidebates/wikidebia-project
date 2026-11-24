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
    adapter=FakeAdapter();writes=[];original_write=adapter.write_page
    def write(**kwargs):
        revision=original_write(**kwargs);writes.append(kwargs['title'])
        return revision
    adapter.write_page=write
    publisher=module.GenericPublisher(config,adapter,path)
    # Publication tests isolate creation/revision guards from the independently
    # tested signed bilingual transaction authorization gate.
    monkeypatch.setattr(module.GenericPublisher, '_assert_paired_translation_authorization', lambda self, plan: None)
    plan=publisher.build_plan()
    return publisher,adapter,writes,plan,path


def test_publication_and_resume_without_creation_dates(tmp_path, monkeypatch):
    pub, adapter, writes, plan, _ = ready_publisher(tmp_path, monkeypatch)
    before = copy.deepcopy(plan)
    source_before = {r['source_path']: (pub.root/r['source_path']).read_bytes() for r in plan['actions']}
    assert 'publication_date' not in plan
    assert all('publication_creation_date' not in row for row in plan['actions'])
    assert pub.publish(plan=plan, confirmation=plan['plan_sha256']) == {'created':2,'updated':0,'skipped':0}
    assert all('|creation-date=' not in text for _,text in adapter.pages.values())
    assert plan == before
    assert all((pub.root/rel).read_bytes() == raw for rel,raw in source_before.items())
    resume = pub.build_plan()
    assert pub.publish(plan=resume, confirmation=resume['plan_sha256']) == {'created':0,'updated':0,'skipped':2}
    assert len(writes) == 2


def test_filtered_publication_keeps_scope(tmp_path, monkeypatch):
    pub, adapter, writes, plan, _ = ready_publisher(tmp_path, monkeypatch)
    assert pub.publish(plan=plan, confirmation=plan['plan_sha256'], page_id='A2') == {'created':1,'updated':0,'skipped':0}
    assert writes == ['Title EN 2']


def test_source_changed_after_plan_remains_blocking(tmp_path, monkeypatch):
    pub, adapter, writes, plan, _ = ready_publisher(tmp_path, monkeypatch)
    (pub.root/plan['actions'][0]['source_path']).write_text('Changed source')
    with pytest.raises(module.PublicationError):
        pub.publish(plan=plan, confirmation=plan['plan_sha256'])
    assert not writes


def test_legacy_date_in_full_page_payload_is_blocked(tmp_path, monkeypatch):
    pub, adapter, writes, plan, _ = ready_publisher(tmp_path, monkeypatch)
    row = pub._manifest_page('en', 'A1')
    with pytest.raises(module.PublicationError, match='date de création obsolète'):
        pub._publication_text(row, '{{Argument|summary=Demo|creation-date=2000-01-01}}')
    assert not writes
