# Audit — titres affichés contextuels et séquence `oe`

Une page Argument peut être citée sous plusieurs titres affichés selon la
relation qui l’emploie. Le titre affiché stocké au niveau du nœud ne suffit donc
pas à reconstruire les pages d’un débat préexistant.

Pour une traduction d’un débat existant, le kit verrouille désormais chaque
`titre-affiché` importé avec l’identifiant de son occurrence ou de son arête. Le
checkpoint français réutilise exactement ce libellé et la revue anglaise exige
sa traduction propre. Les règles de correction des titres affichés continuent
de s’appliquer lors de la génération d’un nouveau débat.

Les consignes de génération, correction et traduction interdisent aussi
d’introduire la ligature `œ` à la place de `oe`. Les textes historiques et les
citations déjà écrits avec une ligature sont conservés tels quels.

## Résultat de l’audit du débat sur les hommes et le combat féministe

L’audit des 125 relations a trouvé cinq libellés historiques qui différaient du
titre affiché global de leur nœud : quatre relations sous `A0007` (`E00043`,
`E00045`, `E00047`, `E00048`) et une sous `A0028` (`E00097`). Les cinq formes
françaises ont été rétablies sur les pages concernées et chacune possède sa
traduction anglaise propre dans le verrou bilingue.

L’audit orthographique a aussi trouvé deux corrections antérieures de titres
canoniques qui avaient transformé `oe` en `œ` (`A0084` et `A0085`). Les titres
canoniques et leurs liens entrants utilisent de nouveau `oe`. Le titre affiché
historique reste inchangé dans chaque cas.

La régression venait de deux contrôles incomplets : le verrou de traduction
protégeait le titre affiché global du nœud, mais pas chaque libellé de relation,
et la revue des titres acceptait une ligature comme correction
orthotypographique. Le rendu, les checkpoints, la revue de traduction et le
validateur consomment maintenant les libellés contextuels ; les diagnostics de
création et les revues françaises bloquent aussi toute introduction de `œ` à la
place d’un `oe` source.
