## Extension 1.2.68 — preuves de forme et de risques

La revue sémantique 1.4 ajoute, lorsque la forme d’un `displayed-title` change, `displayed_title_form_change_reviewed`, `displayed_title_speech_act_preserved` et `displayed_title_form_change_note`. Les risques sémantiques d’un Argument sont accompagnés de `semantic_risk_evidence[]` (`risk`, `source_excerpt`, `target_excerpt`, `note`). La revue Debate possède `debate_field_semantic_risks`, `debate_field_semantic_risk_reviewed`, `debate_field_semantic_risk_note`, `debate_field_semantic_risk_evidence` et un objet `field_sha256` couvrant les quatre champs traduits principaux.

# Schéma du graphe et du registre maître de Wikidéb'IA

- **Version du schéma :** 1.0
- **Révision corrective du paquet :** 1.0.6
- **Version de structure MediaWiki compatible :** 1.0
- **Version de profil de rendu compatible :** 1.0
- **Date de validation de cette version :** 2026-07-23
- **Statut :** source normative
- **Dépendances :**
  - `cahier_des_charges_consolide_wikidebia.md`
  - `requirements_catalog_wikidebia.json`
  - `structures_mediawiki_wikidebia.md`
  - `profils_rendu_wikidebia.md`

## 1. Fonction de ce document

Ce document définit le modèle de données commun à tous les Work de Wikidéb'IA.

Il précise :

- la représentation d'un débat ;
- la distinction entre une page Argument, une relation et une occurrence ;
- le graphe argumentatif structurel ;
- le rendu arborescent du graphe ;
- les titres canoniques et titres affichés français et anglais ;
- les réutilisations d'une même page Argument ;
- les états de validation et de verrouillage ;
- la production des pages par lots ;
- le suivi des fichiers, des empreintes et des imports ;
- les modifications structurelles postérieures au verrouillage ;
- les règles que devront appliquer les futurs schémas JSON et le validateur stable.

Ce document ne contient pas les règles rédactionnelles détaillées des pages. Celles-ci relèvent des profils de rendu et des prompts spécialisés.

---

# 2. Principes directeurs

## 2.1 Une identité logique unique

Chaque raisonnement distinct possède un identifiant stable et correspond à une seule page Argument par langue.

Une même page peut être utilisée à plusieurs endroits du graphe sans être dupliquée.

L'identifiant, et non le titre textuel, constitue la source de vérité pour :

- les relations ;
- les réutilisations ;
- les correspondances bilingues ;
- les lots ;
- les fichiers ;
- les validations ;
- les imports.

La sélection des nœuds maximise la couverture des raisonnements importants, non leur nombre. Un nœud autonome doit apporter une proposition défendable et contestable, une prémisse, un mécanisme, une objection ou une conséquence distincte, et pouvoir recevoir un résumé substantiel. Les exemples, cas marginaux, précisions administratives et reformulations faibles restent dans le journal de consolidation plutôt que de devenir artificiellement des pages.

## 2.2 Séparation entre nœud, relation et occurrence

Le système distingue obligatoirement trois objets.

### Nœud

Un nœud représente un raisonnement logique distinct et la future page Argument correspondante.

Exemple :

```text
A0042 — Une liberté peut être limitée lorsqu'elle cause un tort grave
```

### Relation

Une relation indique qu'un nœud justifie ou objecte à un autre nœud.

Exemple :

```text
A0042 objecte à A0017
```

### Occurrence

Une occurrence représente l'emplacement concret d'un nœud dans le rendu du graphe.

Le même nœud peut avoir plusieurs occurrences :

```text
A0042 apparaît sous A0017
A0042 apparaît aussi sous A0081
```

Cette distinction permet de représenter un véritable graphe logique tout en produisant un arbre ASCII lisible.

## 2.3 Le camp et la profondeur appartiennent aux occurrences

Le `camp` et le `niveau` ne sont pas des propriétés intrinsèques d'un nœud.

Un même argument peut :

- apparaître comme objection dans la branche favorable ;
- apparaître comme justification dans la branche défavorable ;
- apparaître à plusieurs profondeurs ;
- être argument principal à un endroit et argument subordonné à un autre.

Par conséquent :

- aucun champ `camp` ne doit être utilisé comme identité définitive du nœud ;
- aucun champ `level` ne doit être utilisé comme profondeur définitive du nœud ;
- la branche et la profondeur sont enregistrées dans les occurrences ;
- les profondeurs minimale et maximale d'un nœud sont des valeurs dérivées.

## 2.4 Le graphe est un DAG

Le graphe logique final doit être un graphe orienté acyclique.

Il peut contenir :

- plusieurs parents pour un même nœud ;
- plusieurs occurrences d'un même nœud ;
- des réutilisations entre branches.

Il ne peut jamais contenir :

- de cycle ;
- d'autojustification ;
- d'auto-objection ;
- de relation contradictoire en double entre le même parent et le même enfant ;
- de duplication d'un même enfant sous un même parent et une même relation.

## 2.5 Une seule source de vérité

Le fichier maître évolutif est :

```text
data/registre_debat.json
```

Le fichier :

```text
graph/graphe_argumentatif.json
```

est une projection structurelle générée et verrouillée depuis le registre maître.

Après verrouillage :

- les deux fichiers doivent représenter exactement les mêmes nœuds, relations et occurrences ;
- toute correction structurelle est d'abord appliquée au registre maître ;
- le graphe JSON, l'arbre Markdown et les comptages sont ensuite régénérés ;
- aucune correction manuelle isolée du fichier Markdown n'est autorisée.

---

# 3. Arborescence normative minimale d'un paquet de débat

```text
debates/<debate_id>/
├── manifest.json
├── scope.json
├── data/
│   ├── registre_debat.json
│   ├── sources.json
│   ├── lots_fr.json
│   └── lots_en.json
├── graph/
│   ├── graphe_argumentatif.json
│   ├── graphe_argumentatif.md
│   ├── consolidation_log.json
│   ├── research_sources.md
│   └── validation_report.txt
├── output/
│   ├── fr/
│   │   ├── debate/debate.wiki
│   │   ├── arguments/A0001.wiki
│   │   └── aggregates/
│   └── en/
│       ├── debate/debate.wiki
│       ├── arguments/A0001.wiki
│       └── aggregates/
├── reports/
├── handoff/
└── logs/
```

Les fichiers non encore utiles à une étape peuvent être absents, mais leur emplacement futur doit rester stable. Le reçu SHA-256 du ZIP final est externe à cette arborescence. Les agrégats `.wiki` utilisent le séparateur exact `===== PAGE : Titre canonique exact =====`, puis le wikicode de la page à la ligne suivante. Les paquets historiques antérieurs à 1.2.0 peuvent conserver leurs dossiers de patch et de staging comme provenance, mais ces dossiers ne font pas partie du flux actif 1.2.x.

---

# 4. Conventions d'identifiants

## 4.1 Identifiant du débat

Format recommandé :

