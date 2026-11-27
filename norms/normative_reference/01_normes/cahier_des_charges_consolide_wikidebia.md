## Exigences actives 1.2.76 — revue des changements idiomatiques et corpus réel

La traduction champ-à-champ reste source-authoritative. Un changement de forme du `displayed-title` n’est pas une erreur en soi lorsqu’il est idiomatique : il exige une revue explicite du même acte de langage, de la même thèse et de la même portée, plus une justification non vide. Toute proposition source dégradée en fragment reste bloquante. Les familles de risques sémantiques du kit et du validateur sont contractuellement alignées. Un corpus de fixtures dérivé des erreurs réelles contient des couples `fr`, `bad_en`, `good_en` et les signaux attendus. Les risques effectivement détectés sont documentés par des extraits source/cible. La page Debate bénéficie des mêmes empreintes et preuves de champ que les Arguments.

# Cahier des charges consolidé de Wikidéb'IA

- **Révision du paquet :** 1.0.6
- **Date :** 2026-07-23
- **Statut :** source normative de plus haut niveau pour l'intention éditoriale et opérationnelle

## 1. Objet et règle de priorité

Ce document récapitule les desiderata des trois prompts d'origine (graphe, page Débat, pages Argument), le résumé méthodologique, les structures officielles, les réponses explicites données pendant la conception et les corrections issues des audits.

Les fichiers d’origine ayant alimenté la consolidation ne sont pas distribués séparément dans le paquet actif. Leur provenance conceptuelle et les fichiers consolidés qui en reprennent les exigences sont décrits dans `00_sources_reference/PROVENANCE_DOCUMENTAIRE.md`. Aucune conservation octet pour octet d’un fichier absent n’est revendiquée.

En cas de conflit, l'ordre de priorité est :

1. décision explicite la plus récente de l'utilisateur ;
2. présent cahier des charges consolidé ;
3. structures MediaWiki officielles pour la syntaxe autorisée ;
4. profils de rendu, schéma du registre et workflow ;
5. prompts d'origine, conservés comme provenance mais non comme norme lorsqu'ils ont été remplacés.

Les décisions ultérieures sont réunies dans `00_sources_reference/DECISIONS_CONVERSATION_CONSOLIDEES.md`.

Le catalogue machine-readable complet est `requirements_catalog_wikidebia.json` et son objet `source_aliases` résout chaque étiquette de provenance vers un fichier réel.

## 2. Classification des contrôles

- `automatic` : contrôle déterministe attendu du validateur ou des scripts ;
- `heuristic` : signalement automatique possible mais non preuve définitive ;
- `human` : jugement éditorial nécessaire ;
- `prompt` : comportement à intégrer aux prompts Work définitifs.

## 3. Gouvernance et priorité

- **GOV-001 — ACTIVE — human+prompt** : The consolidated requirements baseline is the highest-level expression of user intent; structures define allowed syntax, profiles define rendering, the registry defines data, and the workflow defines execution.
- **GOV-002 — ACTIVE — human+prompt** : When an original prompt conflicts with a later explicit user decision, the later decision prevails and the superseded rule remains documented.
- **GOV-003 — ACTIVE — automatic+human** : Normative versions must be explicit; no validated debate package is silently migrated to a newer norm.
- **GOV-004 — ACTIVE — human+prompt** : The active system is French-English only; Spanish or another language requires a new explicit version.
- **GOV-005 — ACTIVE — automatic+human** : All structural choices must be persisted in files; conversation memory is never a source of truth.

## 4. Organisation des Projets et des Work

- **ORG-001 — ACTIVE — human+prompt** : Use two ChatGPT projects: Wikidéb'IA for active production and Archives de Wikidéb'IA for completed debates.
- **ORG-002 — ACTIVE — human+prompt** : Move completed Work conversations to the archive project; generic conversation archiving is not a substitute.
- **ORG-003 — ACTIVE — human+prompt** : A Work cannot contain another Work; all Work conversations are autonomous and of the same level.
- **ORG-004 — ACTIVE — human+prompt** : Separate graph research, debate writing, argument writing, validation, English adaptation, interlanguage and publication into specialized Work.
- **ORG-005 — ACTIVE — human+prompt** : Lock canonical English titles after graph validation and before generating French pages; produce the English page content only after French validation.
- **ORG-006 — ACTIVE — automatic+human** : Work 03 and Work 07 batches of the same language are sequential unless an explicit future concurrency protocol is introduced.
- **ORG-007 — ACTIVE — prompt guidance** : Prefer high reasoning for ordinary production, very high reasoning for complex/final graph and validation tasks, and maximum only exceptionally when available.
- **ORG-008 — ACTIVE — human+prompt** : The method may use a local directory but must not depend on one to function in the two-project organization.

## 5. Structures et rendu MediaWiki

- **MW-001 — ACTIVE — automatic** : Use only parameters and nested templates allowed by the official French and English structures.
- **MW-002 — ACTIVE — automatic** : Preserve canonical parameter order, spelling, accents, capitalization and hyphenation.
- **MW-003 — ACTIVE — automatic** : Omit every optional parameter and nested parameter that has no relevant content; mandatory parameters may never be empty.
  - Motif/évolution : Supersedes original debate-prompt instruction to retain empty parameters.
- **MW-004 — ACTIVE — automatic** : Allowed-but-not-generated warning parameters remain in the structural schema but are absent from automatic output.
- **MW-005 — ACTIVE — automatic** : A newly created French Debate uses avancement=Débat construit; an existing Debate preserves the exact previous presence and value of avancement.
- **MW-006 — ACTIVE — automatic+human** : A genuinely new English Debate generated from scratch uses progress=Constructed debate. An English Debate produced by translating a French page instead maps the exact French avancement value to progress; an absent source field remains absent. Existing-page preservation remains a technical publication rule, not a source for the editorial translation.
- **MW-007 — ACTIVE — automatic+human** : Add exact AI warnings only to pages genuinely created from scratch by Wikidéb’IA. A newly generated English translation file does not receive an AI warning by default: title/debate/argument warnings are translated from the French source values, and absent source fields remain absent.
- **MW-008 — ACTIVE — automatic** : Do not invent nom-consacré/established-name or initialisation/initialization automatically. For every new Argument page, research whether a conventional name is attested in the literature and emit nom-consacré/established-name only when the dedicated discovery review concludes known_name; preserve legacy nom/name exactly only on attested pre-existing pages, and allow new additions to preexisting pages only through an explicit owner-approved assignment review.
- **MW-009 — SUPERSEDED — automatic** : Do not generate citations/quotes in Argument pages. Replaced by the locked-citation rendering rules RND-003 and RND-004 from revision 1.2.27.
- **MW-010 — ACTIVE — automatic** : Preserve an attested historical `débat-dédié` / `dedicated-debate` parameter exactly. Local justifications and objections may be omitted only when the omission and owner notification are locked.
- **MW-011 — ACTIVE — automatic** : The obsolete top-level date-création and creation-date parameters are forbidden in all four current page types.
- **MW-012 — ACTIVE — automatic** : Current artifacts do not generate page creation dates; historical date metadata remains readable in immutable archives and must not be republished.
- **MW-013 — ACTIVE — automatic** : Publication date is stored separately in import logs.
- **MW-014 — ACTIVE — automatic** : French and English templates and parameters must never be mixed.
- **MW-015 — ACTIVE — automatic** : Generated wikicode must be complete UTF-8 and contain no explanatory comments inside page content.

Le contrat actif des citations textuelles distingue la traduction IA et le passage publié vérifié (RND-003, RND-004, RND-006 à RND-008). Les preuves d'édition, de droits et de complétude demeurent distinctes. Les nouvelles citations ne créent aucun doublon entre pages distinctes du même wiki (RND-010). Les reçus publiés restent liés à leur occurrence et ne sont pas des champs de mémoire de traduction générique (RND-011).

## 6. Titres et identité

- **TTL-001 — ACTIVE — automatic** : Every argument page has a stable internal identifier that is the source of truth for relations, files, translations and imports.
- **TTL-002 — ACTIVE — human+automatic heuristics** : Canonical titles are complete autonomous argumentative propositions, not themes, and are understandable outside the local branch.
- **TTL-003 — ACTIVE — human+automatic heuristics** : Add the debate subject to a canonical title when necessary to avoid ambiguity with other pages.
- **TTL-004 — ACTIVE — human+automatic heuristics** : Displayed titles may be shorter than canonical titles, but each remains a complete intelligible argumentative proposition with an explicit subject and predicate; a nominal topic label is insufficient.
- **TTL-005 — ACTIVE — human+warning** : Canonical and displayed titles must not be made identical by automation when contextual shortening is useful.
- **TTL-006 — ACTIVE — automatic** : No canonical or displayed title ends with a period.
- **TTL-007 — ACTIVE — automatic** : Use straight apostrophes and reject typographic apostrophes in French and English titles.
- **TTL-008 — ACTIVE — automatic** : Normalize and lock every French canonical and displayed title before French page generation.
- **TTL-009 — ACTIVE — automatic** : Fix and lock English canonical and displayed titles only after complete French validation.
- **TTL-010 — ACTIVE — human** : English titles are idiomatic, autonomous, conceptually equivalent and avoid contractions when they reduce encyclopedic tone.
- **TTL-011 — ACTIVE — automatic** : Locked titles can change only through an explicit migration that updates every dependent link and file.

## 7. Graphe argumentatif

