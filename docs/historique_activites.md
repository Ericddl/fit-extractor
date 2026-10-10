# Spécification — Lot 1 : historique local des activités

> Évolution : cette spécification décrit le lot initial. Le batch, le verrou commun
> et la synchronisation/réparation explicite sont désormais livrés et décrits dans
> [batch.md](batch.md), qui remplace les anciennes exclusions correspondantes.
> Le format v1, les unités, les identifiants et les règles de tri restent inchangés.

**Projet :** `fit-extractor`

**Date :** 2 octobre 2026

**Statut :** implémentée et validée le 3 octobre 2026

**Emplacement :** `docs/historique_activites.md`

## 0. Revue et décisions confirmées

La revue porte sur `extractor.py`, `activity_analysis.py`, `file_manager.py`,
`gpx_exporter.py`, les instructions du dépôt et `docs/SPEC.md`. Les unités et les
dates ont aussi été vérifiées dans le `fitparse` installé et, en lecture seule,
sur trois archives locales : trail Suunto, vélo Garmin et natation Suunto.
Cette revue a fixé les règles mises en œuvre dans ce lot.

### Ajustements nécessaires par rapport à la proposition initiale

| Constat avant implémentation | Adaptation retenue |
|---|---|
| `parse_fit(path)` lit et décompresse les octets dans une variable locale ; son résultat ne les expose pas. | Ajouter un crochet limité pour calculer l’empreinte dans cette fonction, uniquement en mode export. Une intégration sans aucun changement du parser imposerait une seconde lecture. |
| Les champs extraits sont des couples `(valeur, unité)`. `numeric_field()` sait déjà convertir m/km et rejette booléens et nombres non finis. | Réutiliser cet utilitaire pur ; ne pas appliquer un facteur uniforme à tous les champs de distance. |
| `resolve_activity_date()` peut utiliser `session.timestamp`, `session.date`, puis la date du jour. | Ne pas réutiliser cette fonction pour dater le registre : elle répond au besoin de nommage. |
| Le titre individuel affiche `running (trail)`, etc. ; aucun dictionnaire de traduction des sports n’existe. | Définir des libellés français propres au registre sans modifier les Markdown individuels. |
| `export_activity()` renvoie le chemin réel de l’archive, avec son éventuel suffixe `_dupN`. | Utiliser ce chemin dans le message de reprise après un échec d’historique. |
| `docs/SPEC.md` exclut l’index global, le HTML et l’écrasement automatique des Markdown. | Documenter les exceptions limitées au registre généré : index incrémental, commentaires techniques et remplacement sans `--force`. |
| Les exports existants sont déjà accompagnés d’archives FIT. | Leur reprise sans nouveaux exports nécessiterait un mode dédié ; elle reste hors de ce lot conformément au choix confirmé ci-dessous. |

### Choix d’usage confirmés lors de la revue

1. **Tableau pour le coaching, Markdown seul.** Les valeurs présentées et
   arrondies suffisent à ce lot. Aucune source structurée supplémentaire destinée
   à de futurs calculs de charge ou de progression n’est ajoutée.
2. **Nouvelles conversions uniquement.** Aucune reprise automatique ni commande
   dédiée pour indexer les exports déjà présents. Une reconversion volontaire
   d’une ancienne archive reste possible avec les effets habituels sur les fichiers.
3. **Avertissement et code 0 après un export réussi.** Un échec du seul historique
   ne rend pas la conversion échouée. Une boucle shell ne peut donc pas détecter
   une inscription manquée par le seul code de sortie.

Le choix technique recommandé pour le périmètre actuel reste un registre Markdown
versionné, alimenté après l’export. Il faut accepter qu’il puisse être incomplet
et que ses liens puissent devenir périmés en cas d’échec après un remplacement.

## 1. Objectif et périmètre

À chaque conversion réussie d’un fichier `.fit` ou `.fit.gz`, alimenter un registre Markdown synthétique des activités traitées. Ce registre doit rester trié et sans doublons lorsqu’on traite des fichiers anciens dans un ordre quelconque ou qu’on retraite le même fichier.

La commande habituelle reste inchangée :

```bash
python extractor.py import/Natation_le_midi.fit
```