```text
<slug_ascii_stable>
```

Exemples :

```text
exemple_debat
exemple_debat
exemple_debat_thematique
```

Règles :

- minuscules ASCII ;
- chiffres autorisés ;
- mots séparés par `_` ;
- aucun accent ;
- aucun espace ;
- aucune ponctuation ;
- identifiant immuable après création du paquet.

## 4.2 Identifiants d'objets

| Objet | Format | Exemple |
|---|---|---|
| Nœud Argument | `A` + 4 chiffres au minimum | `A0001` |
| Relation | `E` + 4 chiffres au minimum | `E0001` |
| Occurrence | `O` + 4 chiffres au minimum | `O0001` |
| Lot français | `FR-A-` + 3 chiffres | `FR-A-001` |
| Lot anglais | `EN-A-` + 3 chiffres | `EN-A-001` |
| Validation | `V` + date + séquence | `V20260723-001` |
| Migration | `M` + date + séquence | `M20260723-001` |
| Source documentaire | `S` + 5 chiffres | `S00001` |

Les identifiants supprimés, fusionnés ou retirés ne sont jamais réattribués à un autre objet.

---

# 5. Structure générale du registre maître

Le registre maître suit cette organisation conceptuelle :

```json
{
  "schema": {},
  "debate": {},
  "graph": {
    "lifecycle": {},
    "depth_policy": {},
    "nodes": [],
    "edges": [],
    "occurrences": [],
    "derived_counts": {}
  },
  "batches": [],
  "validations": [],
  "migrations": []
}
```

Tous les champs obligatoires et leurs contraintes sont détaillés ci-dessous.

---

# 6. Objet `schema`

Exemple :

```json
{
  "schema": {
    "registry_version": "1.0",
    "graph_version": "1.0",
    "mediawiki_structure_version": "1.0",
    "render_profile_version": "1.0",
    "validator_version": "1.0.0"
  }
}
```

Règles :

- les quatre premières versions sont obligatoires ;
- `validator_version` devient obligatoire dès qu'une validation automatisée a été exécutée ;
- une évolution incompatible exige une migration explicite ;
- aucune version ne peut être modifiée silencieusement après validation d'un paquet.

---

# 7. Objet `debate`

## 7.1 Structure

```json
{
  "debate": {
    "id": "exemple_debat",
    "scope": {
      "proposition_fr": "Faut-il adopter la mesure X ?",
      "scope_summary_fr": "Le débat porte sur l’objet défini et sur ses conditions d’application.",
      "jurisdiction": "France",
      "timeframe": "contemporain",
      "included_topics": [],
      "excluded_topics": [],
      "residual_ambiguities": []
    },
    "labels": {
      "fr": {
        "pro": "Arguments pour l'adoption",
        "con": "Arguments contre l'adoption"
      },
      "en": {
        "pro": null,
        "con": null
      }
    },
    "pages": {
      "fr": {},
      "en": {}
    }
  }
}
```

## 7.2 Champs obligatoires

- `id`
- `scope.proposition_fr`
- `scope.scope_summary_fr`
- `scope.included_topics`
- `scope.excluded_topics`
- `scope.residual_ambiguities`
- `labels.fr.pro`
- `labels.fr.con`
- `pages.fr`
- `pages.en`

`jurisdiction` et `timeframe` sont conditionnels, mais doivent être renseignés lorsqu'ils structurent réellement le débat.

## 7.3 Fiche d'une page Débat

```json
{
  "canonical_title": "Faut-il adopter la mesure X ?",
  "title_status": "locked",
  "generation": {
    "status": "validated",
    "assigned_batch_id": null,
    "creation_date": "2026-07-23",
    "generated_at": "2026-07-23T16:00:00+02:00",
    "validated_at": "2026-07-23T17:00:00+02:00"
  },
  "file": {
    "path": "output/fr/debate/debate.wiki",
    "sha256": "0000000000000000000000000000000000000000000000000000000000000000",
    "status": "validated"
  },
  "wiki": {
    "check_status": "unchecked",
    "checked_at": null,
    "decision": null,
    "remote_title": null,
    "remote_revision_id": null,
    "remote_sha256": null,
    "published_at": null
  },
  "interlanguage": {
    "status": "pending",
    "target_language": "en",
    "target_title": null,
    "inserted_at": null,
    "verified_at": null
  }
}
```

La fiche anglaise utilise la même structure, mais son objet `interlanguage` doit avoir :

```json
{
  "status": "not_applicable"
}
```

---

# 8. Cycle de vie du graphe

## 8.1 États autorisés

```text
draft
validated
locked
migration_required
```

### `draft`

Le graphe peut être enrichi, réorganisé, fusionné et élagué.

### `validated`

Les validations structurelles et sémantiques ont réussi. Une correction motivée reste possible avant le début de la production des pages.

### `locked`

Les titres français, les nœuds, les relations et les occurrences sont figés. Les lots français peuvent être produits.

### `migration_required`

Une modification structurelle a été demandée après verrouillage. Aucun nouveau lot ne doit être validé tant que la migration n'est pas appliquée.

## 8.2 Objet de cycle de vie

```json
{
  "lifecycle": {
    "status": "locked",
    "validated_at": "2026-07-23T15:00:00+02:00",
    "locked_at": "2026-07-23T15:10:00+02:00",
    "locked_by_stage": "graph_finalization",
    "structural_sha256": "0000000000000000000000000000000000000000000000000000000000000000"
  }
}
```

`structural_sha256` est calculé à partir d'un objet contenant uniquement les nœuds actifs, relations actives, occurrences actives et titres français verrouillés. Avant sérialisation, les chaînes sont normalisées en Unicode NFC et les tableaux de nœuds, relations et occurrences sont triés par identifiant. La sérialisation Python normative utilise `json.dumps(..., ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)`, puis un encodage UTF-8 sans BOM.

---

# 9. Politique de profondeur

La profondeur ne possède aucune cible normale et aucun seuil d’avertissement. Elle découle de la structure logique du graphe : chaque occurrence non principale doit viser le meilleur parent immédiat et sa relation doit être explicitement une justification ou une objection de ce parent. Un corpus importé depuis une extraction explicitement bornée conserve toutefois cette limite technique et la frontière qui en résulte, afin de ne jamais confondre les pages coupées avec des feuilles réelles.

## 9.1 Règle générale

- par défaut, aucun niveau maximal n’est retenu ;
- une limite technique explicite peut être conservée avec `limit_policy: bounded` lorsqu’elle provient de l’extraction source ;
- aucune profondeur n’exige à elle seule une justification d’exception ;
- aucune alerte n’est produite parce qu’un seuil numérique serait franchi ;
- la profondeur maximale observée reste calculée à titre descriptif et pour contrôler la cohérence des compteurs ;
- une branche profonde reste soumise aux mêmes contrôles sémantiques occurrence par occurrence que toute autre branche.

## 9.2 Objet `depth_policy`