- **GR-001 — ACTIVE — automatic** : The final logical structure is a directed acyclic graph, not merely a tree.
- **GR-002 — ACTIVE — automatic** : Distinguish nodes, edges and occurrences.
- **GR-003 — ACTIVE — automatic** : Camp and depth belong to occurrences, not to node identity.
- **GR-004 — ACTIVE — automatic** : One logical argument corresponds to one page per language even when reused in several branches or depths.
- **GR-005 — ACTIVE — automatic** : Each active node has exactly one primary occurrence; additional occurrences are secondary and do not render children.
- **GR-006 — ACTIVE — automatic** : The rendered graph root is the exact French debate title and has exactly two main branches.
- **GR-007 — ACTIVE — human** : Maximize coverage of important reasoning, not raw node count; exclude decorative examples, administrative details and weak reformulations as autonomous nodes.
- **GR-008 — ACTIVE — human+metrics** : The graph must be balanced across camps without imposing artificial numerical symmetry.
- **GR-009 — ACTIVE — automatic** : No cycles, self-relations, duplicate direct relations, duplicate direct children or unknown relations.
- **GR-010 — ACTIVE — human+automatic heuristics** : A child must directly justify or object to its parent rather than merely relate to the general debate.
- **GR-011 — ACTIVE — automatic+human** : Graph depth is unbounded; maximum observed depth is descriptive only and no warning or exceptional justification is triggered by a numeric threshold.
  - Motif/évolution : Supersedes original fixed maximum of level 3.
- **GR-012 — ACTIVE — human+prompt** : Perform an initial general documentary search before constructing the first graph.
- **GR-013 — ACTIVE — human+prompt** : Perform independent omission passes covering public debate and specialized literature.
- **GR-014 — ACTIVE — human+prompt** : Perform independent omission passes across relevant disciplinary families.
- **GR-015 — ACTIVE — human+prompt** : Perform an omission pass focused on actors, implementation and practical effects.
- **GR-016 — ACTIVE — human+prompt** : Perform an omission pass for intermediate positions, alternatives and conditional variants.
- **GR-017 — ACTIVE — human+prompt** : For every main argument and every crucial developed node, search explicitly for the strongest missing objection or counter-objection.
- **GR-018 — ACTIVE — human+prompt** : Perform a free blind-spot pass from a different research question rather than rereading the same draft.
- **GR-019 — ACTIVE — human+prompt** : Stop research after a documented saturation pass when new searches mostly produce duplicates, examples or marginal variants.
- **GR-020 — ACTIVE — human+automatic records** : Consolidate semantic duplicates, choose the best hierarchy, and record every fusion, deletion and reuse decision.
- **GR-021 — ACTIVE — human** : Apply a deletion test: retain a node only when removing it would erase a significant distinct reasoning step.
- **GR-022 — ACTIVE — automatic** : Generate graph Markdown only from the registry/occurrences; never edit the projection independently.
- **GR-023 — ACTIVE — automatic** : In the graph rendering, reused pages are linked with MediaWiki brackets at every occurrence; unique pages are not bracketed.
- **GR-024 — ACTIVE — automatic** : Graph outputs include registry, graph JSON, graph Markdown, consolidation log, research sources and validation report.
- **GR-025 — ACTIVE — human+prompt** : The consolidation log records concise reasons such as duplicate, example, case-specific, wrong level, same scope or insufficient autonomy.
- **GR-026 — ACTIVE — human+prompt** : The research source file identifies author/institution, title, link, date when available and the argumentative families supported, without duplicating references.
- **GR-027 — ACTIVE — automatic+human** : Do not release graph deliverables until automated blocking validations pass and a separate semantic review covers quasi-duplicates, logic, balance and title autonomy.
- **GR-028 — ACTIVE — human+prompt** : After passes A–F, repeat complete saturation passes until two consecutive passes find no important distinct argument; perform at most six additional saturation passes and report the limit if important additions still occur.
- **GR-029 — ACTIVE — human+prompt** : After pruning, conduct a final independent omission pass over main arguments, strongest reasons and objections, intermediate positions, alternatives, affected actors, implementation, indirect and long-term effects; any important addition restarts consolidation on the affected branch.
- **GR-030 — ACTIVE — human+prompt** : As a non-binding coverage guide, aim normally for roughly six to ten main arguments per camp; never create or keep nodes merely to reach a quota.
- **GR-031 — ACTIVE — human+prompt** : As a non-binding guide, a main argument normally receives two to five direct justifications and two to five direct objections; fewer are preferable when further children would be weak, redundant or remote.
- **GR-032 — ACTIVE — human+prompt** : A developed crucial node normally receives two to four strong justifications and objections without mechanical quotas; deeper levels 4 or 5 are used only where the discussion is central and requires them.
- **GR-033 — ACTIVE — human+prompt** : Initial framing explicitly maps the evaluated proposition, important variants, affected actors, institutions, professionals, beneficiaries, third parties, indirect effects, relevant disciplines and material scope ambiguities.
- **GR-034 — ACTIVE — human+prompt** : A candidate node is autonomous only when it is a complete contestable proposition, adds a distinct premise, mechanism, objection or consequence, matters to serious debate, can sustain a substantive page and would leave a real gap if removed; examples and narrow administrative details remain examples.
- **GR-035 — ACTIVE — human+heuristic** : Graph titles state the central reason directly, avoid metadiscourse and simple themes, and do not mechanically repeat the overall debate conclusion in every node.
- **GR-036 — ACTIVE — human** : Logical review distinguishes principle from application, rule from example, cause from consequence, empirical finding from normative conclusion, legal from moral reasoning, economic from social reasoning, existence from feasibility of an alternative, and transition possibility from transition cost.
- **GR-037 — ACTIVE — human+prompt** : Strong-objection passes test premises, mechanisms, logical links, scope, proportionality, empirical validity, legal validity, practical implementation and less costly or less restrictive alternatives whenever relevant.
- **GR-038 — ACTIVE — human+prompt** : Graph research prioritizes official legal and institutional sources, scientific and academic publications, directly relevant professional or association reports, authoritative books and quality press for documented public positions, while representing several serious positions and verifying current facts.
- **GR-039 — ACTIVE — automatic** : The ASCII rendering contains only the debate title, camp labels, argument titles, Justifications/Objections labels and reuse brackets; it contains no IDs, level numbers, notes, summaries, references, categories, keywords, JSON or working comments.
- **GR-040 — ACTIVE — automatic+human** : The graph Markdown contains, in order, the title, complete ASCII graph, recap table, reused-page table, concise pass note, final-control note and residual scope/research limits.
- **GR-041 — ACTIVE — automatic** : The recap table reports main pro/con arguments, justifications and objections by depth, distinct pages, total occurrences, reused pages, additional reuses, developed pages and pages used only as secondary links; every value is recalculated from the registry.
- **GR-042 — ACTIVE — automatic** : The reused-page table reports canonical page, occurrence count, full-development location and other use locations, exactly matching occurrences and the unique primary occurrence.
- **GR-043 — ACTIVE — automatic** : The validation report lists executed checks, numerical results, corrected anomalies and each final result, and uses VALIDATION GLOBALE : RÉUSSIE only when no blocking error remains.
- **GR-044 — ACTIVE — automatic+human** : The consolidation log records completed passes and added, removed, merged, renamed, moved, reused and converted-to-example items, stop condition and residual limits, using concise editorial reasons rather than private reasoning.
- **GR-045 — ACTIVE — human+automatic heuristics** : Research sources record title, author or institution, date when available, link, verification role and pro/con/neutral status without forcing a position or duplicating documentary records.
- **GR-046 — ACTIVE — automatic** : The rendered tree has no orphan line, uses the correct box-drawing connectors and visually attaches every item to its actual parent.
- **GR-047 — ACTIVE — automatic+human** : A title may not reappear within its own descendant subgraph, and a node may not combine independent reasonings merely for convenience.

## 8. Page Débat française