Elle produit les sorties actuelles — Markdown individuel, GPX si disponible et archive FIT — puis met à jour `export/historique_activites.md`.

Ce lot comprend uniquement le registre, sa déduplication et son classement. Il n’introduit ni option CLI, ni mode batch, ni réseau, ni API Strava, ni nouvelle dépendance. Les agrégations hebdomadaires, `athlete_state.md`, la charge calculée et l’enrichissement Strava restent hors périmètre. Une boucle shell séquentielle suffit pour traiter plusieurs fichiers.

## 2. Contrats à préserver

- Le contenu des Markdown individuels et des GPX reste identique à celui du traitement actuel, à options identiques.
- Nommage, indices, collisions, `--force` et archivage restent inchangés ; aucune déduplication des fichiers exportés n’est ajoutée.
- `export_activity()` conserve sa transaction actuelle et son mécanisme de restauration. L’historique n’entre pas dans cette transaction ; la protection du chemin réservé est vérifiée avant publication.
- `--stdout` ne calcule pas l’empreinte, ne prépare pas d’entrée, ne lit ni ne met à jour l’historique, ne crée aucun dossier et ne déplace aucun fichier. Comme aujourd’hui, il prend priorité sur `--output`. `--details`, `--gps` et `--gps-limit` ne changent pas les métriques du registre.
- Le traitement reste local, sous Python 3.10+, avec `fitparse` comme seule dépendance externe. Les calculs de `activity_analysis.py` restent purs.
- Les archives `.fit.gz` sont conservées compressées ; leur décompression reste exclusivement en mémoire.

## 3. Emplacement et contenu du registre

Le registre unique est placé dans `export/historique_activites.md`, sous la racine du projet, indépendamment du répertoire courant. Il rassemble également les activités exportées avec `--output` vers un autre dossier. Le lien vers leur Markdown est relatif au dossier du registre, avec encodage approprié des espaces et caractères spéciaux.

Le fichier est généré et maintenu par l’outil ; l’édition manuelle du tableau n’est pas prise en charge. Aucun fichier JSON ou base de données supplémentaire n’est nécessaire pour ce lot.

Il s’agit d’un journal des conversions inscrites, pas d’un inventaire vérifié du
contenu actuel de `export/`. Le déplacement du registre seul casse ses liens
relatifs ; les copies destinées à une IA restent lisibles mais ne sont pas mises à jour.

Exemple illustratif, avec valeurs fictives :

```markdown
# Historique des activités
<!-- fit-extractor-history:v1 -->

Périmètre : activités traitées avec succès et enregistrées par cet outil.
Débuts en UTC (début FIT, sinon premier record horodaté) ; « - » signifie donnée absente.
D+, FC, TSS et TE fournis par le FIT, sans recalcul.

| Début (UTC) | Sport | Distance (km) | Durée chrono | D+ (m) | FC moy. (bpm) | FC max (bpm) | TSS | TE aérobie | Fichier |
|---|---|---:|---|---:|---:|---:|---:|---:|---|
| 2026-09-22T10:17:03Z | Natation eau libre | 1.72 | 00:35:10 | - | 138 | 161 | - | 2.4 | [Séance](2026-09-22_swimming_open_water_001.md) <!-- activity-id:sha256:EMPREINTE_COMPLETE --> |

<!-- fit-extractor-history:end rows:1 -->
```

L’empreinte complète de chaque activité est conservée dans un commentaire HTML à l’intérieur de la cellule « Fichier ». Elle n’encombre pas le tableau rendu, mais permet sa relecture fiable. Dans le fichier réel, elle contient les 64 caractères hexadécimaux SHA-256 ; `EMPREINTE_COMPLETE` est uniquement un substitut dans cet exemple.

Le commentaire reste obligatoire même sans lien :
`- <!-- activity-id:sha256:EMPREINTE_COMPLETE -->`. Sans lui, une ligne dont le
Markdown a été remplacé perdrait son identité. Le marqueur final et son nombre
de lignes permettent de refuser un fichier interrompu, même à une frontière de
ligne valide. Ils ne détectent pas toute modification manuelle cohérente du fichier.