```json
{
  "depth_policy": {
    "limit_policy": "unbounded",
    "maximum_observed": 7
  }
}
```

Règles :

- `limit_policy` vaut `unbounded` en l’absence de limite d’extraction ;
- `limit_policy: bounded` exige `maximum_edge_depth`, `frontier_node_ids` et `relations_omitted_at_frontier` ;
- les nœuds de frontière appartiennent au graphe et possèdent une occurrence au niveau `maximum_edge_depth + 1` ;
- les relations omises restent présentes dans les pages sources historiques et ne doivent pas être supprimées lors d’un checkpoint ;
- `maximum_observed` est recalculé automatiquement ;
- `maximum_observed` est une mesure descriptive, non une limite ;
- les anciens champs `normal_target`, `declared_maximum` et `exception_reason` restent lisibles lorsqu’ils sont rencontrés dans un artefact historique pour les besoins de compatibilité et de migration ; le générateur courant ne les émet jamais et leur présence n’active aucune règle éditoriale ancienne.

---

# 10. Objet Nœud Argument

## 10.1 Structure complète

```json
{
  "id": "A0001",
  "status": "active",
  "fr": {
    "canonical_title": "La mesure X peut produire un bénéfice collectif important",
    "displayed_title": "Elle peut produire un bénéfice collectif important",
    "title_status": "locked",
    "rubriques": [
      "Politique"
    ],
    "keywords": [
      "mesure X",
      "intérêt général"
    ]
  },
  "en": {
    "canonical_title": null,
    "displayed_title": null,
    "title_status": "unassigned",
    "sections": [],
    "keywords": []
  },
  "pages": {
    "fr": {
      "generation": {
        "status": "assigned",
        "assigned_batch_id": "FR-A-001",
        "creation_date": null,
        "generated_at": null,
        "validated_at": null
      },
      "file": {
        "path": "output/fr/arguments/A0001.wiki",
        "sha256": null,
        "status": "absent"
      },
      "wiki": {
        "check_status": "unchecked",
        "checked_at": null,
        "decision": null,
        "remote_title": null,
        "remote_revision_id": null,
        "remote_sha256": null,
        "published_at": null
      },
      "interlanguage": {
        "status": "pending",
        "target_language": "en",
        "target_title": null,
        "inserted_at": null,
        "verified_at": null
      }
    },
    "en": {
      "generation": {
        "status": "pending",
        "assigned_batch_id": null,
        "creation_date": null,
        "generated_at": null,
        "validated_at": null
      },
      "file": {
        "path": "output/en/arguments/A0001.wiki",
        "sha256": null,
        "status": "absent"
      },
      "wiki": {
        "check_status": "unchecked",
        "checked_at": null,
        "decision": null,
        "remote_title": null,
        "remote_revision_id": null,
        "remote_sha256": null,
        "published_at": null
      },
      "interlanguage": {
        "status": "not_applicable"
      }
    }
  },
  "sources": {
    "fr": {
      "bibliography": [],
      "webliography": [],
      "videography": []
    },
    "en": {
      "bibliography": [],
      "webliography": [],
      "videography": []
    }
  },
  "derived": {
    "occurrence_count": 1,
    "minimum_depth": 1,
    "maximum_depth": 1,
    "is_main_argument_anywhere": true,
    "is_reused": false,
    "primary_occurrence_id": "O0001"
  }
}
```

## 10.2 Champs fondamentaux

### `id`

Identifiant stable et unique.

### `status`

Valeurs autorisées dans le registre actif :

```text
active
retired
```

Un nœud supprimé avant verrouillage est absent du registre final et consigné dans `consolidation_log.json`.

Un nœud retiré après publication peut recevoir `retired`, mais son identifiant reste réservé.

### `fr`

Les titres français sont obligatoires avant verrouillage du graphe.

### `en`

Les titres anglais sont proposés, validés et verrouillés après stabilisation du graphe et avant la génération des pages françaises ; seul le contenu anglais est produit après la validation française.

### `sources`

Les listes contiennent des identifiants de `data/sources.json`, jamais la duplication complète des métadonnées documentaires.

### `derived`

Toutes les valeurs sont recalculées automatiquement. Elles ne doivent jamais être corrigées manuellement.

## 10.3 Statuts des titres

Valeurs françaises :

```text
draft
normalized
validated
locked
```

Valeurs anglaises :

```text
unassigned
draft
validated
locked
```

Un titre `locked` ne peut être modifié qu'au moyen d'une migration.

Le registre de revue individuelle associe à chaque nœud les attestations de forme et d’intelligibilité des titres affichés. `displayed_title_complete_proposition_*` est exigé pour un titre nouvellement généré ; pour un titre historique préexistant et sa traduction fidèle, la provenance `source_page_origin=preexisting` autorise la forme historique nominale/contextuelle sans fausse attestation. L’intelligibilité, l’équivalence et l’absence de nouvelle dégradation restent revues. Le validateur compare les titres revus aux valeurs exactes du registre maître.

## 10.4 Règles des titres

Le validateur vérifie :

- titre canonique non vide ;
- proposition autonome ;
- absence de point final ;
- absence d'apostrophe typographique ;
- unicité après normalisation Unicode, espaces et casse ;
- absence de collision avec un autre identifiant ;
- fidélité du titre affiché ;
- ajout du sujet au titre canonique lorsqu'il est nécessaire hors contexte.

---

# 11. Fiche de page Argument par langue

Exemple français :

```json
{
  "generation": {
    "status": "pending",
    "assigned_batch_id": "FR-A-001",
    "creation_date": null,
    "generated_at": null,
    "validated_at": null
  },
  "file": {
    "path": "output/fr/arguments/A0001.wiki",
    "sha256": null,
    "status": "absent"
  },
  "wiki": {
    "check_status": "unchecked",
    "checked_at": null,
    "decision": null,
    "remote_title": null,
    "remote_revision_id": null,
    "remote_sha256": null,
    "published_at": null
  },
  "interlanguage": {
    "status": "pending",
    "target_language": "en",
    "target_title": null,
    "inserted_at": null,
    "verified_at": null
  }
}
```

## 11.0 Date de création de la page

Pour chaque langue, `generation.creation_date` correspond à la **date de génération validée** du premier fichier conforme de la page. Elle ne correspond pas nécessairement à la date de publication sur le wiki.

Cette valeur devient immuable après validation initiale et ne change pas lors :

- d'une correction ;
- d'un enrichissement ;
- d'une nouvelle tentative d'import ;
- d'un ajout ou d'une vérification du lien interlangue.

La date effective de publication distante est conservée séparément dans `wiki.published_at`.

## 11.1 États de génération

```text
pending
assigned
in_progress
generated
validated
failed
obsolete
```

`obsolete` est utilisé lorsqu'une migration structurelle ou un renommage verrouillé rend le fichier existant caduc.

## 11.2 États de fichier

```text
absent
present
validated
obsolete
```

## 11.3 États de vérification du wiki

```text
unchecked
absent
equivalent_existing
collision
created
manual_review
```