- **DFR-001 — ACTIVE — human+automatic heuristics** : sujet is the simplest general theme and is not the full interrogative debate proposition.
- **DFR-002 — ACTIVE — human+heuristic** : sujet-développé expresses the exact object, integrates naturally in a sentence, and uses the common acronym when one exists.
- **DFR-003 — ACTIVE — human** : The introduction gives a non-specialist reader the information needed to understand the debate before reading the arguments; it is encyclopedic, neutral, precise, synthetic and structured according to the subject.
- **DFR-004 — ACTIVE — human+prompt** : The introduction defines the subject and scope, explains the exact meaning of the question, gives relevant historical and current context, supplies necessary background and contains a dedicated stakes subsection. The stakes subsection presents concrete consequences rather than a generic list or a copy of the argument graph.
- **DFR-005 — ACTIVE — human** : The introduction presents established facts, uncertainty, interpretive disagreement and relevant evolution without advocating a camp; every subsection has an identifiable purpose in the reader’s understanding.
- **DFR-006 — ACTIVE — human** : Do not turn the introduction into a detailed pro/con list, a literature-review outline, a mirror of the graph or a topic-specific checklist inherited from another debate.
- **DFR-007 — ACTIVE — automatic+human** : Important factual claims in the introduction receive inline references; generated pages never add <references /> tags.
- **DFR-008 — ACTIVE — human+prompt** : Verify all contemporary legal, political, scientific and statistical information on the generation date.
- **DFR-009 — ACTIVE — human+warning heuristics** : Do not confuse proposals with enacted law, unfinished procedures with completed ones, experiments with generalized policy, associations with causality, forecasts with facts, or recommendations with legal duties.
- **DFR-010 — ACTIVE — external check+human** : Use only verified existing French Wikipedia pages with exact titles, and prefer directly useful specific articles over overly general ones.
- **DFR-011 — ACTIVE — automatic** : The main pro and con lists reproduce all and only primary depth-1 occurrences from the locked registry.
- **DFR-012 — ACTIVE — automatic** : A reused subordinate argument appears in a main list only if it also has a primary depth-1 occurrence in the graph.
- **DFR-013 — ACTIVE — human+prompt** : Search all nine documentary positions/categories; omit a category rather than force a weak or foreign source.
- **DFR-014 — ACTIVE — human+metadata** : Every bibliographic, web and video reference on the French Debate page, including introduction citations, must be genuinely and fully available in French; no foreign-language exception applies to debate pages.
- **DFR-015 — ACTIVE — human+metadata** : An originally foreign resource is acceptable only through a real official French edition, translation, page, dubbing or complete official French subtitles linked directly.
- **DFR-016 — ACTIVE — human** : Automatic subtitles, browser translation, partial/unofficial translations, French summaries or reviews do not make a foreign resource a French source.
- **DFR-017 — ACTIVE — human** : Classify a source as pro or con only when it explicitly supports or opposes the debated proposition or a sufficiently close measure; otherwise classify it as neutral.
- **DFR-018 — ACTIVE — human** : Do not infer support for prohibition from evidence of harm or opposition from evidence of benefit; inspect the source position rather than its title.
- **DFR-019 — ACTIVE — human+automatic heuristics** : Avoid exact and semantic duplication across bibliography, webliography and videography; an editor page or download page does not duplicate the underlying cited publication unless it adds autonomous substantive content.
- **DFR-020 — ACTIVE — external check+human** : Related debates are included only when their page exists or creation is explicitly planned, and the relationship is directly thematic.
- **DFR-021 — ACTIVE — human** : Select only central authorized sections; do not add a section solely for a secondary argument.
- **DFR-022 — ACTIVE — human+automatic heuristics** : A genuinely new Debate normally uses five to eight reusable keywords. A pre-existing Debate preserves its historical count by default; intrinsic keyword-quality rules remain active and traceable corrections are allowed.
- **DFR-023 — ACTIVE — human** : A debate, cross-interview, round table or parliamentary hearing presenting several positions is neutral videography; a pro/con video requires an explicit identifiable position.
- **DFR-024 — ACTIVE — human+automatic heuristics** : Do not duplicate the same video in several documentary positions and prefer a stable official source over an unidentified social repost.
- **DFR-025 — ACTIVE — human+metadata** : For a French translation or edition, use the verified French title, publisher, publication date and direct French link; distinguish correctly article/chapter, containing work, authoring institution and publisher.
- **DFR-026 — ACTIVE — human+heuristic** : Inline introduction references specifically cover laws and bills, judicial decisions, historical dates, statistics, study results, foreign experiences, public policies, institutional statements and legislative-procedure status whenever these claims are material.
- **DFR-027 — ACTIVE — automatic+external check** : Wikipedia title verification includes accents, capitalization, disambiguation parentheses, singular/plural and the exact existing title; inventing or approximating a page title is forbidden.
- **DFR-028 — ACTIVE — automatic+human** : Argument page links use the exact locked canonical title; displayed titles may omit redundant context but remain complete, faithful and intelligible argumentative sentences, never nominal labels and never replacements for the canonical page field.
- **DFR-029 — ACTIVE — human+automatic heuristics** : Bibliography contains books, chapters, scientific or academic articles, reports and other publication-like works; webliography contains autonomous substantive web resources rather than mere catalogue, sales, announcement, download or summary pages for publications already cited.
- **DFR-030 — ACTIVE — human+automatic heuristics** : A bibliographic and a web reference to the same underlying work coexist only when the web page has independent substantial content and that distinct contribution is recorded; otherwise retain the primary publication.
- **DFR-031 — ACTIVE — human+automatic heuristics** : Do not duplicate a cited publication through an editor or bookseller page, release announcement, press article announcing it, press release or news page merely summarizing the same report or study.
- **DFR-032 — ACTIVE — human** : A related debate is not merely a shared theme, an argument or a Wikipedia article; it is a distinct debate page with a direct thematic relationship.
- **DFR-033 — ACTIVE — human+automatic** : If no sufficiently relevant verified French Wikipedia article, documentary source or related debate exists, omit the optional parameter rather than inventing, translating or weakening the criterion.
- **DFR-034 — ACTIVE — automatic+human** : The French Debate Work performs a final structural, introduction-purpose, source, language, classification, duplicate, Wikipedia, graph-link, current-fact, interlanguage and obsolete-parameter checklist before delivery.


- **DFR-036 — ACTIVE — human+automatic ledger** : A bilingual introduction-review ledger records, for every actual subsection, its title, purpose and necessity for understanding the debate.
- **DFR-037 — ACTIVE — human** : A technical or specialized subsection is retained only when its relevance to the debated question is explained explicitly.
- **DFR-038 — ACTIVE — human** : The introduction follows a coherent progression for a reader discovering the subject; titles and opening sentences make each subsection's role clear.
- **DFR-039 — ACTIVE — human+profile** : No universal minimum of five subsections or twenty references applies; any local minimum is justified by the breadth and complexity of the debate.
- **DFR-040 — ACTIVE — automatic+human** : The introduction review confirms that no topic-specific checklist, corpus identifier or pilot-debate constant has been imported into the generic production rules.
- **DFR-041 — ACTIVE — human** : A dedicated « Enjeux du débat » / « Stakes of the debate » subsection is a creation-profile requirement for newly authored introductions when applicable; it is not imposed retroactively on unchanged historical introduction subsections or their English adaptation.

## 9. Page Debate anglaise

- **DEN-001 — ACTIVE — human** : The English Debate page is an autonomous adaptation for English-speaking or international context, not a mechanical translation of the French introduction.
- **DEN-002 — ACTIVE — automatic+human** : It preserves the same main logical debate and primary arguments while adapting legal, political and cultural framing.
- **DEN-003 — ACTIVE — human+metadata** : Use verified English-language references rather than reusing French-only documentary references by default.
- **DEN-004 — ACTIVE — external check+human** : Use only verified existing English Wikipedia pages with exact titles and direct relevance.
- **DEN-005 — ACTIVE — human** : Apply the same epistemic cautions, comprehension functions and neutral classification rules as the French Debate page.
- **DEN-006 — ACTIVE — human+prompt** : During FR→EN editorial translation, treat the English target page as if it did not exist; do not reuse its content, metadata, warnings, progress, references or relations as translation input.
- **DEN-011 — ACTIVE — automatic+human** : Translate the exact source values of avancement/progress and Debate/Argument title and page warnings according to the exhaustive owner-approved FR→EN mapping; never replace a source value with a creation default.
- **DEN-012 — ACTIVE — automatic+human** : If one of these mapped metadata parameters is absent in French, keep the corresponding English parameter absent; an unknown source value requires review rather than approximation.
- **DEN-009 — ACTIVE — external check+human** : Build related-debates only from French débats-connexes whose corresponding English page is verified to exist; omit missing counterparts and never add a relation absent from the French source.
- **DEN-010 — ACTIVE — human+prompt** : Close every translation batch only after a distinct FR→EN verification pass covering metadata mapping, related-debate existence, semantic equivalence, argument polarity, idiomatic English, residual French wikicode and documentary adaptation.

## 10. Pages Argument et résumés

- **ARG-001 — ACTIVE — automatic** : Every distinct active graph node becomes exactly one French page and one English page by the end of the bilingual workflow.
- **ARG-002 — ACTIVE — automatic** : Argument pages reproduce graph justifications, objections and reuses exactly; writing may enrich prose but never add, delete, merge or retype nodes.
- **ARG-003 — ACTIVE — human** : The summary directly develops one reasoning: claim, premises, mechanism, relevance, applications, evidence and necessary limits.
- **ARG-004 — ACTIVE — human+heuristics** : Summaries are complete fluid paragraphs, not outlines or lists, and do not merely restate the title.
- **ARG-005 — ACTIVE — warning+human** : Indicative summary lengths are 100–160 words for simple, 150–250 for intermediate and 200–350 for complex arguments; these are quality guides, not rigid padding targets.
- **ARG-006 — ACTIVE — human** : Use concrete examples, typical situations, mechanisms, important studies, data, historical comparisons, distinctions, practical consequences and methodological limits when they materially improve understanding.
- **ARG-007 — ACTIVE — human** : Hypothetical examples are identified as hypothetical; important precise real cases are verified and referenced.
- **ARG-008 — ACTIVE — human+heuristics** : Do not combine several independent arguments, anticipate every objection at length, repeat the same idea, accumulate unexplained studies or describe the page externally.
- **ARG-009 — ACTIVE — automatic+human** : Reject metadiscursive formulations such as cet argument, l'argument, this argument, cette objection or cette justification.
- **ARG-010 — ACTIVE — human+metrics** : Treat pro and con pages with the same standards of development, evidence and methodological caution.
- **ARG-011 — ACTIVE — human+automatic structure** : The French and English summaries express the same logical node and have comparable depth, but each is idiomatic rather than literal.
- **ARG-012 — ACTIVE — human+metrics** : The English version must not be shorter, more schematic or less documented merely because it is produced second.
- **ARG-013 — ACTIVE — automatic+human** : After each batch, report page count, identifiers, reused pages and material normalization difficulties without placing commentary inside wikicode.
- **ARG-014 — ACTIVE — human+heuristic** : Each Argument page is informative and understandable independently of the graph, while remaining exactly one logical node.
- **ARG-015 — ACTIVE — automatic+human** : A coherent batch preferably contains a main argument, its direct justifications and objections, lower dependent nodes and unproduced reused pages assigned to that owner batch, with dependencies declared rather than duplicated.
- **ARG-016 — ACTIVE — automatic** : Before page writing, extract all distinct node IDs, count occurrences, distinct pages, reuses, main arguments, justifications and objections, and report structural inconsistencies.
- **ARG-017 — ACTIVE — human+heuristic** : Study evidence is used to confirm a mechanism, give an order of magnitude, show group variation, test a hypothesis, reveal a limit or provide a documented example, and its relevance is explained rather than merely cited.
- **ARG-018 — ACTIVE — human+heuristic** : Do not overload Argument pages with redundant references or unexplained study lists; every documentary item supports a statement actually made in that page.
- **ARG-019 — ACTIVE — automatic** : Individual page files and aggregate page records remain clearly separated, syntactically complete and compatible with automated import; no explanatory commentary appears inside wikicode.
- **ARG-020 — ACTIVE — automatic** : The independent registry/JSON source stores IDs and relations separately from wikicode so pages and aggregates can be regenerated deterministically.
- **ARG-021 — ACTIVE — automatic+human** : French and English page sets undergo structural, title, wikicode, linguistic-reference and summary-quality checks, including broken links, self-relations, direct-child duplicates and camp parity.
- **ARG-022 — ACTIVE — automatic+prompt** : Canonical English titles are normalized and locked before French page generation solely to support direct interlanguage links; English page prose and documentation are produced only after complete French validation.

