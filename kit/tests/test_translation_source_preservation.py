from __future__ import annotations
import copy
import hashlib
import json
import shutil
from pathlib import Path
import pytest
from test_wikidebia_content_review import make_metadata_applied, content, complete_content_review
from test_wikidebia_editorial_workspace import make_promoted_project
from test_wikidebia_editorial_review import complete_review, review_tool, workspace_tool
import wikidebia_translation_review as translation
import wikidebia_translation_source as preservation
import wikidebia_french_checkpoint as french_checkpoint
import wikidebia_graph_actions as graph_actions
from wikidebia_editorial_workspace import capitalization_policy_for_kind

def prepared(tmp_path):
    project, _=make_promoted_project(tmp_path)
    work_id='PRESERVE-SOURCE-001'
    workspace_tool.create_workspace(project,'debat_test',work_id)
    workspace=project/'.state/editorial-workspaces/debat_test'/work_id
    validator=Path(__file__).resolve().parents[2]/'validator'
    for folder in ['src','scripts']:shutil.copytree(validator/folder,project/'validator'/folder)
    for filename in ['VERSIONS.json','CAPABILITIES.json']:shutil.copy2(validator/filename,project/'validator'/filename)
    complete_review(workspace)
    p=workspace/'reviews/fr/page_metadata_review.json';data=json.loads(p.read_text())
    for item in data['items']:
        item['review'].update(canonical_title_decision='keep',displayed_title_decision='keep' if item['entity_type']=='argument' else 'not_applicable',canonical_title_rationale='Titre historique conservé exactement sans réécriture.',displayed_title_rationale='Libellé historique conservé exactement sans réécriture.')
    p.write_text(json.dumps(data))
    sealed=review_tool.finalize_title_review(project,'debat_test',work_id)
    review_tool.apply_title_review(project,'debat_test',work_id,sealed['review_sha256'])
    content.prepare_review(project,'debat_test',work_id)
    p=workspace/'data/keyword_vocabulary_working.json'
    data=json.loads(p.read_text())
    for row in data['entries']:
        row.update(kind='noun',capitalization_policy=capitalization_policy_for_kind('noun'),lexical_form_reviewed=True)
    p.write_text(json.dumps(data))
    return project,workspace,work_id

def freeze(project,work_id):
    return preservation.freeze_imported_source(project,'debat_test',work_id,reviewer='Test reviewer',note='Preserve the complete published French snapshot without rewriting its content or claiming documentary re-verification.')

def test_source_freeze_is_not_a_documentary_approval_and_cannot_overwrite(tmp_path):
    project,workspace,work_id=prepared(tmp_path)
    before=content.full_tree_sha256(workspace/'reviewed-copy')
    original={str(p.relative_to(workspace/'reviewed-copy')):p.read_bytes() for p in (workspace/'reviewed-copy/imports').rglob('*.wiki')}
    result=freeze(project,work_id)
    assert result['french_pages_changed'] is False
    assert result['documentary_reverification_claimed'] is False
    assert content.full_tree_sha256(workspace/'reviewed-copy')==before
    for rel,b in original.items():assert (workspace/'content-reviewed-copy'/rel).read_bytes()==b
    locked=json.loads((workspace/'content-reviewed-copy/data/fr_content_lock.json').read_text())
    assert all(r['quantitative_claims_verified'] is False for r in locked['arguments'])
    vocabulary = json.loads((workspace/'content-reviewed-copy/data/keyword_vocabulary.json').read_text())
    assert vocabulary['entries']
    for entry in vocabulary['entries']:
        assert entry['atomic_concept'] is True
        assert entry['compositional_intersection'] is False
        assert entry['scope'] == 'site_navigation'
        assert entry['cross_debate_reusable'] is True
        assert entry['local_frequency_is_validity_criterion'] is False
        assert entry['usage_count_in_debate'] == sum(
            usage['page_type'] == 'argument' for usage in entry['usages']
        )
    assert translation.prepare_review(project,'debat_test',work_id)['status']=='en_translation_review_ready'
    with pytest.raises(translation.TranslationReviewError):freeze(project,work_id)