## 11.4 Décisions en cas de titre existant

```text
create
reuse_existing
rename_local
manual_review
none
```

Le workflow ne remplace jamais automatiquement une page existante.

## 11.5 États interlangues français

```text
pending
ready
inserted
verified
blocked
```

Pour toute page anglaise :

```text
not_applicable
```

---

# 12. Objet Relation

## 12.1 Structure

```json
{
  "id": "E0001",
  "parent_node_id": "A0001",
  "child_node_id": "A0002",
  "relation": "justification",
  "order": 1,
  "status": "active",
  "introduced_in_pass": "objections_review"
}
```

## 12.2 Valeurs de `relation`

```text
justification
objection
```

## 12.3 Contraintes

1. `parent_node_id` et `child_node_id` doivent exister.
2. Le parent et l'enfant doivent être différents.
3. Un triplet parent–enfant–relation ne peut apparaître qu'une fois.
4. Le même couple parent–enfant ne peut pas être à la fois justification et objection sans décision éditoriale explicite ; dans le workflow standard, cette situation est bloquante.
5. `order` est unique parmi les enfants d'un même parent et d'une même relation.
6. Une relation active doit avoir exactement une occurrence correspondante sous l'occurrence primaire du parent.
7. Une relation ne contient ni titre, ni camp, ni profondeur.
8. Toute modification après verrouillage passe par une migration.

---

# 13. Objet Occurrence

## 13.1 Structure

```json
{
  "id": "O0002",
  "node_id": "A0002",
  "parent_occurrence_id": "O0001",
  "edge_id": "E0001",
  "branch": "pro",
  "depth": 2,
  "order": 1,
  "occurrence_role": "primary",
  "render_children": true
}
```

## 13.2 Valeurs de `branch`

```text
pro
con
```

## 13.3 Valeurs de `occurrence_role`

```text
primary
secondary
```

Chaque nœud actif possède exactement une occurrence `primary`.

Toutes ses autres occurrences éventuelles sont `secondary`.

## 13.4 Occurrences principales de niveau 1

Une occurrence d'argument principal possède :

```json
{
  "parent_occurrence_id": null,
  "edge_id": null,
  "depth": 1,
  "branch": "pro"
}
```

ou :

```json
{
  "branch": "con"
}
```

## 13.5 Contraintes

1. Chaque occurrence référence un nœud actif.
2. Une occurrence de profondeur supérieure à 1 référence un parent et une relation.
3. La relation doit relier le nœud du parent au nœud de l'enfant.
4. `depth` est recalculé à partir de la chaîne des parents.
5. `branch` est hérité de l'argument principal et vérifié.
6. Une occurrence secondaire est toujours une feuille dans le rendu : `render_children=false`.
7. Les enfants d'un nœud sont rendus uniquement sous son occurrence primaire.
8. Si un nœud n'a aucune relation sortante, son occurrence primaire peut avoir `render_children=false`.
9. Un même nœud ne peut pas apparaître deux fois sous le même parent et la même relation.
10. L'arbre des occurrences doit être acyclique et entièrement rattaché à l'une des deux branches.

---

# 14. Réutilisation d'une page Argument

Un nœud est réutilisé lorsque son nombre d'occurrences est supérieur ou égal à 2.

## 14.1 Règles

1. Toutes les occurrences du nœud sont rendues avec `[[Titre canonique]]` dans l'arbre Markdown.
2. Une seule occurrence est `primary`.
3. Toutes les autres sont `secondary`.
4. Les sous-branches ne sont rendues que sous l'occurrence primaire.
5. Si le nœud n'a aucune relation sortante, l'occurrence primaire reste enregistrée même si elle est visuellement identique aux occurrences secondaires.
6. Le titre canonique est identique dans toutes les occurrences.
7. Une réutilisation ne doit jamais servir à fusionner deux raisonnements seulement proches.

## 14.2 Données dérivées

Pour chaque nœud :

```json
{
  "occurrence_count": 3,
  "is_reused": true,
  "primary_occurrence_id": "O0042",
  "secondary_occurrence_ids": ["O0105", "O0144"]
}
```

Les identifiants secondaires peuvent être calculés et ne sont pas obligatoirement stockés dans la version minimale du registre.

---

# 15. Rendu de l'arbre Markdown

Le fichier `graph/graphe_argumentatif.md` est généré exclusivement depuis les occurrences.

## 15.1 Racine

Le titre français exact du débat constitue la racine.

Sous la racine apparaissent exactement deux branches, selon `debate.labels.fr`.

## 15.2 Titres affichés

Dans l'arbre argumentatif de travail, le rendu utilise normalement le titre canonique français complet.

Le `displayed_title` est destiné aux sous-modèles MediaWiki et peut être utilisé dans des vues secondaires, mais il ne remplace pas l'identité du nœud.

## 15.3 Crochets MediaWiki

- nombre d'occurrences égal à 1 : titre sans crochets ;
- nombre d'occurrences supérieur ou égal à 2 : `[[Titre canonique]]` à toutes les occurrences.

## 15.4 Sous-branches

Les libellés `Justifications` et `Objections` sont générés à partir des relations sortantes actives du nœud rendu sous son occurrence primaire.

Une occurrence secondaire n'affiche aucun enfant.

## 15.5 Interdictions

Le Markdown ne doit jamais être corrigé indépendamment du registre.

Il ne contient pas :

- d'identifiants ;
- de champs techniques ;
- de résumés ;
- de références ;
- de rubriques ;
- de commentaires de construction.

---

# 16. Comptages dérivés

Les comptages sont recalculés automatiquement à partir des occurrences et des relations.

## 16.1 Mesures obligatoires

- arguments principaux favorables ;
- arguments principaux défavorables ;
- justifications par profondeur ;
- objections par profondeur ;
- nœuds Argument distincts ;
- occurrences totales ;
- nœuds réutilisés ;
- réutilisations supplémentaires ;
- nœuds possédant des relations sortantes ;
- nœuds feuilles ;
- profondeur maximale observée.

## 16.2 Définitions

```text
nœuds distincts = nombre de nœuds actifs
occurrences totales = nombre d'occurrences
nœuds réutilisés = nœuds ayant au moins deux occurrences
réutilisations supplémentaires = occurrences totales - nœuds distincts
nœuds développés = nœuds ayant au moins une relation sortante active
nœuds feuilles = nœuds sans relation sortante active
```

Le débat principal et les libellés structurels ne sont jamais comptés comme nœuds Argument.

## 16.3 Exemple d'objet calculé

```json
{
  "derived_counts": {
    "main_pro": 8,
    "main_con": 8,
    "justifications_by_depth": {
      "2": 41,
      "3": 18,
      "4": 3
    },
    "objections_by_depth": {
      "2": 39,
      "3": 17,
      "4": 2
    },
    "distinct_nodes": 112,
    "total_occurrences": 126,
    "reused_nodes": 11,
    "additional_reuses": 14,
    "developed_nodes": 53,
    "leaf_nodes": 59,
    "maximum_depth": 4
  }
}
```