## 11. Références et études

- **REF-001 — ACTIVE — human+prompt** : Argument pages use a domain-appropriate documentary profile: bibliography is generally preferred, while source hierarchy follows the nature of the reasoning and webliography or videography must add substantive value.
- **REF-002 — ACTIVE — human** : Prioritize the strongest sources appropriate to the field: scientific studies and syntheses, official legal materials and doctrine, primary historical sources and historiography, primary philosophical works and scholarship, official data and institutional reports, or equivalent authoritative material.
- **REF-003 — ACTIVE — human+metadata** : When an original study is accessible, prefer it, its DOI, journal page or official institutional report over a press article or secondary metadata page.
- **REF-004 — ACTIVE — human+metadata** : Every source is real, verified, directly relevant, described without exaggeration and linked to the exact claim for which it is used.
- **REF-005 — ACTIVE — human+metadata** : Never invent authors, titles, publication details, methods, samples, statistics, conclusions, institutions, translations or URLs.
- **REF-006 — ACTIVE — human+warning heuristics** : Do not present statistical association as demonstrated causality.
- **REF-007 — ACTIVE — human** : Mention important limits of observational, cross-sectional, self-reported, small, old, country/platform-specific, contested or poorly generalizable studies.
- **REF-008 — ACTIVE — automatic+human** : A study mentioned in a summary must appear in that page's documentary parameters; documentary lists are not general reading lists.
- **REF-009 — ACTIVE — human+metadata** : Verify at least authors, exact title, container/work, year, volume/issue, location, publisher/institution, place, link and correspondence with the claim whenever applicable.
- **REF-010 — ACTIVE — human+automatic date checks** : Preserve original titles, author names and official proper names; adapt variable dates, places and ordinary editorial wording to the page language.
- **REF-011 — ACTIVE — human+metadata** : French Argument pages prefer a verified French edition or equivalent whenever one exists. A foreign-language original is allowed only when no relevant official French equivalent exists or when the foreign source is itself analysed; titles are never translated artificially.
- **REF-012 — ACTIVE — automatic** : Inline reference calls in French prose appear before final punctuation; English prose uses the selected English convention after punctuation.
- **REF-013 — ACTIVE — automatic** : French numéro and English issue contain digits only; chapters, pages, ranges and other positions use localisation/location.
- **REF-014 — ACTIVE — human+metadata** : Bibliographic fields are used semantically: article for an article/chapter/contribution, ouvrage/work for the journal/book/report/container, édition/publisher for publisher and lieu/place for publication place.
- **REF-015 — ACTIVE — automatic+external check** : HTTP/HTTPS links must be verified and point to the represented resource or authorized version.
- **REF-016 — ACTIVE — human+automatic heuristics** : Exact and semantic documentary duplicates are forbidden across categories and pages where they add no distinct value.
- **REF-017 — ACTIVE — human+metadata** : For every video, search the source page, description, credits, speakers and original publication for an author or editorially responsible entity.
- **REF-018 — ACTIVE — human+metadata** : Do not use a hosting platform or unofficial reposting account as author by default; prefer the official original source.
- **REF-019 — ACTIVE — automatic+human** : When no responsible author/entity can be identified after real verification, omit the MediaWiki author field rather than inventing one and record the checks in the source registry.
- **REF-020 — ACTIVE — automatic** : Video models never receive site or date parameters that do not exist in their official structure.
- **REF-021 — ACTIVE — human+heuristic** : French descriptive dates use natural French order and month names; English descriptive dates use natural English forms, while exact source titles remain unchanged.
- **REF-022 — ACTIVE — human+heuristic** : Use the established French or English form of a publication place when one exists, and do not artificially translate place names normally retained unchanged.
- **REF-023 — ACTIVE — human+external check** : For translated or language-specific editions, link directly to the represented edition and use that edition’s verified title, publisher or broadcaster and date rather than metadata from another language version.
- **REF-024 — ACTIVE — human+external check** : A bilingual resource counts for a language only when the complete relevant content is actually available in that language; an abstract, partial excerpt or review is insufficient.
- **REF-025 — ACTIVE — human+external check** : When no individual video author is identifiable, use a verified media outlet, programme, institution or official editorial channel only if it is genuinely responsible for the content.
- **REF-026 — ACTIVE — human+external check** : A missing video author remains exceptional and is accepted only after checking the page, description, credits, speakers and original source; the registry records those checks.

## 12. Rubriques et mots-clés

**Règle active de reprise des pages existantes.** Les contraintes de forme propres à la génération ne sont pas appliquées rétroactivement. Un `titre-affiché` déjà présent sur le wiki est conservé par défaut même s’il n’est pas propositionnel ; seules les fautes et anomalies flagrantes justifient normalement sa modification. Les quotas de mots-clés ne justifient aucune suppression historique, mais les règles intrinsèques de qualité (forme canonique, longueur, atomicité, vocabulaire) restent applicables : un terme historique réellement mauvais peut être corrigé, remplacé ou décomposé avec justification. Les rubriques historiques sont conservées autant que possible ; un delta de classification reste permis lorsqu’il corrige un défaut réel et est explicitement motivé.


- **CAT-001 — ACTIVE — automatic** : Use only the 18 authorized French rubriques and their exact official English correspondences.
- **CAT-002 — ACTIVE — automatic+human** : Argument pages normally use one to three genuinely relevant categories, exceptionally four.
- **CAT-003 — ACTIVE — human+heuristics** : Argument keywords are two to four simple thematic navigation concepts reused across several pages; proposition-specific details, unique phrases and redundant synonyms are forbidden.
- **CAT-004 — ACTIVE — human** : Keep established compound concepts when they function as recognized terms; otherwise split over-specific phrases into reusable concepts.
- **CAT-005 — ACTIVE — human** : English keywords are idiomatic conceptual equivalents preserving exactly the French decreasing-relevance order.
- **CAT-006 — ACTIVE — automatic** : French and English canonical/displayed titles use straight ASCII double quotes; typographic or angle quotation marks are forbidden in page names.

## 13. Bilingue et interlangue

- **BI-001 — ACTIVE — automatic** : French and English share identical active identifiers, edges, reuses and logical primary occurrences.
- **BI-002 — ACTIVE — automatic+human** : Different language pages may use different documentary sources when appropriate, while common sources retain identity in the source registry.
- **BI-003 — ACTIVE — automatic** : Only French pages contain interlanguage parameters; English pages never do.
- **BI-004 — ACTIVE — automatic** : French interlanguage targets come exclusively from canonical English titles locked before French page generation, never displayed titles.
- **BI-005 — ACTIVE — automatic** : Interlanguage links are present in initial French canonical files, even when English pages are created later.
- **BI-006 — ACTIVE — automatic** : The current workflow uses no interlanguage staging: canonical French files contain the links when the English translation is ready. Legacy staging remains historical format compatibility only.
- **BI-007 — ACTIVE — automatic** : Changing an English canonical title through migration updates the English page, all English links and all French interlanguage targets.
- **BI-008 — ACTIVE — automatic** : A pure interlanguage addition preserves all other content and does not restore obsolete page creation dates.

## 14. Lots, fichiers et transmissions

