# Import batch et synchronisation de l’historique

## Commandes

```bash
.venv/bin/python -B extractor.py --batch chemin/copie-activites/
.venv/bin/python -B extractor.py --batch chemin/copie-activites/ --jobs 8
.venv/bin/python -B extractor.py --batch chemin/copie-activites/ --jobs all
.venv/bin/python -B extractor.py --sync-history
```

La synchronisation est une commande indépendante : la lancer avant le premier
batch pour reprendre les anciens exports, et après un arrêt brutal avant de
relancer le batch. Les archives Strava doivent déjà être décompressées dans un
dossier ; seuls les fichiers `.fit` et `.fit.gz`, casse indifférente, sont traités.
Le parcours est récursif, stable et ne suit pas les liens symboliques ni les
dossiers temporaires `.fit-export-*`.

`--jobs auto` est le défaut : `min(4, CPU disponibles)`. Sur les systèmes qui le
permettent, les CPU disponibles sont ceux de l’affinité du processus ; ailleurs,
le nombre de processeurs logiques fourni par le système est utilisé. `all` utilise
ce nombre complet ; un entier strictement positif permet un réglage manuel.
Il ne s’agit pas d’une détection des cœurs physiques ni d’un plafond de mémoire.

`--details`, `--gps` et `--gps-limit` s’appliquent aux Markdown du batch.
`--details` n’enrichit pas le registre. `--output`, `--force` et `--stdout` sont
réservés à la conversion individuelle ; `--jobs` est réservé au batch.
Les combinaisons invalides sont refusées avant tout verrou ou parsing (code 2).

## Reprises et publication

Le batch valide le registre avant de commencer. Un registre absent est accepté ;
un registre invalide bloque l’import et indique `--sync-history`.

L’identité est le SHA-256 des octets FIT décompressés, calculé à la lecture, sans
seconde lecture pour le hachage. Les identités déjà inscrites avec un Markdown
régulier présent sont ignorées avant parsing. Un lien absent, symbolique ou
manquant entraîne une conversion. Des copies renommées ou compressées sont la
même activité ; deux FIT différents ne sont pas fusionnés par date ou distance.
Les doublons internes au lot ne sont publiés qu’une fois ; des doublons déjà en
calcul simultanément peuvent néanmoins avoir été parsés avant cette décision.

Les travailleurs préparent le Markdown, les points GPS, les champs de nommage et
l’entrée d’historique, sans publier de fichier. Le coordinateur conserve au plus
un nombre de tâches en attente égal au nombre de travailleurs. Il consomme les
résultats dans l’ordre de l’inventaire pour obtenir les mêmes noms quel que soit
le parallélisme, génère le GPX avec le nom final puis appelle `export_activity()`.
Les données complètes des records ne sont pas renvoyées au coordinateur.

Après export réussi, les sources sont retirées et leurs octets exacts archivés.
Les doublons ignorés restent dans le dossier source. Utiliser une copie du dossier
Strava pour conserver l’original intact. Une erreur sur un FIT n’interrompt pas
les autres conversions ; les protections de restauration de chaque export restent
celles de la conversion individuelle.

Le registre est fusionné après les exports : une seule lecture finale, un seul
tri et un seul remplacement atomique. Seules les activités publiées avec succès
sont ajoutées ; les identités antérieures sont conservées et les liens réaffectés
sont retirés. Une erreur propre au registre conserve les exports et le code 0,
avec avertissement et chemin du dossier d’archives. Une erreur de conversion ou du
moteur batch donne le code 1. Le bilan distingue exports, ignorés, erreurs et
fichiers non traités, ainsi que l’état de la mise à jour du registre.

Ctrl+C arrête la soumission des tâches, tente d’inscrire les exports déjà publiés
et donne le code 130. Pendant la publication d’une activité, ce signal est différé
jusqu’à la fin de la transaction et de l’enregistrement de son résultat. Les
travailleurs déjà actifs terminent leurs calculs sans publier leurs résultats.
Un arrêt brutal peut toujours laisser des exports absents du registre.

## Verrou commun

Les commandes d’écriture prennent un verrou exclusif non bloquant dans le fichier
`.fit-extractor.lock`, à la racine du projet, ignoré par Git. Une seconde commande
est refusée (code 1) ; `--stdout` ne prend pas ce verrou et reste disponible.
Le fichier persiste, mais le verrou système est automatiquement libéré à la
fermeture du processus. Ne pas supprimer le fichier pour débloquer une commande.
Les travailleurs utilisent `spawn` pour ne pas hériter du verrou parent.