Aucune valeur de ce bloc ne doit être modifiée manuellement.

---

# 17. Données bilingues

## 17.1 Principe

L'identifiant du nœud reste identique dans les deux langues.

Pour chaque `Axxxx`, il existe au terme du workflow :

- un titre canonique français ;
- un titre affiché français ;
- un titre canonique anglais ;
- un titre affiché anglais ;
- les mêmes relations ;
- les mêmes occurrences logiques ;
- une page française ;
- une page anglaise.

## 17.2 Chronologie

1. Les titres français sont normalisés et verrouillés dans le Work du graphe.
2. Si `translation_status.en=deferred`, les titres anglais peuvent rester absents et les pages françaises sont produites sans `interlangue`.
3. La validation française globale peut être réussie et la portée française publiée indépendamment.
4. Lorsque la traduction commence, les titres anglais sont proposés, validés puis verrouillés.
5. Les pages anglaises sont produites et la cohérence bilingue est validée.
6. Après passage à `ready` ou `published`, les liens interlangues français sont ajoutés ou vérifiés par la reprise interlangue explicite, sans modifier les dates de création françaises.
7. Les anciens dossiers de patch/staging interlangue ne font pas partie du flux actif.

## 17.3 Invariants bilingues

Les éléments suivants doivent être identiques par identifiant :

- nombre de pages ;
- relations ;
- réutilisations ;
- occurrence primaire ;
- structure logique ;
- statut actif ou retiré.

Peuvent différer :

- syntaxe des titres ;
- titres affichés ;
- références ;
- exemples ;
- formulation des résumés ;
- contexte juridique ou culturel ;
- date de création ;
- mots-clés idiomatiques.

## 17.4 Sections et rubriques

Les sections anglaises correspondent normalement aux rubriques françaises selon la table officielle.

Toute divergence volontaire doit être :

- rare ;
- motivée ;
- consignée dans une validation bilingue.

---

# 18. Registre des sources

Les métadonnées complètes sont conservées dans :

```text
data/sources.json
```

Le registre maître ne contient que les identifiants des sources associées à chaque page.

## 18.1 Structure conceptuelle d'une source

```json
{
  "id": "S00001",
  "type": "bibliography",
  "language": "fr",
  "metadata": {
    "authors": [
      "Institution ou auteur responsable"
    ],
    "article": null,
    "work": "Ouvrage ou rapport de référence",
    "volume": null,
    "issue": null,
    "location": null,
    "publisher": "Éditeur ou institution",
    "place": "Paris",
    "date": "2026",
    "link": null,
    "page": null,
    "site": null,
    "title": null
  },
  "verification": {
    "status": "verified",
    "verified_at": "2026-07-23T18:00:00+02:00",
    "primary_source": true,
    "notes": []
  },
  "usage": [
    {
      "page_id": "A0001",
      "language": "fr",
      "role": "supports_summary"
    }
  ],
  "deduplication_key": "institution-ou-auteur|ouvrage-ou-rapport|2026"
}
```

Le schéma exécutable détaillé de `sources.json` est fixé dans `source_registry.schema.json`. Une référence bibliographique peut ne pas avoir de lien en ligne, mais elle possède au moins un champ `article` ou `work` non vide ; le champ `title` est réservé notamment aux références vidéographiques. Une référence sitographique ou vidéographique exige une URL HTTP ou HTTPS vérifiée. Toute source enregistrée possède au moins un auteur ou organisme responsable et au moins un usage déclaré. Les champs `issue` destinés à `numéro=` ou `issue=` ne contiennent que des chiffres.

---

# 19. Production par lots

## 19.1 Principe

Chaque page Argument active est assignée à exactement un lot par langue.

Une page réutilisée n'est générée qu'une fois par langue.

## 19.2 Structure d'un lot

```json
{
  "batch_schema_version": "1.0",
  "id": "FR-A-001",
  "debate_id": "exemple",
  "language": "fr",
  "page_type": "argument",
  "strategy": "subtree",
  "root_node_ids": [
    "A0001"
  ],
  "node_ids": [
    "A0001"
  ],
  "dependency_node_ids": [],
  "status": "planned",
  "inputs": {
    "registry_sha256": null,
    "structural_sha256": null,
    "render_profile_version": "1.0",
    "handoff_path": "handoff/FR-A-001_input.json"
  },
  "outputs": {
    "individual_directory": "output/fr/arguments",
    "aggregate_path": "output/fr/aggregates/arguments_batch_001.wiki",
    "aggregate_sha256": null,
    "report_path": "reports/fr_batch_001.txt"
  },
  "work": {
    "work_id": "W03.FR.001",
    "conversation_name": "[EX] 03.FR.001 — Arguments français — lot pilote",
    "started_at": null,
    "completed_at": null
  }
}
```

## 19.3 Stratégies autorisées

```text
subtree
size_balanced
manual_editorial
```

La stratégie recommandée est `subtree`, avec un argument principal et son sous-graphe cohérent.

## 19.4 Taille recommandée

- normalement 10 à 25 pages distinctes ;
- moins si les pages sont très complexes ;
- davantage seulement si les pages sont simples et que la qualité reste stable.

## 19.5 États d'un lot

```text
planned
assigned
in_progress
generated
validated
released
obsolete
failed
```

## 19.6 Contraintes

1. Un nœud actif appartient à un seul lot actif par langue.
2. Tous les identifiants du lot existent dans le registre.
3. Le lot enregistre l'empreinte du registre utilisé.
4. Une modification structurelle postérieure rend le lot `obsolete` si elle l'affecte.
5. Un lot anglais ne peut être planifié qu'après verrouillage des titres anglais.
6. La validation globale refuse une page manquante, dupliquée ou produite dans deux lots.

---

# 20. Validations

## 20.1 Structure d'une validation

```json
{
  "id": "V20260723-001",
  "scope": "graph",
  "language": null,
  "validator_version": "1.0.0",
  "executed_at": "2026-07-23T17:30:00+02:00",
  "input_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
  "result": "passed",
  "blocking_errors": 0,
  "warnings": 2,
  "report_path": "graph/validation_report.txt"
}
```

## 20.2 Portées autorisées

```text
graph
fr_debate
fr_batch
fr_global
en_titles
en_debate
en_batch
en_global
bilingual
interlanguage
release
```

## 20.3 Résultats

```text
passed
passed_with_warnings
failed
```

Aucun état `locked`, `validated` ou `released` ne peut être attribué sans validation correspondante réussie.

---

# 21. Verrouillage et migrations

## 21.1 Règle générale

Après verrouillage, les modifications suivantes exigent une migration :

- ajout ou suppression d'un nœud ;
- fusion de nœuds ;
- modification d'une relation ;
- déplacement d'une occurrence ;
- changement d'occurrence primaire ;
- renommage canonique français ;
- renommage canonique anglais après verrouillage ;
- changement de correspondance bilingue.