- **FIL-001 — ACTIVE — automatic** : One page equals one individual source file; aggregates are generated from individual files and never edited manually.
- **FIL-002 — ACTIVE — automatic** : File names use stable identifiers rather than textual titles.
- **FIL-003 — ACTIVE — human+automatic warning** : A coherent batch normally contains 10–25 distinct pages and follows a main argument/subgraph when possible.
- **FIL-004 — ACTIVE — automatic** : Each page has exactly one owner batch per language; other batches may depend on it but may not regenerate it.
- **FIL-005 — ACTIVE — automatic+human** : Batch reports state generated page count, identifiers, reuses, dependencies and normalization difficulties.
- **FIL-006 — ACTIVE — automatic** : Every Work handoff records debate ID, versions, required state, files, SHA-256, locks, allowed outputs and prior validations.
- **FIL-007 — ACTIVE — automatic** : A receiving Work rejects mismatched IDs, versions, status or hashes instead of guessing the newest file.
- **FIL-008 — ACTIVE — automatic** : Aggregate separators must contain exact canonical titles and the aggregate must be deterministic.
- **FIL-009 — ACTIVE — automatic** : Do not create cryptographic self-reference: archive SHA-256 belongs in an external receipt, not inside the archive it hashes.
- **FIL-010 — ACTIVE — automatic** : The mandatory graph deliverables are graph/graphe_argumentatif.md, graph/graphe_argumentatif.json, graph/validation_report.txt, graph/consolidation_log.json and graph/research_sources.md, plus the master registry and handoffs required by the workflow.
- **FIL-011 — ACTIVE — automatic+prompt** : Graph, page and aggregate outputs contain no ellipses or omitted branches; all mandatory artifacts are complete.
- **FIL-012 — ACTIVE — prompt** : A Work output report lists produced paths, main counts, validation status and material residual limits without duplicating full artifacts in the conversation when files have been created.
- **FIL-013 — ACTIVE — automatic** : Every aggregate page separator uses the exact locked canonical title and every page appears once; the individual files remain authoritative over aggregates.

## 15. Import et pages existantes

- **IMP-001 — ACTIVE — automatic+human** : Check remote title existence before import and classify absent, equivalent existing, collision or manual review.
- **IMP-002 — ACTIVE — automatic** : Never overwrite an existing wiki page by default.
- **IMP-003 — ACTIVE — automatic** : Simulation is mandatory before writing; creation uses create-only semantics.
- **IMP-004 — ACTIVE — automatic** : Compare local and remote content, log differences, record revision IDs and re-read after import.
- **IMP-005 — ACTIVE — automatic** : Resume logic is based on title and content SHA-256, not title alone.
- **IMP-006 — ACTIVE — automatic+human** : Import French Argument pages before the French Debate page, then English Argument pages before the English Debate page; French links are already included in the created pages.
- **IMP-007 — ACTIVE — human policy** : Historical Pywikibot tools remain read-only/non-approved until adapted to the validator, create-only, hashes and new logs.

## 16. Validateur

- **VAL-001 — ACTIVE — automatic** : Combine JSON Schema, semantic graph, batches, bilingual, wikicode, file/hash, workflow and report validation.
- **VAL-002 — ACTIVE — automatic** : Use stable unique diagnostic codes and ERROR/WARNING/INFO severities.
- **VAL-003 — ACTIVE — automatic** : Provide human-readable text and structured JSON output; blocking errors cause a non-zero exit code.
- **VAL-004 — ACTIVE — automatic** : Validation mode never modifies files; recalculation/fix modes are explicit and separate.
- **VAL-005 — ACTIVE — automatic** : Support whole-package and targeted validation with unit and integration tests.
- **VAL-006 — ACTIVE — automatic** : Resolve local JSON Schema references using the modern referencing API rather than deprecated RefResolver architecture.
- **VAL-007 — ACTIVE — automatic+human** : Separate machine-provable constraints, automatic documentary heuristics and editorial judgments requiring human review.
- **VAL-008 — ACTIVE — automatic** : Detect duplicate identifiers/titles, dangling references, cycles, self-relations, occurrence/edge mismatch, depth/branch errors, primary occurrence errors and derived-count errors.
- **VAL-009 — ACTIVE — automatic** : Detect missing/duplicate pages, batch gaps/overlaps, stale inputs, missing files, bad hashes and invalid state transitions/handoffs.
- **VAL-010 — ACTIVE — automatic** : Parse wikicode to detect unknown, forbidden, empty or misordered parameters, malformed templates, wrong fixed values, mixed languages and relation mismatches.
- **VAL-011 — ACTIVE — automatic** : Validate interlanguage timing, uniqueness, direction and canonical target.
- **VAL-012 — ACTIVE — automatic+human** : Validate bilingual structural identity and report editorial asymmetries in development/documentation for human review.
- **VAL-013 — ACTIVE — heuristic+human** : Flag summary skeletons, metadiscourse, unsupported mentioned studies, missing mechanisms and camp imbalance as heuristic or human-review findings rather than pretending full semantic proof.
- **VAL-014 — ACTIVE — automatic** : Do not release any Work stage with unresolved blocking errors; failure still produces a report and blocked handoff.

## 17. Clôture et archivage

- **ARC-001 — ACTIVE — automatic+human** : A debate closes only after French, English, bilingual, interlanguage, import and release validations succeed.
- **ARC-002 — ACTIVE — automatic** : The final package is autonomous outside conversations and contains manifests, registry, graph, pages, reports, patches and logs.
- **ARC-003 — ACTIVE — human checklist** : After verification, move all debate conversations and final artifacts to the archive project and remove debate-specific temporary files from the active project.

## 18. Comportement des futurs prompts Work

- **PRM-001 — ACTIVE — prompt** : When title and scope are sufficiently clear, execute each Work autonomously without requesting intermediate validation or confirmation.
- **PRM-002 — ACTIVE — prompt** : Infer minor missing scope details from the natural reading of the title; report only ambiguities that could materially alter the output.
- **PRM-003 — ACTIVE — prompt** : Do not expose intermediate graph drafts; complete research, enrichment, consolidation, pruning and validation before delivering final graph files.
- **PRM-004 — ACTIVE — prompt+automatic** : Final page-generation outputs contain complete wikicode without ellipses, placeholders or abridged sections.
- **PRM-005 — ACTIVE — prompt** : The final French Debate Work returns only a brief verification statement and the complete MediaWiki page artifact, not an additional page summary.
- **PRM-006 — ACTIVE — prompt+human** : Argument Work makes reasonable editorial decisions but records choices that could change the meaning of a node.
- **PRM-007 — ACTIVE — prompt+human** : Graph research uses Web sources when the subject requires current or external verification and represents several serious positions.
- **PRM-008 — ACTIVE — prompt+human** : Do not continue research indefinitely; stop according to the saturation criterion and disclose residual research limitations.
- **PRM-009 — ACTIVE — prompt** : The graph Work final response states completion, gives the five artifact paths, summarizes main counts, reports global validation and mentions only important residual limits; it does not paste the whole graph when the file exists.
- **PRM-010 — ACTIVE — prompt** : Do not expose private detailed reasoning; logs contain only concise verifiable editorial operations and reasons.
- **PRM-011 — ACTIVE — prompt+audit** : Never claim that a search, pass, source verification or validation was performed unless it was actually executed on the current inputs.
- **PRM-012 — ACTIVE — prompt+human** : Numerical ranges are coverage guides only; never invent nodes, references or prose to satisfy a quota.
- **PRM-013 — ACTIVE — automatic+prompt** : Do not edit derived counts, graph projections or aggregate files manually; update the source registry and regenerate.
- **PRM-014 — ACTIVE — prompt+automatic** : Do not deliver competing graph versions, incomplete branches, placeholders or points of suspension as final artifacts.
- **PRM-015 — ACTIVE — prompt+human** : When a category has no qualifying source, omit it and disclose the absence where operationally useful instead of weakening language, relevance or verification requirements.
- **PRM-016 — ACTIVE — prompt** : For sufficiently clear large graphs, report structural counts and material ambiguities through files/reports rather than interrupting autonomous batch production for unnecessary confirmation.

## 19. Règles remplacées ou modifiées

- **SUP-001 — SUPERSEDED — none** : Retain every empty parameter in generated Debate pages.
  - Motif/évolution : Replaced by omission of optional empty parameters.
- **SUP-002 — SUPERSEDED — none** : Use Débat construit and Généré par IA.
  - Motif/évolution : Replaced by Débat construit and explicit page-type AI warnings.
- **SUP-003 — SUPERSEDED — none** : Limit every graph to level 3 and forbid level 4.
  - Motif/évolution : Replaced by normal target 3 with justified levels 4–5.
- **SUP-004 — MODIFIED — none** : Fix all English titles before French page generation.
  - Motif/évolution : Canonical English titles are now locked after graph validation and before French page generation, while English page content remains deferred until after French validation.
- **SUP-005 — REACTIVATED — automatic** : Insert interlanguage links in initial French page generation.
  - Motif/évolution : Reinstated by norm 1.2.0; staging and a second remote update are no longer used for 1.2.x packages.
- **SUP-006 — SUPERSEDED — none** : Produce French and English Argument pages in a single monolithic Work.
  - Motif/évolution : Replaced by separate sequential French and English Work.
- **SUP-007 — MODIFIED — none** : Require every video author field to be filled regardless of verifiability.
  - Motif/évolution : Systematic search remains mandatory; verified absence is exceptionally represented by omission plus registry note.
- **SUP-008 — SUPERSEDED — documentation** : Use a node model where camp and level are intrinsic fields of each node rather than occurrence properties.
  - Motif/évolution : Replaced by nodes/edges/occurrences DAG model.
- **SUP-009 — SUPERSEDED — documentation** : Generate Argument pages without mandatory AI-warning and creation-date fields.
  - Motif/évolution : Mandatory AI warnings still apply; page creation dates were retired on 2026-11-24.