Les colonnes et leur ordre sont fixes en version 1, même lorsque certaines métriques sont absentes. Les cellules textuelles doivent être échappées pour préserver les séparateurs du tableau et éviter les retours à la ligne internes. Le registre ne contient ni coordonnées GPS ni séries brutes.

### Origine et présentation des valeurs

Utiliser les données déjà extraites en mémoire pour l’activité courante, sans relire le Markdown individuel et sans reparsing du FIT.

| Colonne | Règle |
|---|---|
| Début | `session.start_time`, sinon premier `record.timestamp` valide dans l’ordre du fichier, sinon `-`. Normaliser en UTC ; conserver les secondes et toute fraction disponible. Aucun repli sur `session.timestamp`, une date sans heure, le nom du fichier ou la date d’import. |
| Sport | `session.sport` et `session.sub_sport` ; traduction limitée définie ci-dessous, valeur technique en repli, `-` si absents. |
| Distance | `session.total_distance` via `numeric_field(..., "km")`, affichée à deux décimales. Le parser installé fournit ce champ en m, tandis que `record.distance` est en km. Aucun repli sur les records. |
| Durée chrono | `session.total_timer_time`, en s, rendu `HH:MM:SS` sans limite à 24 h. Tronquer les fractions de seconde comme `_fmt_duration()`. Aucun repli sur `total_elapsed_time` ni sur les horodatages. |
| D+ | `session.total_ascent`, en m ; aucun repli sur une estimation GPS ou terrain. |
| FC moyenne / max | `session.avg_heart_rate` / `session.max_heart_rate`, en bpm ; aucune nouvelle moyenne des records. |
| TSS | `session.training_stress_score`, unité `tss`. Aucun calcul ni substitution par une autre mesure de charge. |
| TE aérobie | `session.total_training_effect`, sans unité. Ne pas y substituer `total_anaerobic_training_effect`, qui reste dans le Markdown individuel. |
| Fichier | Lien vers le Markdown individuel effectivement publié, et identifiant technique caché. |

Les `datetime` naïfs provenant de `start_time` et `record.timestamp` sont
interprétés comme UTC : le `fitparse` installé les construit avec
`datetime.utcfromtimestamp()`. Les dates avec fuseau sont converties en UTC.
Ne jamais utiliser le fuseau de la machine ni les champs `local_timestamp`.
Rendu ISO 8601 avec suffixe `Z` ; comparer les instants, pas leurs chaînes de texte.

Une valeur absente, booléenne, structurée, non finie, négative ou d’unité inattendue
devient `-`. Zéro reste valide pour distance, durée, D+, TSS et TE ; la FC doit
rester strictement positive après arrondi, sinon afficher `-`. Ne pas inventer
de seuil physiologique maximal. D+, FC : arrondi à l’entier ; TSS et TE : une
décimale, selon le formatage Python.
Le point décimal est fixe, indépendamment de la locale. La relecture conserve
ces valeurs présentées ; elle ne permet pas de retrouver leur précision d’origine.

Libellés minimaux : `running` → « Course », `running/trail` → « Trail »,
`cycling` → « Vélo », `cycling/road` → « Vélo route », `cycling/mountain` → « VTT »,
`swimming` → « Natation », `swimming/open_water` → « Natation eau libre »,
`swimming/lap_swimming` → « Natation en bassin ». Omettre `generic` et les
sous-sports identiques au sport ; conserver les autres valeurs techniques entre
parenthèses. Un sous-sport seul reste affichable. Ce mapping concerne seulement
le registre ; les fichiers individuels gardent leur rendu actuel.

Une absence de TSS ne signifie pas une charge nulle. Le registre ne garantit ni
une métrique de charge commune à tous les appareils ni la comparabilité des TE.

## 4. Identité, déduplication et classement

**Identifiant retenu :** SHA-256 du contenu binaire FIT décompressé, calculé à partir des octets déjà disponibles en mémoire, avant archivage. Ne pas inclure le nom du fichier ni les métadonnées de compression gzip.