Une correction de résumé ou de référence ne constitue pas une migration structurelle si elle ne modifie ni titre ni relation.

## 21.2 Structure d'une migration

```json
{
  "id": "M20260723-001",
  "status": "proposed",
  "reason": "Un argument important a été omis lors de la validation initiale.",
  "requested_at": "2026-07-23T18:00:00+02:00",
  "operations": [
    {
      "type": "add_node",
      "node_id": "A0113"
    },
    {
      "type": "add_edge",
      "edge_id": "E0207"
    }
  ],
  "affected_node_ids": ["A0008", "A0113"],
  "affected_batches": ["FR-A-004"],
  "required_regeneration": {
    "graph": true,
    "fr_pages": ["A0008", "A0113"],
    "en_pages": [],
    "debate_pages": false,
    "interlanguage_patches": false
  }
}
```

## 21.3 États d'une migration

```text
proposed
approved
applied
validated
rejected
```

## 21.4 Opérations autorisées

```text
add_node
retire_node
merge_nodes
rename_title
add_edge
remove_edge
change_relation
move_occurrence
change_primary_occurrence
change_bilingual_mapping
```

Le journal ne contient qu'une justification éditoriale concise et vérifiable. Il ne doit pas exposer de raisonnement privé détaillé.

---

# 22. Gestion des pages déjà existantes sur le wiki

## 22.1 Vérification préalable

La vérification intervient dès la normalisation des titres, puis de nouveau avant import.

## 22.2 Décisions possibles

### Page absente

Le titre peut être conservé et la page créée.

### Page existante et équivalente

Le registre peut décider de la réutiliser après comparaison éditoriale et technique.

### Page existante mais différente

Le workflow choisit :

- un titre local plus précis ;
- ou une revue manuelle.

### Page existante proche mais ambiguë

Aucune fusion automatique. Un rapport de collision est produit.

## 22.3 Interdictions

- aucun écrasement automatique ;
- aucune décision fondée sur le seul titre ;
- aucune réutilisation sans vérifier l'équivalence du raisonnement ;
- aucune perte de l'identifiant local en cas de réutilisation d'une page existante.

---

# 23. Fichiers, empreintes et manifestes

## 23.1 Une page, un fichier

Chaque page possède un fichier individuel :

```text
output/fr/arguments/A0001.wiki
output/en/arguments/A0001.wiki
```

Le nom du fichier repose sur l'identifiant, non sur le titre, afin de rester stable lors des renommages.

## 23.2 Agrégats

Les fichiers agrégés sont générés automatiquement depuis les fichiers individuels.

Ils ne constituent pas la source éditoriale principale.

## 23.3 Empreintes

Chaque fichier validé possède une empreinte SHA-256 calculée sur ses octets exacts. Les producteurs écrivent les fichiers texte en UTF-8 sans BOM, avec des fins de ligne LF et exactement une fin de ligne finale. Le validateur ne transforme jamais silencieusement un fichier avant de vérifier son empreinte.

Une normalisation peut être proposée dans un mode de correction séparé ; elle crée alors un nouveau fichier et une nouvelle empreinte.

La reprise d'un import tient compte au minimum de :

```text
titre canonique + langue + SHA-256 du contenu
```

Un simple titre déjà présent dans un journal ne suffit pas à ignorer un fichier modifié.

## 23.4 Métadonnées minimales d'une page dans le manifeste

```json
{
  "page_manifest_version": "1.0",
  "debate_id": "exemple",
  "page_id": "A0001",
  "page_type": "argument",
  "language": "fr",
  "canonical_title": "La mesure X produirait un bénéfice collectif important",
  "file_path": "output/fr/arguments/A0001.wiki",
  "sha256": null,
  "creation_date": null,
  "batch_id": "FR-A-001",
  "status": "planned",
  "structure_version": "1.0",
  "render_profile_version": "1.0",
  "validation": {
    "status": "pending",
    "report_path": null,
    "validated_at": null
  },
  "wiki": {
    "check_status": "unchecked",
    "checked_at": null,
    "decision": null,
    "remote_title": null,
    "remote_revision_id": null,
    "remote_sha256": null,
    "published_at": null
  }
}
```

---

# 24. Invariants obligatoires du registre

Le validateur applique ces invariants en fonction de l'état du paquet. Un registre `initialized` peut encore avoir un graphe vide ; à partir de `graph_validated`, les invariants de complétude du graphe deviennent bloquants.

Le futur validateur doit traiter les violations applicables à l'état courant comme bloquantes.

## 24.1 Identité

- identifiants uniques ;
- aucun identifiant réattribué ;
- un nœud actif correspond à une page par langue au terme du workflow ;
- aucun titre canonique verrouillé partagé par deux nœuds distincts dans une même langue.

## 24.2 Graphe

- exactement deux branches d'arguments principaux ;
- au moins un argument principal par branche ;
- aucun cycle ;
- aucun nœud orphelin ;
- aucune auto-relation ;
- aucune relation inconnue ;
- aucune relation directe dupliquée ;
- correspondance exacte entre relations et occurrences ;
- profondeur réelle inférieure ou égale à la profondeur déclarée.

## 24.3 Occurrences

- une occurrence primaire par nœud ;
- toute occurrence supplémentaire est secondaire ;
- aucune occurrence secondaire ne possède d'enfants ;
- une occurrence principale de niveau 1 ne possède ni parent ni relation ;
- toute autre occurrence possède un parent et une relation cohérents ;
- tous les chemins aboutissent à une branche `pro` ou `con`.

## 24.4 Titres

- titres français verrouillés avant production française ;
- titres anglais absents avant l'étape prévue, puis verrouillés avant production anglaise ;
- aucun point final ;
- aucune apostrophe typographique ;
- titres affichés fidèles ;
- absence de collision après normalisation.

## 24.5 Lots

- chaque nœud actif assigné exactement une fois par langue ;
- aucune page réutilisée produite deux fois ;
- empreinte d'entrée enregistrée ;
- aucun lot validé à partir d'un registre devenu obsolète.

## 24.6 Fichiers

- un fichier individuel par page déclarée générée ;
- hash exact ;
- titre du séparateur agrégé cohérent avec le registre ;
- aucun fichier orphelin ;
- aucun contenu dupliqué sous deux identifiants.

## 24.7 Bilingue

- mêmes identifiants actifs ;
- mêmes relations ;
- mêmes réutilisations ;
- même occurrence primaire logique ;
- aucune page anglaise avec interlangue ;
- en `deferred`, absence autorisée du titre anglais et du lien interlangue français ;
- en `ready` ou `published`, lien français unique pointant vers le titre canonique anglais exact ;
- tout ajout interlangue après une phase `deferred` passe par la reprise explicite et préserve la date de création française.

---

# 25. Exemple initial syntaxiquement valide

L'exemple suivant correspond à la sortie du Work 00. Son graphe est encore vide, ce qui est autorisé à l'état `initialized`. Il ne peut pas être déclaré `graph_validated` avant l'ajout et la validation des deux branches argumentatives.