Ce verrou coordonne les CLI de cette version du projet, pas un éditeur manuel,
une ancienne version du programme ou des appels directs aux utilitaires Python.
Éviter de modifier le registre à la main pendant une commande.

## Synchronisation et réparation

`--sync-history` lit les archives de `export/` et contrôle les associations avec
les Markdown, sans déplacement ni régénération des exports. Les FIT connus sont
identifiés par empreinte ; seuls les inconnus nécessitent un parsing des métriques.

- Registre valide : préserver ses entrées, ajouter les archives absentes et
  contrôler les liens. Une ligne supprimée est réintroduite si son FIT existe.
- Registre absent : reconstruire depuis les archives. Un dossier sans activités
  produit un registre vide valide.
- Registre cassé : récupérer les lignes v1 valides, y compris celles d’activités
  archivées ailleurs, puis compléter depuis les FIT. Signaler les lignes perdues
  et les identifiants répétés. Une sauvegarde exacte est créée sous
  `historique_activites.md.bak-<date UTC>-<suffixe unique>` avant le remplacement.

Une suppression de ligne sans ajuster le compteur final, une troncature, une
cellule invalide ou un en-tête endommagé peuvent ainsi être réparés. Les métriques
d’une ligne irrécupérable ne peuvent être retrouvées sans son FIT ; la ligne reste
dans la sauvegarde. Un fichier cassé sans aucune donnée récupérable reste intact.
Les registres symboliques, non réguliers, inaccessibles et les versions futures
inconnues restent refusés. La réparation nécessite une lecture complète des
archives ; si une lecture, un parsing, une sauvegarde ou la publication échoue,
le registre d’origine reste intact et la commande retourne 1.

Les liens existants exploitables sont conservés, sauf contradiction avec les
archives ou partage du même chemin entre identités distinctes. Une nouvelle
association exige une seule destination candidate et une famille d’archives
sans ambiguïté. Les `_dupN`, plusieurs contenus pour le même Markdown ou plusieurs
Markdown pour une identité sont signalés ; aucun lien n’est inventé. Les activités
restent inscrites sans lien si nécessaire. Les Markdown sans archive associée sont
signalés sans tenter d’en déduire l’identité ou les métriques. Les archives hors
`export/` ne sont pas parcourues ; leurs lignes encore récupérables sont conservées.

## Validation et mesures

Commandes de validation :

```bash
.venv/bin/python -B -m unittest discover -s tests -v
.venv/bin/python -B extractor.py --help
git diff --check
```

Les 71 tests de la suite passent. Ils construisent des FIT synthétiques en mémoire et utilisent des dossiers
temporaires. Ils couvrent notamment une vraie exécution multiprocessus, les
reprises FIT/gzip, les collisions, le verrou entre commandes, Ctrl+C, la restauration
d’export et la réparation avec sauvegarde exacte et erreurs injectées.

Mesure locale du 10 octobre 2026, sur huit copies de FIT course, trail, vélo et
natation, sans `--details`. Une exécution par configuration, stockage local ; ce
petit échantillon n’est pas une prédiction pour 900 FIT.

| Processus | Durée totale | Pic de RSS agrégée estimé |
|---:|---:|---:|
| 1 | 3,03 s | 51,3 Mio |
| 2 | 2,18 s | 127,1 Mio |
| 4 | 1,43 s | 212,3 Mio |
| 8 | 1,29 s | 326,0 Mio |

La mémoire est la somme des RSS du coordinateur et de ses descendants, échantillonnée
toutes les 50 ms sous Linux ; elle peut compter plusieurs fois des pages partagées
et manquer des pics brefs. Le gain entre quatre et huit processus est modeste sur
cet échantillon, pour une consommation mémoire supérieure.

L’échantillon inclut deux FIT identifiés Suunto et un Garmin ; les cinq autres
n’exposent pas de fabricant reconnu par le détecteur actuel.
Les huit exports de chaque configuration (Markdown, GPX, archives et registre)
ont été comparés octet pour octet à la version précédente en séquentiel. Huit
rendus `--stdout`, avec/sans `--details` et GPS échantillonné, sont également
identiques. Une reprise gzip et la restauration d’une ligne supprimée ont été
vérifiées sur les copies ; les empreintes des originaux sont inchangées.
La compatibilité sans GPS est couverte par les FIT synthétiques. La branche de
verrouillage Windows n’a pas été exécutée dans cet environnement Linux.