- Même FIT renommé, copié ou compressé en `.fit.gz` : même identifiant.
- Identifiant inconnu : ajouter une ligne.
- Identifiant connu : remplacer la ligne par les métriques et le lien du dernier export réussi ; le nombre de lignes reste constant.
- Des fichiers FIT aux octets différents sont des activités distinctes pour ce lot, même s’ils décrivent possiblement la même séance. Aucune fusion approximative par date, distance ou durée.

Cette garantie porte uniquement sur le registre. Retraiter un FIT peut encore produire un nouvel indice ou une archive `_dupN`, conformément au comportement actuel. Le registre référence alors le dernier Markdown réussi.

Après chaque ajout ou remplacement, trier toutes les lignes par instant de début UTC **décroissant**, avec la précision disponible, et non par ordre d’import ou nom de fichier. À instant égal, départager par identifiant dans l’ordre lexicographique croissant. Placer les activités sans début exploitable en fin de tableau, également ordonnées par identifiant croissant.

Lors d’une mise à jour réussie, si le chemin publié était référencé par une autre
activité, conserver cette ancienne ligne mais remplacer son lien par `-`, en
gardant son commentaire d’identité. Appliquer cette règle quel que soit le mode
de nommage : `--output --force` en est le cas habituel, mais une suppression
manuelle peut aussi permettre de réutiliser un ancien nom automatique.

Comparer les destinations normalisées, pas les URL encodées littérales : chemins
absolus/relatifs et segments `..` peuvent désigner le même fichier. Produire les
liens avec des séparateurs `/` et un encodage des caractères spéciaux, notamment
espaces, `%`, `#`, `?`, parenthèses et `|`. Décoder une seule fois à la relecture.
Les destinations des liens restent des données ; ne jamais les ouvrir pour relire
des métriques ni les utiliser pour supprimer un fichier.

Ne pas supprimer automatiquement des lignes lorsque des fichiers sont déplacés
ou effacés manuellement. Si la mise à jour échoue après un export forcé, l’ancien
lien peut désormais désigner une autre activité : le registre étant indépendant
de la transaction, il ne peut pas garantir cette cohérence dans le cas d’échec.

## 5. Mise à jour et gestion des erreurs

Ordre obligatoire :

1. Préparer les données de l’activité et son identifiant en mémoire.
2. Vérifier le chemin réservé, puis exécuter l’export existant via `export_activity()`.
3. Uniquement après son succès, lire le registre existant, vérifier son format, effectuer l’ajout/remplacement et trier.
4. Rendre le fichier complet en mémoire, écrire un temporaire dans le même dossier, puis remplacer le registre par une opération atomique (`os.replace`). Nettoyer le temporaire en cas d’échec.

Si le registre n’existe pas, le créer. S’il existe mais est illisible, tronqué, d’une version inconnue, ou contient des lignes invalides ou des identifiants en double, **ne pas l’écraser ni ignorer silencieusement des lignes**. Préserver ses octets et signaler l’erreur. Refuser de remplacer un registre qui est un lien symbolique.

La relecture porte uniquement sur le format produit par l’outil, sans parser
Markdown généraliste. Vérifier le marqueur de version, les dix colonnes dans
l’ordre prévu, chaque cellule, un identifiant SHA-256 de 64 caractères hexadécimaux
minuscules par ligne, et le marqueur final avec son effectif. Un fichier vide
existant, un contenu inattendu ou une date invalide est une erreur ; seul un
fichier absent autorise une création. Un registre valide sans activité contient
les en-têtes et le marqueur final `rows:0`. Ne pas convertir les cellules
corrompues d’une ancienne ligne en `-` pour la faire passer silencieusement.

L’aller-retour lecture/rendu d’un registre canonique doit être stable : ne pas
doubler l’échappement HTML des textes ni l’encodage des liens. Écrire en UTF-8,
avec fins de ligne LF et saut de ligne final. Fermer le temporaire avant le
remplacement. Si son nettoyage échoue, signaler son chemin sans masquer la cause
initiale. L’atomicité évite un registre partiellement publié ; elle n’ajoute pas
de garantie de durabilité après coupure électrique.

Un échec d’historique ne restaure pas l’export, ne modifie pas ses fichiers et ne change pas le code de succès de la conversion : retour **0**, avec avertissement explicite sur `stderr`, par exemple :