```json
{
  "schema": {
    "registry_version": "1.0",
    "graph_version": "1.0",
    "mediawiki_structure_version": "1.0",
    "render_profile_version": "1.0",
    "validator_version": null
  },
  "debate": {
    "id": "exemple_debat",
    "scope": {
      "proposition_fr": "Titre français du débat à remplacer",
      "scope_summary_fr": "Cadrage du débat à compléter lors du Work 00.",
      "jurisdiction": null,
      "timeframe": null,
      "included_topics": [],
      "excluded_topics": [],
      "residual_ambiguities": []
    },
    "labels": {
      "fr": {
        "pro": "Arguments pour",
        "con": "Arguments contre"
      },
      "en": {
        "pro": null,
        "con": null
      }
    },
    "pages": {
      "fr": {
        "canonical_title": "Titre français du débat à remplacer",
        "title_status": "draft",
        "generation": {
          "status": "pending",
          "assigned_batch_id": null,
          "creation_date": null,
          "generated_at": null,
          "validated_at": null
        },
        "file": {
          "path": "output/fr/debate/debate.wiki",
          "sha256": null,
          "status": "absent"
        },
        "wiki": {
          "check_status": "unchecked",
          "checked_at": null,
          "decision": null,
          "remote_title": null,
          "remote_revision_id": null,
          "remote_sha256": null,
          "published_at": null
        },
        "interlanguage": {
          "status": "pending",
          "target_language": "en",
          "target_title": null,
          "inserted_at": null,
          "verified_at": null
        }
      },
      "en": {
        "canonical_title": null,
        "title_status": "unassigned",
        "generation": {
          "status": "pending",
          "assigned_batch_id": null,
          "creation_date": null,
          "generated_at": null,
          "validated_at": null
        },
        "file": {
          "path": "output/en/debate/debate.wiki",
          "sha256": null,
          "status": "absent"
        },
        "wiki": {
          "check_status": "unchecked",
          "checked_at": null,
          "decision": null,
          "remote_title": null,
          "remote_revision_id": null,
          "remote_sha256": null,
          "published_at": null
        },
        "interlanguage": {
          "status": "not_applicable"
        }
      }
    }
  },
  "graph": {
    "lifecycle": {
      "status": "draft",
      "validated_at": null,
      "locked_at": null,
      "locked_by_stage": null,
      "structural_sha256": null
    },
    "depth_policy": {
      "limit_policy": "unbounded",
      "maximum_observed": 0
    },
    "nodes": [],
    "edges": [],
    "occurrences": [],
    "derived_counts": {
      "main_pro": 0,
      "main_con": 0,
      "justifications_by_depth": {},
      "objections_by_depth": {},
      "distinct_nodes": 0,
      "total_occurrences": 0,
      "reused_nodes": 0,
      "additional_reuses": 0,
      "developed_nodes": 0,
      "leaf_nodes": 0,
      "maximum_depth": 0
    }
  },
  "batches": [],
  "validations": [],
  "migrations": []
}
```

---

# 26. Source de vérité par type de donnée

| Donnée | Source de vérité |
|---|---|
| Identifiant du débat | `registre_debat.json` |
| Identifiants des arguments | `registre_debat.json` |
| Titres français verrouillés | `registre_debat.json` |
| Titres anglais verrouillés | `registre_debat.json` |
| Relations | `registre_debat.json` |
| Occurrences et réutilisations | `registre_debat.json` |
| Graphe structurel exporté | `graphe_argumentatif.json`, généré depuis le registre |
| Arbre lisible | `graphe_argumentatif.md`, généré depuis le registre |
| Métadonnées des sources | `sources.json` |
| Contenu exact d'une page | fichier individuel `.wiki` |
| Empreinte et statut d'une page | manifeste et registre |
| État distant du wiki | journal d'import et fiche `wiki` |
| Modifications post-verrouillage | migrations |

En cas de divergence, le fichier dérivé doit être régénéré depuis sa source de vérité. Il ne doit pas devenir une source concurrente.

---

# 27. Évolution du schéma

Toute modification de ce modèle exige :

1. une nouvelle version du schéma ;
2. une mise à jour des schémas JSON exécutables ;
3. une mise à jour du validateur stable ;
4. une mise à jour des prompts concernés ;
5. une procédure de migration pour les paquets existants ;
6. l'absence de modification silencieuse des graphes verrouillés.

Les paquets archivés conservent la version du schéma avec laquelle ils ont été validés.

---

# Addendum intégré 1.1.0 — schémas correctifs

Les énumérations acceptent `corrective_in_progress`, `corrective_blocked`, `corrective_prepublication`, `corrective_editorial_review` et `corrective_full`. `normative_versions` peut déclarer `consolidated_norm`. Le manifeste de paquet et le manifeste de libération peuvent inclure `publication_gate`; le manifeste de libération accepte l’état local `release_ready`.

Les titres affichés demeurent inclus dans l’objet canonique de l’empreinte structurelle. Les handoffs historiques décrivent leurs entrées d’origine et ne sont pas recalculés lors d’une reprise corrective.


# Addendum actif 1.2.0 — registre documentaire et interlangues

Une source enregistre sa langue réelle, un type documentaire, un groupe d’équivalence éventuel et les attestations de langue et d’attribution. Chaque usage enregistre la langue de la page, l’adéquation linguistique et, pour la bibliographie de débat, la portée synthétique et la justification de sélection. Les fiches françaises d’interlangue passent directement à l’état `ready` lorsque le titre anglais est verrouillé ; le fichier canonique contient alors `{{Lien interlangue}}`.


# Addendum intégré 1.2.2 (historique, complété par 1.2.3) — schéma direct et profils locaux

L’arborescence active 1.2.x ne contient ni `patches/interlanguage_fr*` ni `staging/interlanguage/`. Les états historiques restent acceptés seulement pour la validation rétrocompatible. Les compteurs, dates et chemins propres à un débat sont déclarés par son manifeste ou son profil local et ne sont jamais codés dans le schéma générique.

# Addendum intégré 1.2.6 — ordre des classifications bilingues

Les tableaux `fr.rubriques` et `en.sections` sont triés alphabétiquement dans leur langue. Ils représentent le même ensemble conceptuel au moyen de la table officielle, mais ne conservent pas nécessairement le même ordre positionnel après traduction. Les projections, pages et registres de revue reproduisent exactement ces listes triées.

## Addendum intégré 1.2.7 — cohérence de livraison

Le schéma de données ne change pas par rapport à 1.2.6. La révision 1.2.7 corrige uniquement la provenance, les chemins de traçabilité et l’auto-audit des archives.


## Règle de sérialisation 1.2.11

Lors de la sérialisation des listes de sous-modèles dans les fichiers `.wiki` et leurs agrégats, deux sous-modèles consécutifs sont concaténés avec la jonction exacte `}}{{`. Aucun retour à la ligne ni espace n’est inséré entre les deux délimiteurs.