- **SUP-010 — SUPERSEDED — documentation** : Limit Argument documentary parameters to bibliography only.
  - Motif/évolution : Domain-appropriate documentary profile prefers bibliography but permits web/video sources when substantively necessary.
- **SUP-011 — SUPERSEDED — documentation** : Use the original aggregate-only pages.wiki/pages.json layout as the authoritative storage format.
  - Motif/évolution : Replaced by one individual source file per page plus generated aggregates.
- **SUP-012 — SUPERSEDED — documentation** : Treat date-création or creation-date as the immediate draft-generation date even before validation.
  - Motif/évolution : Refined to the date on which the language-specific page file first becomes valid.
- **SUP-013 — SUPERSEDED — documentation** : Keep warning parameters and nested warnings present even when empty.
  - Motif/évolution : Allowed structurally but not generated; empty optional parameters are omitted.

## 20. Complétude

Le catalogue contient le nombre d’exigences indiqué par le fichier machine actif et son reçu de livraison ; ce nombre est recalculé automatiquement à chaque révision. Les prompts Work définitifs devront citer les identifiants applicables et le validateur devra indiquer pour chaque contrôle automatique ou heuristique quels identifiants il couvre.

Les fichiers historiques inclus dans l'archive exhaustive restent des sources de provenance. Ils ne doivent jamais être lus comme normes concurrentes.

---

# Intégration 1.1.0

Le présent cahier est désormais une provenance incorporée à `WIKIDEBIA_NORME_CONSOLIDEE_1.1.0.md`. Cette norme unique ajoute les règles correctives relatives aux résumés, à `page=`, aux dates web, aux éditions françaises, aux titres affichés, à la classification, à la documentation des pages Débat/Debate, aux dates du 25 juillet 2026, au workflow correctif et au kit W11.
# Intégration 1.1.4

Le présent cahier demeure une source de provenance incorporée à `WIKIDEBIA_NORME_CONSOLIDEE_1.1.4.md`. En cas de contradiction, la norme 1.1.4 et les décisions ultérieures priment.


# Addendum 1.1.5 — historique, remplacé par 1.1.7

La source normative active unique est `WIKIDEBIA_NORME_CONSOLIDEE_1.1.9.md`. Chaque titre affiché et chaque ensemble de rubriques fait l’objet d’une décision page par page ; aucun quota global ne remplace cette revue. Une rubrique ubiquitaire est admise lorsque sa pertinence est justifiée pour chaque nœud. Cette ancienne révision exigeait un reçu de test dans l’espace utilisateur ; cette disposition est remplacée par le test canonique de la page Débat en 1.2.3. Toute disposition antérieure incompatible est historique.


# Addendum intégré 1.1.7 — règle active

Chaque rubrique retenue est justifiée individuellement au moyen d’une structure générique ; aucune rubrique ne reçoit de traitement spécial. Les dates et chemins propres à un corpus sont déclarés par son manifeste et ne sont pas codés dans le moteur de validation. Toute disposition antérieure incompatible est historique.


## 21. Exigences ajoutées par la norme 1.2.0

- **TTL-012 — ACTIVE — automatic+human** : A canonical title is referentially autonomous: every expression needed to identify its subject has an antecedent inside the title itself. Context-dependent demonstratives or pronouns are allowed only in displayed titles whose immediate context makes the referent unambiguous.
- **TTL-013 — ACTIVE — human+automatic heuristics** : A displayed title newly generated by Wikidéb’IA states the argumentative claim as a complete proposition. A historical displayed title and its faithful English translation may remain nominal/contextual; creation form is not imposed retroactively.
- **MW-016 — ACTIVE — automatic** : All French pages, including Débat, use `{{Lien interlangue}}` from their first valid generation.
- **MW-017 — ACTIVE — automatic** : English Debate uses `topic` and `expanded-topic`; `type` is forbidden.
- **DFR-035 — ACTIVE — automatic+human** : French Debate references, including inline introduction calls, are entirely available in French.
- **REF-027 — ACTIVE — automatic+human** : Argument pages use a verified equivalent in the page language whenever one exists; cross-language use is explicitly justified.
- **REF-028 — ACTIVE — human+automatic** : Debate bibliography contains foundational books or broad syntheses rather than narrow argument-level studies.
- **REF-029 — ACTIVE — automatic+human** : Web authors are emitted only after attribution verification; page is omitted when identical to site.
- **MW-018 — ACTIVE — automatic** : Generated pages never contain `<references />` or `<references>` tags.


## 22. Exigences ajoutées par la norme 1.2.1

- **MW-019 — ACTIVE — automatic+human** : In generated French prose, paired em dashes may not delimit a parenthetical aside, apposition or inserted enumeration; parentheses are used instead.
- **TTL-012 — CLARIFIED — automatic+human** : Canonical-title autonomy concerns any referent, not specifically protocols or studies; displayed titles may use contextual reference when their actual placement resolves it unambiguously.


## 23. Exigences ajoutées par la norme 1.2.2

- **VAL-021 — ACTIVE — automatic** : Package SHA-256 manifests are exhaustive and their declared file and test counts equal the delivered artifacts.
- **IMP-014 — ACTIVE — automatic** : Canonical publication begins by creating and verifying the canonical French Debate page from the signed plan; a signed debate-test receipt is reverified remotely before any remaining write, and no user-space test page is created.
- **VAL-022 — ACTIVE — automatic** : Publication configurations for page content run all applicable scopes, including `wikicode` and `editorial`.
- **MW-020 — ACTIVE — automatic** : Active examples and checklists obey direct French interlanguage generation and contain no late-staging instruction.


## 24. Exigence modifiée par la norme 1.2.3

- **IMP-014 — ACTIVE — automatic** : la première écriture distante est la création `createonly` de la page Débat française canonique absente ; son reçu signé est revérifié avant les autres pages. Toute sous-page utilisateur de test est exclue du workflow actif.


## 25. Exigences ajoutées par la norme 1.2.4

- **DFR-036 — ACTIVE — human+automatic ledger** : chaque sous-partie réelle de l'introduction possède un objectif explicite et nécessaire à la compréhension du débat.
- **DFR-037 — ACTIVE — human** : toute sous-partie technique explique son rapport avec la question débattue.
- **DFR-038 — ACTIVE — human** : la progression de l'introduction est compréhensible pour un lecteur non spécialiste.
- **DFR-039 — ACTIVE — human+profile** : aucun minimum universel de cinq sous-parties ou vingt références n'est imposé ; les minima locaux sont justifiés.
- **DFR-040 — ACTIVE — automatic+human** : aucune checklist, constante ou configuration propre à un corpus pilote n'est active dans les composants génériques.
- **DFR-041 — ACTIVE — human** : les enjeux du débat sont explicitement présentés dans l'introduction.
- **VAL-023 — ACTIVE — automatic** : le validateur exige et contrôle le registre bilingue de revue des introductions chaque fois que cette revue est fonctionnellement requise ; la révision normative historique déclarée ne désactive pas ce contrôle.
- **VAL-024 — ACTIVE — audit** : l'auto-audit des composants génériques recherche les identifiants, exemples et constantes propres aux corpus pilotes hors dossiers historiques.
- **PRM-017 — ACTIVE — prompt** : la rédaction de l'introduction part des besoins de compréhension du lecteur et non des branches du graphe ou des familles de sources.
- **FIL-014 — ACTIVE — packaging** : les configurations propres à un débat restent dans son corpus et ne sont pas distribuées dans le kit générique.


## 26. Exigences ajoutées par la norme 1.2.5

- **DFR-042 — ACTIVE — human+automatic** : les appels de référence inline des introductions sont déterminés par les affirmations factuelles à attribuer ; aucun minimum global ou par sous-partie n’est imposé.
- **VAL-025 — ACTIVE — automatic** : le validateur n’exige pas au moins un appel `<ref>` ; il contrôle l’interdiction de `<references />`, l’activation fonctionnelle du contrôle et la cohérence de la revue humaine, indépendamment de la révision normative historique déclarée.

## 27. Exigences ajoutées par la norme 1.2.6

- **CAT-008 — ACTIVE — automatic** : les rubriques françaises et sections anglaises sont triées alphabétiquement dans leur langue ; l’équivalence bilingue compare les ensembles conceptuels et non leur position.
- **MW-021 — ACTIVE — automatic** : `sujet` et `topic` commencent par une majuscule.
- **MW-022 — ACTIVE — human+heuristic** : `sujet-développé` et `expanded-topic` sont non interrogatifs, complètent naturellement les en-têtes et emploient l’acronyme courant déclaré lorsqu’il existe.
- **DFR-043 — ACTIVE — human** : pour les rubriques d’une page Débat/Debate, la précision prime sur l’exhaustivité ; seules les catégories centrales à l’ensemble de la controverse sont retenues.
- **DFR-044 — ACTIVE — human+ledger** : la profondeur documentaire d’une page Débat/Debate est proportionnée à l’abondance de la littérature et la revue examine séparément bibliographie, sitographie et vidéographie sans quota universel.
- **ARG-034 — ACTIVE — human+automatic ledger** : la revue de chaque résumé relève une expression exacte présente dans le texte qui rend sa force ferme, imagée ou légèrement mordante perceptible.
- **VAL-026 — ACTIVE — automatic** : le validateur contrôle l’ordre alphabétique des rubriques/sections et la majuscule initiale de `sujet`/`topic`.
- **VAL-027 — ACTIVE — automatic+human** : le validateur contrôle la forme non interrogative des sujets complets, les attestations de précision documentaire et l’ancrage réel de la force expressive dans chaque résumé.

