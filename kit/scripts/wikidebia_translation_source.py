"""Freeze a published import for translation without editing its French pages.

This is a preservation receipt, not a documentary re-verification. New French
content still follows the editorial content-review workflow.
"""
from __future__ import annotations
import copy
import collections
from decimal import Decimal
import hashlib
import os
from pathlib import Path
import shutil
import tempfile
import re
from typing import Any, Mapping

from wikidebia_corpus_build import canonical_json, full_tree_sha256, load_json, now_iso, write_json
from wikidebia_content_review import _outer_template, _source_imports, _assert_reviewed_copy
from wikidebia_editorial_review import _assert_source_unchanged, _load_workspace
from wikidebia_editorial_workspace import workspace_receipt_hash
from wikidebia_graph_extract import iter_templates, normalize_key

POLICY = "published-french-import-preserved-for-translation-1.0"

def historical_numbers_preserved(french: str, english: str) -> bool:
    """Check digit values, allowing an English spelling of a source number.

    This is transfer fidelity, never verification of the historical claim.
    Scope, units and words still require the semantic review.
    """
    def plain(s: str) -> str:
        s=re.sub(r'<ref\b[^>]*>.*?</ref\s*>',' ',s,flags=re.S|re.I)
        return re.sub(r'\[https?://\S+\s+([^\]]*)\]',r'\1',s)
    def digits(s: str, lang: str) -> list[Decimal] | None:
        text = plain(s)
        # Grouping conventions belong to the language, not the claim. In
        # particular, 5 M. 100.000 and 5,100,000 denote the same source value.
        numeric = (r'[+−-]?\d+(?:[, \u00a0\u202f]\d{3})*(?:\.\d+)?' if lang == 'en'
                   else r'[+−-]?\d+(?:[. \u00a0\u202f]\d{3})*(?:,\d+)?(?:\.\d+)?')
        def decimal(raw: str) -> Decimal:
            value = re.sub(r'[ \u00a0\u202f]', '', raw).replace('−', '-')
            if lang == 'en':
                value = value.replace(',', '')
            else:
                # A grouped French integer uses periods; other periods remain
                # decimal marks (e.g. a historical mathematical notation).
                if re.fullmatch(r'[+-]?\d{1,3}(?:\.\d{3})+(?:,\d+)?', value):
                    value = value.replace('.', '')
                value = value.replace(',', '.')
            return Decimal(value)
        # Only the explicit French abbreviation permits a compound remainder.
        # A year after "million" is not silently folded into the quantity.
        scale = r'(?:millions?|(?P<abbr>M\.))' if lang == 'fr' else r'millions?'
        remainder_pattern = r'(?(abbr)(?:\s+(' + numeric + r'))?)' if lang == 'fr' else ''
        pattern = re.compile(r'(?<!\w)(' + numeric + r')(?:\s*(' + scale + r')(?=\W|$)' + remainder_pattern + r')?', re.I)
        values = []
        for match in pattern.finditer(text):
            try:
                value = decimal(match[1])
            except ArithmeticError:
                return None
            if match[2]:
                value *= 1_000_000
                if lang == 'fr' and match[4]:
                    try:
                        remainder = decimal(match[4])
                    except ArithmeticError:
                        return None
                    if not 0 <= remainder < 1_000_000:
                        return None
                    value += -remainder if value.is_signed() else remainder
            values.append(value)
        return values
    source_values, target_values = digits(french, 'fr'), digits(english, 'en')
    if source_values is None or target_values is None:
        return False
    source=collections.Counter(source_values);target=collections.Counter(target_values)
    # No invented digit value, and no lost repeated digit occurrence.
    if target-source:return False
    missing=source-target
    words={w:Decimal(i) for i,w in enumerate(['zero','one','two','three','four','five','six','seven','eight','nine','ten','eleven','twelve','thirteen','fourteen','fifteen','sixteen','seventeen','eighteen','nineteen','twenty'])}
    spelled=collections.Counter(words[w] for w in re.findall(r'\b[a-z]+\b',plain(english).lower()) if w in words)
    return not (missing-spelled)