## Reprise distante d’un corpus publié — révision 1.2.16

Une reprise compare obligatoirement le dernier état publié signé, l’état distant courant et le nouveau corpus validé. Le kit produit un plan signé comprenant `create`, `skip`, `update`, `move`, `redirect`, `delete`, `manual_review` et `blocked`. Une page absente du nouveau manifeste n’est jamais supprimée sans preuve d’appartenance à la version antérieure du même débat.

Les mises à jour et suppressions vérifient la révision ou l’empreinte attendue et utilisent le contrôle de concurrence MediaWiki. Toute modification humaine ou provenance indéterminée est classée `manual_review`. Les déplacements et fusions sont déclarés explicitement. Les suppressions sont exécutées seulement après vérification du nouveau graphe publié. Les opérations sont idempotentes et donnent lieu à un reçu final et à un nouvel état publié signé.

Le validateur contrôle localement les structures et la cohérence des plans, mais toutes les lectures et écritures MediaWiki restent dans le kit.


# Addendum 1.2.20 — registre de placement des occurrences

Le manifeste déclare :

```json
{
  "editorial_controls": {
    "graph_placement_review_path": "reports/graph_placement_review.json"
  }
}
```

Le registre de placement contient exactement une entrée par occurrence active. Chaque entrée reproduit `occurrence_id`, `node_id` et `declared_depth`, déclare `placement_status`, `declared_function`, `semantic_target`, `direct_fit=true` et une `rationale` non vide.

Pour une occurrence de niveau 1 :

```json
{
  "occurrence_id": "O00001",
  "node_id": "A0001",
  "declared_depth": 1,
  "placement_status": "approved",
  "declared_function": "main_argument",
  "semantic_target": "debate",
  "direct_fit": true,
  "rationale": "Cette proposition répond directement au débat et organise une famille causale autonome.",
  "main_argument_review": {
    "direct_answer_to_debate": true,
    "autonomous_without_parent": true,
    "organizes_distinct_argument_family": true,
    "more_general_nonduplicate_parent_available": false,
    "principally_supports_or_attacks_specific_argument": false,
    "principally_example_or_specialization": false
  }
}
```

Pour une occurrence de profondeur supérieure à 1, `semantic_target` est l’identifiant de l’occurrence parente, `declared_function` vaut `justification` ou `objection`, et `subordinate_review.parent_is_best_immediate_target` ainsi que `subordinate_review.relation_to_parent_explicit` valent `true`.

Le validateur compare ce registre aux occurrences et relations actives. Une couverture incomplète, un niveau divergent, une cible erronée, une fonction incompatible ou une attestation défavorable bloque la validation éditoriale courante, quelle que soit la révision normative historique déclarée.

### Renforcement 1.2.22 — concision des titres affichés

Pour chaque langue, la concision et l’équivalence sémantique d’un titre affiché nouvellement généré sont revues explicitement. La proposition complète, le prédicat explicite et l’intelligibilité autonome sont des exigences de création. Pour un `titre-affiché` préexistant importé du wiki, la revue atteste au contraire sa préservation par défaut et ne le réécrit pas pour satisfaire ces seules exigences formelles ; seules une faute, une corruption, une ambiguïté flagrante ou une autre anomalie manifeste, ou une décision explicite du propriétaire, justifient normalement sa modification.


## Attestations de revue ajoutées en 1.2.24

Chaque entrée linguistique du registre de revue d’introduction atteste `topic_is_nominal_label`, `conventional_topic_label_used_or_not_applicable`, `topic_label_rationale` et `complete_topic_lowercase_initial_or_justified`. Une justification distincte est fournie lorsqu’un nom propre ou un acronyme impose exceptionnellement une majuscule initiale.

## Capitalisation du vocabulaire contrôlé (1.2.32)

Chaque entrée de mot-clé contient `kind`, `capitalization_policy` et `capitalization_rationale`. Les politiques autorisées sont `lowercase_common`, `canonical_proper_name` et `canonical_acronym`. La justification est obligatoire pour les deux politiques canoniques conservant une majuscule.

## État de traduction anglaise — révision 1.2.34

Le manifeste porte `translation_status.en` avec les valeurs `pending`, `deferred`, `ready` ou `published`. En `deferred`, les champs de titre anglais peuvent rester absents, nuls ou `unassigned`, les fiches interlangues peuvent avoir une cible nulle et aucun lien français n'est rendu. Un titre déclaré `locked`, une page anglaise manifestée ou un statut `ready`/`published` réactive l'obligation d'un titre canonique anglais valide et les contrôles de cohérence correspondants.

## Correctif 1.2.35 — données importées

Le manifeste peut déclarer `editorial_controls.creation_date_policy=per_page_preserved`. Chaque entrée de page porte alors sa date immuable, reproduite à l'identique dans le registre et le wikicode. Le statut anglais différé n'exige pas de métadonnées anglaises avant traduction.

## Registre global des ressources documentaires — schéma 1.0 / norme 1.2.58

Le fichier courant `data/documentary_resources.json` est une projection déterministe de `data/sources.json`. Il ne remplace pas le registre des usages : il sépare l’identité de la ressource de son emploi dans une page. Chaque entrée contient un `id` stable dérivé de l’identité, `identity_type` (`doi`, `url`, `bibliographic_fingerprint`), `identity_key`, `canonical_url`, `doi`, les `source_ids`, langues, libellés, variantes de métadonnées et conflits éventuels. `source_registry_sha256` lie obligatoirement cette projection aux octets exacts de `sources.json`.

La normalisation d’URL minuscule schéma/hôte, supprime le fragment, normalise les slashs, trie les paramètres utiles et élimine les paramètres de suivi usuels. Le DOI est normalisé en minuscules sans préfixe `doi:` ni URL. Une divergence de libellé pour une même identité dans une même langue constitue un conflit documentaire à résoudre; une traduction réelle dans une autre langue n’en constitue pas un.



## Extension 1.2.66 — identité des champs traduits et preuves sémantiques

La filiation des champs est explicite : titre canonique FR→EN canonique, `titre-affiché` FR→`displayed-title` EN, résumé FR→summary EN. La revue enregistre les empreintes des champs et l'empreinte sémantique globale. Le vocabulaire contrôlé peut porter un `concept_id` stable, identique dans les deux langues et unique dans le registre. Le reçu `wikidebia-semantic-convergence-review-1.0` référence l'empreinte exacte de la revue et du contenu sémantique; il ne fait pas partie de l'objet qu'il atteste.


## Addendum 1.2.86 — origine cible et origine éditoriale source

Les artefacts de traduction distinguent `page_origin` de la page anglaise cible et `source_page_origin` de la page française autoritative. Le second est dérivé des verrous français et ne peut être modifié par le paquet de revue. Les contrôles de quota/préférence de création suivent `source_page_origin`; les invariants structurels et contrôles sémantiques restent indépendants de cette provenance.