```text
Activité exportée avec succès.
Attention : historique des activités non mis à jour : <cause>.
Archive disponible pour reprise : <chemin réellement renvoyé par export_activity()>.
```

Conserver les messages actuels de succès Markdown/GPX/archive ; leur adjoindre
l’avertissement si nécessaire. La source ayant déjà été archivée, une reprise
utilise l’archive FIT ou une copie de celle-ci ; ne pas demander de relancer sur
le chemin source supprimé. Une erreur de préparation propre au registre, y
compris le calcul d’empreinte, doit également rester non bloquante pour la
conversion. Isoler ces erreurs du bloc qui transforme les erreurs d’export en
code 1. En cas d’échec de parsing ou d’export, aucune lecture du contenu ni
écriture du registre ne doit avoir lieu ; la vérification préalable de son
chemin reste permise.

La réécriture du registre généré est automatique, sans exiger `--force`. Son chemin est réservé : une sortie `--output` qui désigne le registre doit être refusée avant publication, sans écraser les données, même avec `--force`.

Cette collision est une erreur d’export (code 1), pas un simple avertissement
d’historique : la source et les sorties doivent rester intactes. Comparer les
chemins résolus et, pour les fichiers existants, leur identité comme le fait
`_same_file()` ; couvrir les alias relatifs, les parents symboliques et les liens
physiques. Ce refus s’applique même si le registre n’existe pas encore. La
branche `--stdout` n’effectue pas cette vérification, puisqu’elle ignore la sortie.

La garantie vise une exécution isolée et des imports **séquentiels**. La mise à jour du registre n’est pas transactionnelle avec l’export : un arrêt entre les deux peut laisser une séance absente. Les imports concurrents, le verrouillage interprocessus et la récupération après coupure restent hors périmètre.

## 6. Intégration

Les points d’intégration ci-dessous ont été vérifiés dans le code actuel.

| Fichier | Responsabilité |
|---|---|
| `extractor.py` | Calculer l’empreinte au point de lecture des octets ; préparer l’entrée hors `--stdout` ; déclencher la mise à jour après `export_activity()` réussi ; avertir avec `final_fit` en cas d’échec. |
| `activity_history.py` — nouveau | Construire les entrées, interpréter/valider le texte du tableau versionné, remplacer par identifiant, trier et produire le Markdown. Ces transformations restent pures ; réutiliser `numeric_field()` de `activity_analysis.py`. |
| `file_manager.py` | Résoudre le chemin global et les liens ; lire et remplacer atomiquement le registre via la stdlib ; protéger le chemin réservé. Ne pas élargir la transaction `export_activity()`. |
| `tests/test_activity_history.py` — nouveau | Tests ciblés des données, de la relecture, du remplacement et du tri. |
| `tests/test_history_integration.py` — nouveau | Tests ciblés des branchements CLI, écritures et erreurs, avec `tempfile` et `unittest.mock`. |
| `README.md`, `docs/SPEC.md` | Documenter le fichier ajouté, la déduplication limitée au registre et les avertissements. Mettre à jour architecture, flux, limites, historique d’évolution et exceptions aux règles « pas d’index global », « pas de HTML » et « pas de remplacement sans `--force` ». |
| `AGENTS.md`, `CONTRIBUTING.md` | Actualiser les responsabilités, la présence de tests et leur commande. Préciser l’exception au remplacement automatique pour le seul registre généré. |
| `.gitignore` | Le registre global est déjà couvert par `/export/*`, y compris avec `--output` ailleurs. Ne pas ajouter de règle globale `historique_activites.md`, qui masquerait aussi cette spécification. |

La signature est `parse_fit(path: Path, *, include_history_id: bool = False) -> dict`.
La CLI active ce paramètre avec `not args.stdout`. Le résultat inclut alors une
métadonnée `history` contenant `activity_id` ou `error` ; les octets
bruts ne sont pas conservés dans le dictionnaire ni exposés au rendu. Le
calcul utilise exactement les octets déjà décompressés transmis à `FitFile`.
Ce crochet limité ne change ni l’extraction générique ni les métriques.