def test_preserved_source_content_checkpoint_reuses_graph_output_exactly(tmp_path):
    project, workspace, work_id = prepared(tmp_path)
    graph = french_checkpoint.build_checkpoint(project, 'debat_test', work_id, stage='graph')
    freeze(project, work_id)
    content = french_checkpoint.build_checkpoint(project, 'debat_test', work_id, stage='content')
    graph_pages = {
        path.relative_to(graph / 'output/fr').as_posix(): path.read_bytes()
        for path in (graph / 'output/fr').rglob('*.wiki')
    }
    content_pages = {
        path.relative_to(content / 'output/fr').as_posix(): path.read_bytes()
        for path in (content / 'output/fr').rglob('*.wiki')
    }
    assert content_pages == graph_pages
    record = json.loads((content / 'data/fr_publication_checkpoint.json').read_text())
    lock = json.loads((content / 'data/fr_content_lock.json').read_text())
    assert record['stage'] == 'content'
    assert record['source_preservation_policy'] == preservation.POLICY
    assert record['source_content_review_sha256'] == lock['review_sha256']


def test_source_freeze_inherits_effective_metadata_preserved_by_graph_publication(tmp_path):
    project, workspace, work_id = prepared(tmp_path)
    graph = french_checkpoint.build_checkpoint(project, 'debat_test', work_id, stage='graph')
    manifest = json.loads((graph / 'manifest.json').read_text())
    effective_root = project / '.state/update-effective/debat_test/fr'
    effective_root.mkdir(parents=True)
    operations = {name: [] for name in (
        'create','update','move','redirect','delete','skip','manual_review','blocked',
    )}
    state_pages = []
    for page in manifest['pages']:
        source = graph / page['file_path']
        operation_name = 'skip'
        if page['page_id'] == 'A0001':
            payload = source.read_text(encoding='utf-8')
            payload = graph_actions._set_optional_parameter_value(payload, 'argument', 'rubriques', 'Société')
            payload = graph_actions._set_optional_parameter_value(payload, 'argument', 'mots-clés', 'féminisme')
            source = effective_root / 'A0001-effective.wiki'
            source.write_text(payload, encoding='utf-8', newline='\n')
            operation_name = 'update'
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        operations[operation_name].append({
            'language':'fr', 'page_id':page['page_id'], 'page_type':page['page_type'],
            'title':page['canonical_title'], 'phase':3 if operation_name == 'update' else 0,
            'new_sha256':digest, 'local_file_sha256':digest,
            'source_path':source.relative_to(project).as_posix(),
        })
        state_pages.append({
            'page_id':page['page_id'], 'page_type':page['page_type'],
            'canonical_title':page['canonical_title'], 'content_sha256':digest,
            'revision_id':1000 + len(state_pages), 'status':'published',
        })
    plan={'debate_id':'debat_test','operations':operations}
    plan['plan_sha256']=french_checkpoint.sha_object(plan)
    graph_state=project/'.state/fr-publication/debat_test'/work_id/'graph'
    french_checkpoint.write_json(graph_state/'update-plan.json',plan)
    published={
        'state_version':'wikidebia-published-state-1.0','debate_id':'debat_test',
        'language':'fr','pages':state_pages,
    }
    published['state_sha256']=french_checkpoint.sha_object(published)
    french_checkpoint.write_json(project/'.state/published/debat_test/fr/latest.json',published)
    receipt={
        'schema':french_checkpoint.RECEIPT_SCHEMA,'schema_version':'1.0','debate_id':'debat_test',
        'work_id':work_id,'stage':'graph','status':'published',
        'plan_path':(graph_state/'update-plan.json').relative_to(project).as_posix(),
        'plan_sha256':plan['plan_sha256'],'published_state':{'state_sha256':published['state_sha256']},
    }
    receipt['receipt_sha256']=french_checkpoint.sha_object(receipt)
    french_checkpoint.write_json(graph_state/'publication-receipt.json',receipt)

    result=freeze(project,work_id)
    assert result['french_pages_changed'] is False
    frozen=workspace/'content-reviewed-copy'
    provenance=json.loads((frozen/'data/import_provenance.json').read_text())
    row=next(row for row in provenance['pages'] if row.get('page_id')=='A0001')
    text=(frozen/row['import_path']).read_text(encoding='utf-8')
    assert '|rubriques=Société' in text
    assert '|mots-clés=féminisme' in text
    metadata=json.loads((frozen/'data/fr_page_metadata_lock.json').read_text())
    locked=next(row for row in metadata['arguments'] if row['id']=='A0001')
    assert locked['rubriques']==['Société']
    assert locked['keywords']==['féminisme']
    receipt=json.loads((frozen/'data/source_preservation_receipt.json').read_text())
    frozen_row=next(row for row in receipt['pages'] if row.get('page_id')=='A0001')
    assert frozen_row['sha256']==hashlib.sha256((frozen/row['import_path']).read_bytes()).hexdigest()