## 28. Correctif de cohérence 1.2.7

- tous les alias de provenance du catalogue résolvent vers des fichiers livrés ;
- les anciens chemins vers la norme 1.1.9 pointent vers `01_normes/history/` ;
- les exigences du validateur et du kit renvoient aux documents actifs qui les codifient ;
- la provenance non distribuée séparément est décrite sans prétendre conserver des fichiers absents ;
- aucune exigence éditoriale 1.2.6 n’est modifiée.


## 29. Correctif de cohérence 1.2.8

- toutes les étiquettes utilisées par `requirements[].sources` sont déclarées dans `source_aliases` ;
- chaque alias et chaque `normative_files` pointe vers un fichier livré ;
- les exemples actifs déclarent la révision courante et respectent la langue de leur entrée ;
- les conditions de schéma éditoriales actives s’appliquent cumulativement ; les versions historiques ne servent qu’à la compatibilité de lecture et aux migrations ;
- aucune exigence éditoriale nouvelle n’est ajoutée.


## 30. Correctif références et publication 1.2.9

- **REF-030 — ACTIVE — automatic** : Complete documentary dates are written in natural language in the page language; ISO machine dates are forbidden.
- **MW-023 — ACTIVE — automatic** : les appels inline des introductions sont rédigés directement dans `<ref>…</ref>` en français comme en anglais ; aucun modèle MediaWiki n’est admis dans le corps d’une note développée.
- **DFR-045 — ACTIVE — automatic+human** : les paramètres documentaires de la page Débat ou Debate sont remplis selon la pertinence réelle des sources, sans quota par paramètre. Une catégorie peut contenir une seule référence ; si aucune source pertinente n’est retenue, le paramètre est entièrement omis. Une même référence ne figure jamais dans plusieurs orientations ; une source développant substantiellement les deux positions est classée uniquement dans la documentation neutre.
- **MW-024 — ACTIVE — human+heuristic** : l’acronyme courant, s’il existe, est déclaré et employé dans `sujet-développé` ou `expanded-topic`.
- **PUB-021 — ACTIVE — automatic** : une publication sélectionnant uniquement les pages françaises n’exige pas les pages anglaises dans le manifeste lorsque leurs titres verrouillés sont présents dans le registre maître.


## Décision corrective 1.2.11 — compaction entre modèles

Le wikicode final est compact aux frontières de modèles adjacents. La séquence `}}` + saut de ligne + `{{` est interdite ; la seule forme admise est `}}{{`. Cette exigence est déterministe, bilingue, applicable aux pages et agrégats, et contrôlée automatiquement avant publication.

## Exigences opérationnelles 1.2.13 — portabilité, publication et sauvegarde

- fournir un lanceur racine `./wikidebia` indépendant du nom et de l’emplacement du dossier ;
- publier par une seule commande un ZIP placé directement dans `incoming/`, sans suffixe imposé, avec sélection automatique s’il est unique ou sélection par nom de fichier s’il y en a plusieurs ;
- traiter le nom du ZIP comme un sélecteur seulement et utiliser `manifest.debate_id` comme identité autoritative du corpus ;
- exiger que le fichier `<identifiant>.zip` contienne un manifeste dont `debate_id` vaut exactement `<identifiant>` ;
- proposer les portées `all`, `fr`, `en`, `fr-debate` et `en-debate` ;
- traiter Débat/Debate avant Argument dans chaque langue, sans configuration inverse possible ;
- installer une mise à jour par `./wikidebia update`, avec vérification, tests, sauvegarde horodatée des versions précédentes, remplacement atomique et vidage de `updates/` ;
- versionner dans Git uniquement les sources nécessaires et portables, puis commiter et pousser automatiquement lorsque `origin` est configuré ;
- exclure de Git `private/`, `corpus/`, `archives/`, `updates/`, `incoming/`, `logs/`, `plans/`, `.state/`, `.venv/` et la configuration locale ;
- conserver `user-config.py` et `user-password.cfg` dans `private/pywikibot/` ;
- n’enregistrer aucun chemin absolu de l’installation dans les fichiers persistants.



## Publication des corpus historiques

Les versions normatives et techniques déclarées par un corpus restent une provenance immuable. Le flux intégré de publication accepte une révision antérieure lorsqu’elle est explicitement compatible avec le validateur installé et que la validation courante réussit. Il ne demande jamais de remplacer `normative_versions.validator`, `normative_versions.kit` ou `consolidated_norm` par les versions locales seulement pour franchir le préflight.


## Reprise distante d’un corpus publié — révision 1.2.16

Une reprise compare obligatoirement le dernier état publié signé, l’état distant courant et le nouveau corpus validé. Le kit produit un plan signé comprenant `create`, `skip`, `update`, `move`, `redirect`, `delete`, `manual_review` et `blocked`. Une page absente du nouveau manifeste n’est jamais supprimée sans preuve d’appartenance à la version antérieure du même débat.

Les mises à jour et suppressions vérifient la révision ou l’empreinte attendue et utilisent le contrôle de concurrence MediaWiki. Toute modification humaine ou provenance indéterminée est classée `manual_review`. Les déplacements et fusions sont déclarés explicitement. Les suppressions sont exécutées seulement après vérification du nouveau graphe publié. Les opérations sont idempotentes et donnent lieu à un reçu final et à un nouvel état publié signé.

Le validateur contrôle localement les structures et la cohérence des plans, mais toutes les lectures et écritures MediaWiki restent dans le kit.


## Correctifs de production 1.2.17

- rechercher et rendre au moins un article Wikipédia exact et vérifié dans chaque page Débat/Debate ; un paramètre Wikipédia vide est bloquant ;
- ne jamais rendre `débats-connexes` ni `related-debates` dans le profil générique visé par ce correctif historique ; pour une traduction FR→EN, l’exception active `DEN-009` s’applique et autorise uniquement les débats connexes français dont la page anglaise correspondante existe ;
- convertir les listes JSON d’auteurs en texte MediaWiki (`["Auteur"]` → `Auteur`, plusieurs auteurs séparés par `, `, liste vide → omission) ;
- publier sans invite interactive : le plan signé est confirmé automatiquement par l’orchestrateur après validation, sans supprimer les contrôles d’empreinte et de concurrence.

### Renforcement 1.2.22 — concision des titres affichés

Pour chaque langue, la concision et l’équivalence sémantique d’un titre affiché nouvellement généré sont revues explicitement. La proposition complète, le prédicat explicite et l’intelligibilité autonome sont des exigences de création. Pour un `titre-affiché` préexistant importé du wiki, la revue atteste au contraire sa préservation par défaut et ne le réécrit pas pour satisfaire ces seules exigences formelles ; seules une faute, une corruption, une ambiguïté flagrante ou une autre anomalie manifeste, ou une décision explicite du propriétaire, justifient normalement sa modification.


## Décisions du 2 août 2026 — révision 1.2.24

- Le sujet court est un libellé nominal conventionnel quand un tel concept existe.
- Le complément de sujet commence normalement par une minuscule en français et en anglais.
- Le nettoyage auteur/site/page s’applique aux références des pages Argument et à la vidéographie. Une égalité auteur-site impose une nouvelle vérification d’attribution puis l’omission de l’auteur si aucune responsabilité distincte n’est trouvée.
- La décision historique d’utiliser « Corrections » comme résumé de reprise par défaut est remplacée par la décision du 12 août 2026 : chaque mutation d’un corpus validé reçoit un résumé MediaWiki individualisé décrivant la modification réelle.
- Une archive de livraison unique contient directement les trois composants et reste installable par les gestionnaires antérieurs.


## Ajout 1.2.24 — modèles de définition Wikipédia au survol

- **ARG-035 — ACTIVE — human+automatic syntax** : les résumés expliquent les notions spécialisées par une définition intégrée ou par le modèle Wikipédia localisé lorsque son premier paragraphe suffit.
- **DFR-047 — ACTIVE — human+automatic syntax** : les introductions françaises utilisent `{{Lien Wikipédia}}` avec `article` et, seulement si nécessaire, `texte-affiché`.
- **DEN-008 — ACTIVE — human+automatic syntax** : les introductions anglaises utilisent `{{Wikipedia link}}` avec `article` et, seulement si nécessaire, `displayed-text`.
- **MW-027 — ACTIVE — automatic** : les noms, paramètres, langues, emplacements et interdictions dans les notes sont contrôlés.
- **PRM-018 — ACTIVE — prompt+human** : la première occurrence utile est liée sans surliaison et sans substitution aux explications centrales.
- **VAL-032 — ACTIVE — automatic+human ledger** : le validateur contrôle la syntaxe et les attestations de revue pour tout corpus traité par les composants courants.

## Décision du 2 août 2026 — révision 1.2.25

La reprise distante ne peut annoncer un succès lorsque des opérations `manual_review` subsistent ou lorsqu’aucune opération exécutable n’a été appliquée. Le dry-run est localement non destructif, les archives sont isolées en staging et la sélection d’une archive est explicite. Les bundles génériques ne contiennent pas de corpus de débat.

## Décision corrective du 2 août 2026 — révision 1.2.26

La reprise sans changement renouvelle l’état publié uniquement après une attestation distante complète et signée, sans édition du wiki. Les archives sont toujours sélectionnées explicitement, les zones de staging sont nettoyées et les portées partielles conservent les preuves nécessaires aux opérations différées, notamment les suppressions.