Les fonctions pures du registre reçoivent les champs extraits et les liens déjà
préparés ; les accès disque et comparaisons de chemins restent dans
`file_manager.py`. Éviter une dépendance de `activity_history.py` vers
`extractor.py`, qui l’importera lui-même. Ne pas déplacer les utilitaires de rendu
existants pour cette seule évolution.

Aucun refactoring général du parser, des analyses sportives ou du GPX ; aucun
changement dans `requirements.txt`. Les tests utilisent la stdlib et des
données synthétiques ; aucun FIT personnel n’est versionné. La documentation
principale et les instructions du dépôt décrivent également ce comportement.

## 7. Validation et critères d’acceptation

Les tests doivent établir les comportements suivants :

1. Premier export réussi : création d’un registre contenant une ligne et un lien correct ; conversion sans GPS également enregistrée.
2. Import d’une activité récente, puis ancienne, puis intermédiaire : classement final décroissant, indépendant de l’ordre de traitement. Même jour, heures et secondes différentes : ordre exact.
3. Même FIT renommé, retraité ou compressé : une seule ligne, lien mis à jour. Deux FIT distincts : deux lignes, même avec des métriques égales.
4. Début absent, valeurs manquantes, zéros valides et unités : rendu conforme, aucun faux zéro ni durée trompeuse. Relecture/réécriture sans perte des lignes précédentes.
5. Échec de parsing ou d’export : registre inchangé. `--stdout` : aucune opération d’historique et aucun dossier créé.
6. Échec de lecture, écriture temporaire ou remplacement : registre précédent identique octet pour octet ; sorties d’activité conservées ; avertissement et retour 0. Registre corrompu ou inconnu : aucune destruction.
7. Chemin personnalisé, espaces, `--force`, collision d’archive et chemin du registre réservé : liens et protections conformes ; aucun changement de la logique d’export existante.

Compléments issus de la revue :

- UTC naïf/avec fuseau, secondes identiques mais fractions différentes, premier
  record invalide, absence de `start_time` malgré un `session.timestamp`, et
  dates absentes : aucun repli sur le jour courant ni le fuseau de la machine.
- Distance en m et km, unité inattendue, booléens, FC nulle, durées fractionnaires
  et supérieures à 24 h ; TSS absent conservé comme absent. Vérifier les sports
  connus et inconnus, sans changer les titres individuels.
- Même contenu compressé avec des métadonnées gzip différentes : même identité ;
  aucune seconde lecture ni reparsing pour calculer l’identifiant. Avec `--stdout`,
  aucun calcul d’empreinte, même si `--output` désigne le registre.
- Relire plusieurs fois les textes échappés et les liens contenant `%`, `#`, `|`,
  espaces et caractères accentués ; conserver exactement les valeurs précédentes.
  Refuser aussi un fichier vide existant, un marqueur final absent ou un effectif
  incorrect, sans changer les octets du registre.
- Après remplacement d’une activité par une autre au même chemin, relire l’ancienne
  ligne sans lien et vérifier que son identité est conservée. Tester aussi un
  chemin automatique réutilisé. Injecter un échec de mise à jour après `--force`
  pour vérifier l’avertissement et documenter le lien désormais périmé.
- Refuser les alias du chemin réservé avant publication ; refuser de mettre à
  jour un registre symbolique, même si sa cible est absente. En cas d’échec,
  afficher le chemin effectif de l’archive, y compris avec `_dupN`.

Commande de la suite créée par ce lot :

```bash
.venv/bin/python -B -m unittest discover -s tests -v
```

Compléter, si des copies de FIT sont disponibles, par une conversion Suunto et Garmin, avec et sans GPS, puis `.fit.gz`. Comparer les sorties individuelles avant/après à options identiques. Les contrôles d’écriture se font dans un environnement temporaire, sur des copies exclusivement. Rapporter les commandes exécutées et les cas non vérifiés.

**Résultat observable attendu :** une boucle shell séquentielle sur des FIT, dans un ordre quelconque, alimente progressivement un historique synthétique trié et dédupliqué, tout en conservant le fonctionnement actuel de chaque conversion.

## 8. Limites et suite éventuelle