def test_modified_reviewed_copy_is_rejected_before_freeze(tmp_path):
    project,workspace,work_id=prepared(tmp_path)
    page=next((workspace/'reviewed-copy/imports').rglob('*.wiki'))
    page.write_text(page.read_text()+'\nChanged after title review')
    with pytest.raises(Exception,match='changé|diverg'):freeze(project,work_id)
    assert not (workspace/'content-reviewed-copy').exists()

def test_frozen_import_or_documentation_cannot_drift(tmp_path):
    project,workspace,work_id=prepared(tmp_path);freeze(project,work_id)
    root=workspace/'content-reviewed-copy';m=json.loads((root/'data/fr_page_metadata_lock.json').read_text());c=json.loads((root/'data/fr_content_lock.json').read_text())
    preservation.verify_frozen_source(root,m,c)
    c['arguments'][0]['documentation_raw']['webliography']='Replacement reference'
    with pytest.raises(translation.TranslationReviewError,match='Champ français historique modifié'):preservation.verify_frozen_source(root,m,c)

@pytest.mark.parametrize('fr,en,expected',[
    ('260 000 emplois en 2018','260,000 jobs in 2018',True),
    ('un facteur 2 et 0,5 g/l','a factor of two and 0.5 g/L',True),
    ('260 000 emplois','26,000 jobs',False),
    ('-7,2 %','+7.2%',False),
    ('13 %','13% and 20%',False),
    ('13 % et 13 %','13%',False),
])
def test_historical_number_fidelity_is_separate_from_truth(fr,en,expected):
    assert preservation.historical_numbers_preserved(fr,en) is expected

def test_creation_duplicate_keywords_still_rejected():
    with pytest.raises(translation.TranslationReviewError,match='doublon'):
        translation._strings(['cannabis','cannabis'],'keywords')
    assert translation._strings(['cannabis','cannabis'],'keywords',allow_source_duplicates=True)==['cannabis','cannabis']

def test_quote_mutation_changes_semantic_content_hash():
    review={
        'arguments':[{'id':'A0001','translation':{'french':{'content':{'citations':[{'citation':'Texte français'}]}}}}],
        'final_values':{'debate':{},'arguments':[{'id':'A0001','citations':[{'quote':'The English quotation'}]}]},
    }
    before=translation.semantic_content_sha256(review)
    changed=copy.deepcopy(review);changed['final_values']['arguments'][0]['citations'][0]['quote']='A different claim'
    assert translation.semantic_content_sha256(changed)!=before

def test_relation_label_source_coverage_is_mandatory(tmp_path):
    project,workspace,work_id=prepared(tmp_path);freeze(project,work_id)
    root=workspace/'content-reviewed-copy';rows=preservation.relation_labels_from_source(root)
    for row in rows:row.update(translated_text='Translated contextual label',equivalent_to_french=True,review_note='The contextual source label has been compared independently.')
    assert len(preservation.validate_relation_labels(rows,root))==len(rows)
    with pytest.raises(translation.TranslationReviewError,match='incomplète'):preservation.validate_relation_labels(rows[:-1],root)
    changed=copy.deepcopy(rows);changed[0]['source_text']='Different source'
    with pytest.raises(translation.TranslationReviewError,match='Source'):preservation.validate_relation_labels(changed,root)