def _sha_text(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()

def _csv(value: str) -> list[str]:
    return [v.strip() for v in value.split(',') if v.strip()]

def relation_labels_from_source(source: Path) -> list[dict[str,Any]]:
    from wikidebia_translation_review import TranslationReviewError
    registry,debate,arguments=_source_imports(source)
    provenance=load_json(source/'data/import_provenance.json','provenance française')
    nodes={str(node.get('id')):node for node in (registry.get('graph') or {}).get('nodes') or [] if node.get('status')=='active'}
    title_to_id={}
    for row in provenance.get('pages') or []:
        if not isinstance(row,Mapping) or row.get('kind')!='argument' or not row.get('page_id'):
            continue
        node_id=str(row['page_id'])
        if row.get('status')=='pending_redirect' and row.get('pending_redirect_target_node_id') in nodes:
            node_id=str(row['pending_redirect_target_node_id'])
        for key in ('canonical_title','requested_title','source_graph_title'):
            title=str(row.get(key) or '').strip()
            if title:title_to_id[title]=node_id
    for node_id,node in nodes.items():
        title=str((node.get('fr') or {}).get('canonical_title') or '').strip()
        if title:title_to_id[title]=node_id
    historical_roots={}
    debate_template=_outer_template(source/debate['import_path'],{'debat'})
    for branch,param,name in [('pro','arguments-pour','argument pour'),('con','arguments-contre','argument contre')]:
        calls=[c for c in iter_templates(debate_template.get(param)) if normalize_key(c.name)==name]
        for call in calls:
            page=call.get('page').strip();node_id=title_to_id.get(page)
            if node_id:
                historical_roots[(branch,node_id)]=call.get('titre-affiché').strip() or page
    historical_edges={}
    for arg in arguments:
        template=_outer_template(source/arg['import_path'],{'argument'})
        for relation,param in [('justification','justifications'),('objection','objections')]:
            calls=[c for c in iter_templates(template.get(param)) if normalize_key(c.name)==relation]
            for call in calls:
                page=call.get('page').strip();child_id=title_to_id.get(page)
                if child_id:
                    historical_edges[(arg['id'],relation,child_id)]=call.get('titre-affiché').strip() or page
    result=[]
    for branch in ('pro','con'):
        occs=sorted([o for o in registry['graph']['occurrences'] if o.get('depth')==1 and o.get('branch')==branch],key=lambda o:(int(o.get('order') or 0),str(o.get('id') or '')))
        for occ in occs:
            node_id=str(occ['node_id']);fallback=str((nodes.get(node_id,{}).get('fr') or {}).get('displayed_title') or '')
            source_text=historical_roots.get((branch,node_id),fallback)
            if not source_text:raise TranslationReviewError('Titre affiché français principal absent : '+node_id)
            result.append(dict(id='root:'+occ['id'],source_page_id='debate',target_node_id=node_id,relation=branch,source_text=source_text))
    edges=sorted([e for e in registry['graph']['edges'] if e.get('status')=='active'],key=lambda e:(str(e.get('parent_node_id') or ''),str(e.get('relation') or ''),int(e.get('order') or 0),str(e.get('id') or '')))
    for edge in edges:
        parent_id=str(edge['parent_node_id']);child_id=str(edge['child_node_id']);relation=str(edge['relation'])
        fallback=str((nodes.get(child_id,{}).get('fr') or {}).get('displayed_title') or '')
        source_text=historical_edges.get((parent_id,relation,child_id))
        if source_text is None:
            previous_labels={label for (parent,_,child),label in historical_edges.items() if parent==parent_id and child==child_id}
            source_text=next(iter(previous_labels)) if len(previous_labels)==1 else fallback
        if not source_text:raise TranslationReviewError('Titre affiché français relationnel absent : '+str(edge.get('id')))
        result.append(dict(id='edge:'+str(edge['id']),source_page_id=parent_id,target_node_id=child_id,relation=relation,source_text=source_text))
    return result

def validate_relation_labels(rows: Any, source: Path) -> list[dict[str,Any]]:
    from wikidebia_translation_review import TranslationReviewError
    expected=relation_labels_from_source(source)
    if not isinstance(rows,list) or len(rows)!=len(expected):raise TranslationReviewError('Couverture des libellés contextuels incomplète')
    by_id={r.get('id'):r for r in rows if isinstance(r,dict)}
    if len(by_id)!=len(expected):raise TranslationReviewError('Libellés contextuels dupliqués')
    result=[]
    for original in expected:
        row=by_id.get(original['id'],{})
        if any(row.get(k)!=v for k,v in original.items()):raise TranslationReviewError('Source d’un libellé contextuel modifiée : '+original['id'])
        if not str(row.get('translated_text') or '').strip() or row.get('equivalent_to_french') is not True or len(str(row.get('review_note') or '').strip())<12:
            raise TranslationReviewError('Libellé contextuel non traduit ou non revu : '+original['id'])
        result.append(copy.deepcopy(row))
    return result

def freeze_imported_source(project_root: Path, debate_id: str, work_id: str, *, reviewer: str, note: str) -> dict[str, Any]:
    from wikidebia_translation_review import TranslationReviewError
    if len(reviewer.strip()) < 3 or len(note.strip()) < 30:
        raise TranslationReviewError("Le gel de source exige un relecteur et une justification explicite de préservation")
    workspace, meta = _load_workspace(project_root, debate_id, work_id)
    if meta.get('status') not in {'fr_titles_applied', 'fr_metadata_applied', 'fr_content_review_ready'}:
        raise TranslationReviewError("Le gel historique exige des titres français déjà revus et appliqués")
    _assert_source_unchanged(project_root, debate_id, meta)
    source = _assert_reviewed_copy(workspace, meta)
    target = workspace/'content-reviewed-copy'
    if target.exists():
        raise TranslationReviewError('Une base française existe déjà ; elle ne peut pas être écrasée')
    title_lock = load_json(source/'data/fr_page_metadata_lock.json', 'titres français verrouillés')
    registry, debate, arguments = _source_imports(source)
    provenance = load_json(source/'data/import_provenance.json', 'provenance française')
    imported = provenance.get('pages') or []
    if not imported or any(not r.get('revision_id') or not r.get('sha256') for r in imported):
        raise TranslationReviewError('Le gel exige des révisions distantes et empreintes attestées pour toutes les pages')
    for row in imported:
        path = source/row['import_path']
        if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != row['sha256']:
            raise TranslationReviewError('Import français divergent : '+str(row.get('import_path')))
    if any(s.get('page_origin') != 'preexisting' for s in [debate,*arguments]):
        raise TranslationReviewError('Les pages françaises nouvelles doivent suivre la revue de création')
    if (source/'output').exists():
        raise TranslationReviewError('Le gel ne reprend pas de pages finales')
    relation_labels_from_source(source)  # The reviewed graph must still match the imported pages.
    metadata = copy.deepcopy(title_lock)
    by_id = {r['entity_id']:r for r in metadata['arguments']}
    stamp = now_iso()
    pages = [('debate',debate,metadata['debate']), *[(r['id'],r,by_id[r['id']]) for r in arguments]]
    usages: dict[str,list[dict[str,str]]] = {}
    for page_id, content, page_meta in pages:
        template = _outer_template(source/content['import_path'], {'debat'} if page_id=='debate' else {'argument'})
        # Read actual imported parameters, never the importer's classification defaults.
        page_meta.update(id=page_id, rubriques=_csv(template.get('rubriques')),
                         keywords=_csv(template.get('mots-clés')),
                         source_parameter_presence=copy.deepcopy(content['source_parameter_presence']),
                         source_import_sha256=content['import_sha256'], source_preservation_policy=POLICY)
        for term in page_meta['keywords']:
            usages.setdefault(term,[]).append(dict(page_type='debate' if page_id=='debate' else 'argument',page_id=page_id))
    final_debate = copy.deepcopy(debate)
    final_debate.update(documentation={k:[] for k in debate['documentation_raw']},
        introduction_provenance='historical_existing' if debate['introduction'] else 'historical_absent',
        historical_introduction_present=bool(debate['introduction']), historical_introduction_sha256=_sha_text(debate['introduction']),
        historical_text_decision='preserved',historical_content_preserved=True,
        documentary_review_status='historical_references_preserved_not_reverified',source_preservation_policy=POLICY)
    final_arguments=[]
    for arg in arguments:
        row=copy.deepcopy(arg)
        row.update(sources={k:[] for k in arg['documentation_raw']},summary_provenance='historical_existing' if arg['summary'] else 'historical_absent',
            historical_summary_present=bool(arg['summary']),historical_summary_sha256=_sha_text(arg['summary']),
            historical_text_decision='preserved',historical_content_preserved=True,
            quantitative_claims_verified=False,documentary_review_status='historical_references_preserved_not_reverified',source_preservation_policy=POLICY)
        final_arguments.append(row)
    receipt=dict(schema='wikidebia-translation-source-preservation-1.0',policy=POLICY,debate_id=debate_id,work_id=work_id,
        status='frozen_as_imported',reviewer=reviewer,reviewed_at=stamp,note=note,
        documentary_reverification_claimed=False,french_pages_changed=False,pages=copy.deepcopy(imported))
    receipt['receipt_sha256']=hashlib.sha256(canonical_json(receipt)).hexdigest()
    metadata.update(source_preservation_policy=POLICY,source_preservation_receipt_sha256=receipt['receipt_sha256'])
    content=dict(schema='wikidebia-fr-content-lock-1.0',debate_id=debate_id,work_id=work_id,status='frozen_as_imported',
        review_sha256=receipt['receipt_sha256'],source_preservation_policy=POLICY,source_preservation_receipt_sha256=receipt['receipt_sha256'],
        debate=final_debate,arguments=final_arguments)
    # Vocabulary preserves source spellings and relevance order; no keyword quota or cleanup.
    lexical=load_json(workspace/'data/keyword_vocabulary_working.json','formes lexicales françaises')
    lexical_by_fr={r.get('fr'):r for r in lexical.get('entries') or []}
    entries=[]
    for term,term_usages in sorted(usages.items()):
        form=lexical_by_fr.get(term,{})
        if form.get('kind') not in {'noun','noun_phrase','proper_name','acronym'} or not form.get('capitalization_policy') or form.get('lexical_form_reviewed') is not True:
            raise TranslationReviewError('Forme lexicale source à revoir avant gel : '+term)
        entries.append(dict(concept_id='KWD-'+_sha_text(term)[:12].upper(),fr=term,en=None,
            kind=form['kind'],capitalization_policy=form['capitalization_policy'],
            usages=term_usages,status='source_preserved'))
    temporary=Path(tempfile.mkdtemp(prefix='.translation-source-',dir=workspace))
    shutil.copytree(source,temporary,dirs_exist_ok=True)
    write_json(temporary/'data/fr_page_metadata_lock.json',metadata)
    write_json(temporary/'data/fr_content_lock.json',content)
    write_json(temporary/'data/keyword_vocabulary.json',dict(debate_id=debate_id,entries=entries,status='source_preserved'))
    write_json(temporary/'data/source_preservation_receipt.json',receipt)
    verify_frozen_source(temporary,metadata,content)
    os.replace(temporary,target)
    tree_sha=full_tree_sha256(target)
    meta.update(status='fr_source_preserved',content_reviewed_copy=dict(tree_sha256=tree_sha,mode=POLICY),
                source_preservation=dict(policy=POLICY,receipt_sha256=receipt['receipt_sha256']))
    meta['workspace_sha256']=None
    meta['workspace_sha256']=workspace_receipt_hash(meta)
    write_json(workspace/'workspace.json',meta)
    readiness=load_json(workspace/'reviews/en/translation_readiness.json','préparation anglaise')
    readiness.update(status='ready_for_translation',source_preservation_policy=POLICY)
    write_json(workspace/'reviews/en/translation_readiness.json',readiness)
    return dict(status='fr_source_preserved',pages=len(imported),receipt_sha256=receipt['receipt_sha256'],french_pages_changed=False,documentary_reverification_claimed=False)

def verify_frozen_source(source: Path, metadata: Mapping[str, Any], content: Mapping[str, Any]) -> None:
    from wikidebia_translation_review import TranslationReviewError
    if not content.get('source_preservation_policy'):
        return
    if content.get('source_preservation_policy') != POLICY:
        raise TranslationReviewError('Politique de préservation historique inconnue')
    receipt=load_json(source/'data/source_preservation_receipt.json','reçu de préservation')
    body=copy.deepcopy(receipt);sha=body.pop('receipt_sha256',None)
    if sha!=hashlib.sha256(canonical_json(body)).hexdigest() or content.get('source_preservation_receipt_sha256')!=sha or metadata.get('source_preservation_receipt_sha256')!=sha:
        raise TranslationReviewError('Empreinte du reçu de source historique divergente')
    _,debate,arguments=_source_imports(source)
    locked={r['id']:r for r in content['arguments']};meta_by_id={r.get('id') or r.get('entity_id'):r for r in metadata['arguments']}
    for row in receipt['pages']:
        p=source/row['import_path']
        if p.is_symlink() or not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=row['sha256']:
            raise TranslationReviewError('Page historique modifiée après gel : '+row['import_path'])
    for page_id,original,frozen,page_meta in [('debate',debate,content['debate'],metadata['debate']), *[(r['id'],r,locked[r['id']],meta_by_id[r['id']]) for r in arguments]]:
        for field in ('introduction','summary','citations','citation_passages','documentation_raw','preserved_parameters','source_parameter_presence','import_sha256'):
            if original.get(field)!=frozen.get(field):
                raise TranslationReviewError(f'Champ français historique modifié : {page_id}/{field}')
        template=_outer_template(source/original['import_path'],{'debat'} if page_id=='debate' else {'argument'})
        if page_meta.get('rubriques')!=_csv(template.get('rubriques')) or page_meta.get('keywords')!=_csv(template.get('mots-clés')):
            raise TranslationReviewError('Classification historique non fidèle : '+page_id)