L’historique ne représente que les activités enregistrées avec succès par cette évolution. Il n’indexe pas automatiquement les exports déjà présents. Pour les reprendre, traiter leurs archives ou des copies avec la commande existante, en acceptant les sorties individuelles supplémentaires prévues par le nommage actuel.

La prise en charge reste celle du programme actuel : une activité par invocation,
sans extension au multisession. Actuellement, `parse_fit()` fusionne les messages
`session` avec `dict.update()` ; ce résultat ne constitue pas une synthèse fiable
d’un triathlon. Le registre hérite de cette limite, sans prétendre la résoudre.
La récupération des sources historiques est extérieure à ce lot ; tous les
fichiers d’une archive tierce ne sont pas nécessairement des FIT compatibles.

Le registre conserve des valeurs de présentation arrondies. Il prépare une vue longitudinale lisible, mais des calculs futurs exigeant la précision originale devront repartir des FIT archivés ou faire évoluer explicitement son format.

Le SHA-256 déduplique des fichiers binaires identiques, pas nécessairement des
séances réelles : une même sortie réexportée par deux services peut produire
deux lignes. Le choix est volontaire pour éviter les fusions erronées.

Une mise à jour relit tout le registre, trie ses lignes et le réécrit : mémoire
proportionnelle au nombre d’activités et tri en `O(N log N)`. C’est adapté à un
historique personnel ; ce lot ne prévoit ni pagination ni export d’une période
pour limiter la taille du contexte envoyé à une IA.

Supprimer le registre fait repartir l’outil d’un historique vide à la conversion
suivante. Aucune reconstruction automatique ni réparation d’un registre corrompu
n’est prévue. Une reprise depuis les FIT peut récupérer les métriques, mais ne
retrouve pas à elle seule le dernier Markdown choisi par `--output` ou `--force`.

### Validation préalable de la spécification

- Lecture du code, des références du dépôt et de `fitparse/processors.py` et
  `fitparse/profile.py` dans le venv.
- Commande `.venv/bin/python -B -` : script ponctuel appelant `parse_fit()` et
  `detect_device()` sur trois archives existantes, sans export ni déplacement ;
  vérification des noms de champs, types, unités et dates naïves. Le TSS est absent
  de l’échantillon Garmin vélo ; le TE anaérobie y est présent.
- Même commande : vérification synthétique de `numeric_field()` pour une même
  distance représentée en m et km.

Ces contrôles ont validé les hypothèses avant développement. La validation de
l’implémentation est rapportée ci-dessous.

## 9. Validation de l’implémentation

- `.venv/bin/python -B -m unittest discover -s tests -v` : **32 tests réussis**,
  couvrant les métriques, les dates, la relecture, l’identité FIT/gzip, le tri,
  les collisions, les chemins réservés et les erreurs injectées. Les tests
  vérifient aussi un registre symbolique en boucle et le refus d’un fichier non
  régulier avant ouverture, pour éviter de bloquer la conversion.
- `.venv/bin/python -B extractor.py --help` : aide CLI vérifiée, aucune option ajoutée.
- `.venv/bin/python -B -` : comparaison ponctuelle de **16 rendus Markdown**
  (quatre activités, avec/sans `--details` et `--gps`) et de **4 GPX** aux références
  capturées avant modification. Tous sont identiques.
- `.venv/bin/python -B -` : cinq conversions CLI réelles, lancées par
  `subprocess.run()` dans une copie temporaire isolée du projet : course et trail
  Suunto, vélo Garmin, natation Suunto, puis reprise du trail compressé en `.fit.gz`.
  Résultat : quatre entrées triées, lien actualisé pour le FIT compressé,
  Markdown/GPX conformes et archives conservées octet pour octet.
- `git diff --check` : aucune erreur de mise en forme.

Les empreintes des quatre FIT originaux ont été vérifiées après les essais :
aucune modification. Les écritures ont été limitées aux dossiers temporaires ;
le `export/` réel n’a pas été alimenté par ces validations.

Limites : absence de GPS validée sur données synthétiques, pas sur un FIT indoor
réel. Les garanties après arrêt brutal, les imports concurrents et le multisession
restent hors périmètre. Les tests ne constituent pas une validation de tous les
matériels FIT ni de tous les calculs sportifs existants.