def test_duplicate_relations_to_same_target_keep_each_contextual_label(tmp_path, monkeypatch):
    source = tmp_path / 'source'
    source.mkdir()
    (source / 'debate.wiki').write_text('{{Débat}}\n', encoding='utf-8')
    (source / 'argument.wiki').write_text(
        '{{Argument\n'
        '|objections={{Objection|page=Cible|titre-affiché=Premier contexte}}'
        '{{Objection|page=Cible|titre-affiché=Second contexte}}\n'
        '}}\n',
        encoding='utf-8',
    )
    registry = {
        'graph': {
            'nodes': [
                {'id': 'A0001', 'status': 'active', 'fr': {'canonical_title': 'Parent'}},
                {
                    'id': 'A0002', 'status': 'active',
                    'fr': {'canonical_title': 'Cible', 'displayed_title': 'Titre global'},
                },
            ],
            'occurrences': [],
            'edges': [
                {
                    'id': 'E00001', 'status': 'active', 'parent_node_id': 'A0001',
                    'child_node_id': 'A0002', 'relation': 'objection', 'order': 1,
                },
                {
                    'id': 'E00002', 'status': 'active', 'parent_node_id': 'A0001',
                    'child_node_id': 'A0002', 'relation': 'objection', 'order': 2,
                },
            ],
        },
    }
    provenance = {
        'pages': [
            {'kind': 'argument', 'page_id': 'A0001', 'canonical_title': 'Parent'},
            {'kind': 'argument', 'page_id': 'A0002', 'canonical_title': 'Cible'},
        ],
    }
    monkeypatch.setattr(
        preservation,
        '_source_imports',
        lambda unused: (
            registry,
            {'import_path': 'debate.wiki'},
            [{'id': 'A0001', 'import_path': 'argument.wiki'}],
        ),
    )
    monkeypatch.setattr(preservation, 'load_json', lambda *args, **kwargs: provenance)

    rows = preservation.relation_labels_from_source(source)

    assert [row['source_text'] for row in rows] == ['Premier contexte', 'Second contexte']
    assert [row['id'] for row in rows] == ['edge:E00001', 'edge:E00002']

def test_historical_numbers_do_not_acquire_a_false_verification(tmp_path):
    project,workspace,work_id=prepared(tmp_path);complete_content_review(workspace)
    review=json.loads((workspace/'reviews/fr/content_review.json').read_text());item=review['arguments'][0]
    item['source']['summary']='Une assertion historique de 260 000 emplois non revérifiée.'
    r=item['review'];r.update(proposed_summary=item['source']['summary'],historical_summary_present=True,
        historical_summary_sha256=hashlib.sha256(item['source']['summary'].encode()).hexdigest(),quantitative_claims_verified=False)
    sources=json.loads((workspace/'data/sources_working.json').read_text())
    _,by_id=content._validate_source_registry(sources,'debat_test')
    assert content._validate_argument(item,by_id)['quantitative_claims_verified'] is False

