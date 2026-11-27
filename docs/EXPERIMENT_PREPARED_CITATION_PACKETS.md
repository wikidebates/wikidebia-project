# Archive du prototype de projection des citations préparées

**Statut : expérience historique, non opérationnelle.** Ce prototype (PR #232)
précède le contrat actif de provenance des citations publiées, intégré à la
norme 1.2.89 et au kit 2.16.48.

Le mécanisme expérimental retirait temporairement des citations des paquets
de traduction, puis réinsérait le texte préparé sans produire toutes les
preuves exigées par le contrat actuel. Il ne doit pas être utilisé pour
préparer une revue, sceller un verrou, traduire ou publier. La sélection
des citations, la vérification des droits, les références, les avertissements
et le contrôle d'unicité restent exclusivement régis par le kit actif.

Le code et les tests d'origine sont conservés intégralement, sous forme de
fichiers texte non exécutables, à titre de provenance et pour une éventuelle
nouvelle expérimentation indépendante :

- [Documentation originale](history/experimental-prepared-citations/README-original.md)
- [Prototype original](history/experimental-prepared-citations/experimental_prepared_citations.py.txt)
- [Tests originaux](history/experimental-prepared-citations/test_experimental_prepared_citations.py.txt)

Référence historique : commit `3e61da9866eea530084972b86cf7dfde76cd0be1`.
Pour les opérations courantes, suivre le
[guide actif du résolveur](../kit/GUIDE_QUOTE_RESOLVER_BRIDGE.md).
L'éventuelle optimisation de taille des paquets devra être réimplémentée
et testée contre les schémas, verrous et preuves actuels ; cette archive
ne constitue ni une validation de cette optimisation ni un nouveau parcours
de production.