- **REF-034 — ACTIVE — automatic+human** : An Argument-page reference is selected because it develops or supports that argument; also discussing objections is permitted and never a removal criterion once argument development is verified.

## Exigence active 1.2.34 — publication française avant traduction

Un corpus déclarant `translation_status.en=deferred` est publiable avec une portée française sans titre ni page anglaise et sans lien interlangue. La portée anglaise est bloquée. La dérogation cesse dès que l'anglais est déclaré `ready` ou `published`, ou qu'une page anglaise est inscrite au manifeste. Aucun titre ou lien provisoire n'est généré.

## Ponctuation des notes de référence (1.2.44)

Une simple notice documentaire placée dans `<ref>…</ref>` ne se termine pas par un point avant `</ref>`. Le point de la phrase principale vient après l’appel de note. Un point terminal interne est réservé à une phrase explicative complète et doit être attesté dans la revue par l’empreinte du corps exact de la note.

## Cohérence locale des liens Wikipédia explicatifs (1.2.45)

Les notions spécialisées de même rang énumérées ou comparées dans un même passage sont revues comme un groupe. Lier une seule notion alors que les notions voisines disposent d’articles pertinents et présentent le même besoin explicatif est interdit sans justification explicite. Le registre `wikipedia_link_groups` consigne la sous-partie, les termes, les articles, la décision et toute exception.



## Inventaire général des notions spécialisées (1.2.46)

La revue ne se limite pas aux séries de notions comparables. Chaque sous-partie est examinée intégralement et reçoit une entrée dans `specialized_term_inventory`. Toute notion susceptible d’arrêter un lecteur est liée, expliquée, rattachée à un traitement antérieur ou déclarée intelligible en contexte avec une justification spécifique. Tous les liens Wikipédia réellement présents sont recensés. Le registre `wikipedia_link_groups` de 1.2.45 est remplacé comme mécanisme actif par cet inventaire général.

## Exigences actives 1.2.58 — identité documentaire et validation multicouche

- **REF-041 — ACTIVE — automatic** : un registre global normalisé sépare l’identité canonique des ressources de leurs usages dans `sources.json`; l’identité privilégie DOI, puis URL canonique, puis empreinte bibliographique déterministe.
- **REF-042 — ACTIVE — automatic+human review** : une même identité DOI/URL ne peut porter des libellés documentaires incompatibles dans une même langue; les variantes interlangues restent distinctes et autorisées.
- **REF-043 — ACTIVE — automatic** : le registre global des ressources est lié par SHA-256 à la version exacte de `sources.json`, déterministe et régénérable.
- **VAL-049 — ACTIVE — automatic** : tout rapport du validateur expose séparément `structural`, `documentary`, `semantic_review` et `fresh_archive`, avec `not_run` lorsqu’une couche n’a pas été exécutée.
- **VAL-050 — ACTIVE — automatic+human review** : le moteur sémantique FR→EN compare les marqueurs de négation, modalité, attribution, quantification, fréquence, nécessité/possibilité, restriction, condition, causalité, conséquence, concession, comparaison, intensité et immédiateté dans les titres canoniques, titres affichés et résumés; ses sorties sont des signaux de revue et non des verdicts automatiques.
- **ARCH-005 — ACTIVE — automatic** : le statut `fresh_archive` n’est scellé qu’après création, empreinte, contrôle, extraction vierge et revalidation de l’archive exacte, dans un reçu externe lié au SHA-256 de l’archive.



## Exigences actives 1.2.66 — équivalence propositionnelle et convergence

- **TRN-020** : `displayed-title` traduit directement `titre-affiché`; il n'est jamais reconstruit depuis le titre canonique anglais.
- **TRN-021** : lorsqu'une proposition est attendue, le titre anglais possède un prédicat principal; un verbe uniquement relatif ne suffit pas.
- **TRN-022 / TRN-025** : la revue des résumés atteste ouverture, conclusion, conditions/exclusivités et prémisses décisives, avec empreintes de champs et preuves concrètes.
- **TRN-023 / TRN-026** : le métadiscours ajouté uniquement en anglais et les glissements sémantiques observés sont des régressions ou signaux différentiels; aucune réécriture automatique n'est permise.
- **TRN-024 / TRN-027** : l'application d'une traduction exige deux passes sémantiques indépendantes propres sur la même empreinte exacte; le reçu est lié jusqu'à la release et l'extraction fraîche.
- **EDT-066 / VAL-054** : les nouvelles entrées de vocabulaire disposent d'un `concept_id` stable et les contrôles multiligne lisent la valeur complète de `summary=`/`quote=`.


## Compatibilité par schémas/capacités

Les versions de producteur sont de la provenance. Les workflows actifs déterminent la compatibilité par identifiant/version de schéma et capacités déclarées ; aucune égalité de version de kit ou de validateur ne sert de feature flag éditorial. Les alias MediaWiki historiques sont normalisés à la frontière d’entrée et les sorties nouvelles utilisent exclusivement les noms canoniques.

- **EDT-073 — ACTIVE — automatic+human** : Lors d’une reprise de pages préexistantes, la revue de contenu préserve par défaut l’introduction et les résumés historiques, y compris l’absence historique de résumé ; une suggestion seule n’est jamais appliquée, et toute modification exige une décision propriétaire explicite, précise et traçable couvrant le champ et la valeur finale.

- **PUB-052 — ACTIVE — automatic** : Le second checkpoint français conserve l’introduction et les résumés historiques sans consentement, mais publie dans ce même checkpoint les deltas historiques explicitement autorisés et scellés pendant `fr_content_review`; aucune troisième publication française n’est créée.

- **VAL-062 — ACTIVE — automatic** : Le verrou français porte état historique, présence, empreinte historique, décision `preserved`/`authorized_change`, empreinte finale et preuve de consentement ; le validateur exige l’identité historique pour `preserved` et l’identité avec la valeur finale autorisée pour `authorized_change`.

- **EDT-074 — ACTIVE — automatic+human** : ChatGPT peut signaler et proposer des corrections sur un texte historique sans les appliquer ; l’autorisation propriétaire ouvre uniquement les champs et deltas explicitement désignés et ne vaut jamais dispense générale des autres contrôles.

- **GOV-016 — ACTIVE — automatic** : Une autorisation de texte historique ne peut pas être fabriquée dans le ZIP de revue : le kit génère localement une preuve liée au paquet exact, au `package_id`, au manifeste, au champ et aux empreintes avant/après seulement après une action explicite du propriétaire.

- **PUB-053 — ACTIVE — automatic** : Une modification historique autorisée avant la clôture de `fr_content_review` est intégrée au changeset et publiée au checkpoint français n°2 avec résumé MediaWiki individualisé ; elle n’ouvre aucune troisième frontière de publication.

- **VAL-063 — ACTIVE — automatic** : Le validateur refuse `authorized_change` sans reçu de workflow valide, refuse un rendu divergent du SHA final autorisé et refuse toute modification de champ historique non couvert par la portée du reçu.

- **TRN-035 — ACTIVE — automatic+human** : La traduction anglaise part du texte français final effectivement autorisé ; un résumé historique préservé est traduit tel quel, un résumé historique autorisé utilise sa version finale, et une absence historique reste absente sauf création française nominativement autorisée.

- **EDT-075 — ACTIVE — automatic+human** : Pour un texte historique protégé, l’historique est la provenance ; la valeur éditoriale effective est l’historique avec `preserved` et la valeur finale explicitement autorisée avec `authorized_change`.

- **VAL-064 — ACTIVE — automatic** : Les contrôles structurels utilisent la valeur finale sélectionnée ; une portée structurée d’introduction doit correspondre exactement au delta, et les règles de création ne s’appliquent qu’aux portions ajoutées ou substantiellement réécrites.

- **PUB-054 — ACTIVE — automatic** : Le checkpoint français n°2 publie la valeur finale historique autorisée et son delta individualisé, sans troisième frontière de publication et sans modifier les portions historiques hors portée.

## Addendum 1.2.90 — titres français sans ligatures

Pour les titres **français** (nom de page Débat ou Argument, titre affiché du registre et libellé de chaque occurrence relationnelle), les ligatures doivent être dissociées en lettres accessibles sur un clavier ordinaire : `œ → oe`, `Œ → OE`, `æ → ae`, `Æ → AE`, `ﬀ → ff`, `ﬁ → fi`, `ﬂ → fl`, `ﬃ → ffi`, `ﬄ → ffl`, `ﬅ → st`, `ﬆ → st`. Les accents français et les autres caractères ne sont pas translittérés ; aucune normalisation Unicode de compatibilité générale n'est appliquée. Cette règle ne s'étend ni aux citations, ni aux titres bibliographiques, ni aux textes historiques hors des champs de titre.

Cette correction orthographique est une exception obligatoire à la préservation des titres historiques. La revue explicite les changements du registre ; chaque libellé contextuel conserve sa formulation et son occurrence, avec la seule substitution des ligatures au premier checkpoint français. La provenance importée reste intacte ; les renommages et liens suivent le plan signé et les contrôles de collision habituels. Une ligature importée est signalée avant verrouillage, puis bloquante après le verrou des titres ou en validation finale (`WDV-GRA-016`). Les relations rendues sont contrôlées indépendamment. Un titre externe hors périmètre qui nécessite un renommage doit être traité explicitement avant publication ; il n'est jamais renommé par un remplacement global. Le parcours de traduction sans correction française ne peut pas sceller un corpus présentant cette anomalie.