def test_french_render_preserves_every_historical_parameter_and_comments(tmp_path):
    import re
    from wikidebia_graph_extract import parse_template
    from wikidebia_render import _render_preserved_french, RenderError
    raw = "<!-- header {{ignored}} -->\n{{Argument\n|résumé=Une ancienne formulation.\n|citations={{Citation|citation=Exactement !|auteurs=Un auteur}}\nTexte entre les citations.\n|webliographie=[https://example.org Ancienne source]\n|mots-clés=justice, justice\n|date-création=2001-01-01\n}}"
    p=tmp_path/'imports/fr/arguments/A1.wiki';p.parent.mkdir(parents=True);p.write_text(raw)
    locked={'import_path':str(p.relative_to(tmp_path)),'import_sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
    result=_render_preserved_french(tmp_path,locked,'An English title')
    fr=parse_template(raw[raw.index('{{Argument'):].strip())
    en=parse_template(result[result.index('{{Argument'):].strip())
    assert len(en.params)==len(fr.params)+1
    assert all(en.get(k)==v for k,v in fr.params.items())
    assert re.sub(r'\|interlangue=\{\{Lien interlangue.*?\}\}\n','',result,flags=re.S).rstrip('\n')==raw
    assert result.startswith('<!-- header {{ignored}} -->')
    assert 'langue=en' in en.get('interlangue')
    p.write_text(raw+'changed')
    with pytest.raises(RenderError,match='modifié'):_render_preserved_french(tmp_path,locked,'Title')

def test_french_render_never_replaces_existing_interlanguage(tmp_path):
    from wikidebia_render import _render_preserved_french, RenderError
    p=tmp_path/'page.wiki';p.write_text('{{Argument|interlangue={{Lien interlangue|langue=en|page=Existing}}}}\n')
    locked={'import_path':'page.wiki','import_sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
    with pytest.raises(RenderError,match='existe déjà'):_render_preserved_french(tmp_path,locked,'Different')


def test_preserved_french_graph_baseline_updates_page_target_only(tmp_path):
    from wikidebia_render import _render_graph_aligned_french_source
    from wikidebia_graph_extract import parse_template

    raw = (
        "{{Argument\n"
        "|justifications={{Justification|page=Ancien titre|titre-affiché=Libellé historique}}\n"
        "|objections=\n"
        "|rubriques=Société\n"
        "}}\n"
    )
    path = tmp_path / "imports/fr/arguments/A0001.wiki"
    path.parent.mkdir(parents=True)
    path.write_text(raw, encoding="utf-8")
    locked = {
        "import_path": path.relative_to(tmp_path).as_posix(),
        "import_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "preserved_parameters": {"débat-dédié": {"present": False, "value": None}},
    }
    registry = {"graph": {
        "depth_policy": {"limit_policy": "unbounded", "frontier_node_ids": []},
        "nodes": [
            {"id": "A0001", "status": "active", "fr": {"canonical_title": "Parent", "displayed_title": "Parent"}},
            {"id": "A0002", "status": "active", "fr": {"canonical_title": "Nouveau titre", "displayed_title": "Libellé global"}},
        ],
        "edges": [
            {"id": "E00001", "status": "active", "parent_node_id": "A0001", "child_node_id": "A0002", "relation": "justification", "order": 1},
        ],
    }}
    rendered = _render_graph_aligned_french_source(
        tmp_path,
        locked,
        registry,
        page_id="A0001",
        page_type="argument",
        contextual_labels=[{
            "id": "edge:E00001",
            "source_page_id": "A0001",
            "source_text": "Libellé historique",
        }],
    )
    parsed = parse_template(rendered.strip())
    relation = parse_template(parsed.get("justifications"))
    assert relation.get("page") == "Nouveau titre"
    assert relation.get("titre-affiché") == "Libellé historique"
    assert "|objections=" not in rendered
    assert "|rubriques=Société" in rendered

def test_reopening_an_applied_review_archives_the_complete_previous_tree(tmp_path):
    from test_wikidebia_translation_review import make_french_locked, complete_translation_review, complete_semantic_convergence, translation as tool
    project,workspace,work_id=make_french_locked(tmp_path)
    tool.prepare_review(project,'debat_test',work_id);complete_translation_review(workspace)
    sealed=tool.finalize_review(project,'debat_test',work_id);complete_semantic_convergence(project,work_id)
    tool.apply_review(project,'debat_test',work_id,sealed['review_sha256'])
    digest=tool.full_tree_sha256(workspace/'translated-copy')
    tool.reopen_review(project,'debat_test',work_id,reviewer='Test reviewer',note='Reopen a pre-render review after finding a concrete translation error, preserving the previous application.')
    archived=workspace/'reviews/en/history'/('translated-copy.'+sealed['review_sha256'])
    assert tool.full_tree_sha256(archived)==digest
    assert not (workspace/'translated-copy').exists()
    assert json.loads((workspace/'reviews/en/translation_review.json').read_text())['status']=='draft'
    assert (workspace/'content-reviewed-copy').is_dir()

@pytest.mark.parametrize('fr,en,expected', [
    ('5 M. 100.000 et non 6 Millions', '5,100,000 rather than 6 million', True),
    ('5 M. 100.000', '5,000,100', False),
    ('2,5 millions', '2.5 million', True),
    ('1.234.567', '1,234,567', True),
    ('100.000', '100', False),
    ('0,5', '0.5', True),
    ('5 M. 100.000 et 5 M. 100.000', '5,100,000', False),
])
def test_historical_grouping_and_million_notation(fr, en, expected):
    assert preservation.historical_numbers_preserved(fr, en) is expected

@pytest.mark.parametrize('fr,en,expected', [
    ('-5 M. 100.000', '-5,100,000', True),
    ('-5 M. 100.000', '5,100,000', False),
    ('6 millions 2018', '6 million 2018', True),
    ('1.234.56', '1,234.56', False),
])
def test_historical_number_parser_is_signed_and_fails_closed(fr, en, expected):
    assert preservation.historical_numbers_preserved(fr, en) is expected
