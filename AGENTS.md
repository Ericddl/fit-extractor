# Instructions pour Codex

## Projet et références

`fit-extractor` convertit une activité `.fit` ou `.fit.gz` en Markdown dense pour
le coaching sportif par IA, et en GPX 1.1 si des coordonnées sont disponibles.
Le traitement est local, sans appel réseau ni API d’IA.

- `README.md` : installation et usage ; `CONTRIBUTING.md` : contributions.
- `docs/SPEC.md` : spécification principale, décisions et limites connues.
- `docs/historique_activites.md` : format et règles de l’historique local.
- `docs/file_manager_change.md` et `docs/gpx.md` : spécifications historiques,
  dont certaines propositions diffèrent du code livré.
- `docs/SPEC_template.md` : modèle de document.
- Vérifier le code avant de tenir un comportement documentaire pour acquis.

## Architecture et dépendances

- `extractor.py` : CLI `argparse`, parsing FIT, calcul HRV et rendu Markdown.
- `activity_analysis.py` : calculs purs d’allure, kilomètres, terrain et qualité, sans accès disque.
- `activity_history.py` : entrées, relecture, validation, tri et rendu du registre, sans accès disque.
- Les séries des graphiques Unicode sont échantillonnées dans `activity_analysis.py` ;
  leur rendu reste dans `extractor.py`.
- `file_manager.py` : chemins, nommage, collisions, archivage et publication séparée du registre.
- `gpx_exporter.py` : filtrage GPS et génération XML avec `xml.etree.ElementTree`.
- Python 3.10+ ; seule dépendance externe : `fitparse>=1.2.0` dans `requirements.txt`.
  Privilégier la bibliothèque standard ; justifier toute nouvelle dépendance.

Flux : lecture → décompression en mémoire → parsing → rendu Markdown/GPX en mémoire
→ préparation des fichiers → publication et archivage avec restauration sur erreur
→ mise à jour indépendante de l’historique après export réussi.
Les dossiers `import/` et `export/` sont ancrés à
la racine du projet, indépendamment du répertoire courant.
Nommage automatique : `YYYY-MM-DD_<activité>_<indice>`, avec indice incrémenté
en tenant compte des fichiers `.md`, `.fit`, `.fit.gz` et `.gpx` existants.

Repères dans le code :

- `parse_fit(path, *, include_history_id=False)` extrait les messages `session`,
  `lap`, `record`, `hrv`, `device_info`, `user_profile` et `zones_target` ; le rendu
  sélectionne ensuite les données utiles. `detect_device()` lit le fabricant ;
  la présence des champs détermine les sections, pas une matrice rigide par appareil.
- `analyze_records(records, sport)` produit qualité, kilomètres, terrain,
  altitudes et séries de graphiques sans modifier les records ni accéder au disque.
- `activity_history.py` expose `HistoryEntry`, `build_history_entry()`,
  `parse_history()`, `render_history()` et `upsert_history()` ;
  `update_activity_history()` dans `file_manager.py` gère les lectures et écritures.
- `move_processed_fit()` et `write_gpx_file()` sont des utilitaires autonomes ;
  la CLI publie le lot via `export_activity()`.

## Commandes

Depuis la racine, utiliser le venv existant ou l’installer si nécessaire :

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -B extractor.py --help
.venv/bin/python -B -m unittest discover -s tests -v
.venv/bin/python -B extractor.py mon_activite.fit --stdout
.venv/bin/python -B extractor.py mon_activite.fit --stdout --details
.venv/bin/python -B extractor.py mon_activite.fit --stdout --gps --gps-limit 30
.venv/bin/python extractor.py mon_activite.fit
```

- Un nom seul est recherché d’abord tel quel, puis dans `import/`.
- La conversion normale écrit dans `export/` et **déplace la source**.
- `--stdout` ne génère pas d’export, ne déplace rien et ne crée aucun dossier.
  `-B` évite les caches Python.
- `--details` ajoute les champs complémentaires et les synthèses de séries,
  sans RR bruts ; les moyennes d’échantillons ne sont pas pondérées par le temps.
  Compter les valeurs non numériques sans les moyenner ; exclure des synthèses
  les booléens, dates, coordonnées et RR. Résumer les listes de plus de 16 éléments,
  conserver les unités, échapper les cellules Markdown et éviter les doublons
  entre champs standard et `enhanced_*`.
- `--output chemin/seance.md` place aussi le GPX et la source archivée à côté.
- `--force` permet d’écraser le Markdown et le GPX. Une collision d’archive FIT
  entraîne un suffixe `_dupN`, pas un écrasement.
- Avec `--output --force`, retirer l’ancien GPX si l’activité n’a plus de GPS.
- `--gps` et `--gps-limit` concernent seulement le Markdown ; le GPX conserve
  toute la trace exploitable. Une limite non positive est refusée avant parsing.
- Codes de sortie : 0 succès, 1 erreur de traitement, 2 arguments invalides.
- L’historique global reste dans `export/historique_activites.md`, même avec
  `--output` ailleurs. Échec du seul historique : avertissement, archive indiquée,
  code 0. Aucun accès à l’historique ni calcul d’empreinte avec `--stdout`.
- Les analyses sportives sont affichées par défaut ; `--details` ajoute seulement
  les compléments techniques. Course : min/km ; natation : min/100 m ; vélo : km/h.
  Les autres sports utilisent aussi km/h. L’effort moyen utilise distance et
  durée chronométrée positives, sinon la vitesse moyenne FIT exploitable.
  Afficher les types/cycles/cadences de nage, les altitudes, la VAM en m/h et le
  Training Effect anaérobie lorsque les champs existent. Les pourcentages de zones
  FC utilisent la somme des durées de zones valides, pas la durée totale.
- Les graphiques Unicode sont inclus par défaut : altitude/distance, cardio/temps,
  vitesse ou allure/temps, sur 60 caractères et avec des échelles indépendantes.

## Validation

La suite `unittest` dans `tests/` couvre l’historique et son intégration avec
l’export, sur données synthétiques et dossiers temporaires. Pas de CI ni de
configuration de lint ; aucun dossier `examples/` ou jeu de FIT personnel versionné.

- Vérifier l’aide CLI et le rendu `--stdout` sur un FIT approprié si disponible.
- Pour une évolution fonctionnelle, vérifier si possible Suunto et Garmin,
  une activité avec GPS et une sans GPS, ainsi que `.fit.gz` si concerné.
- Tester les écritures, collisions et déplacements uniquement sur des copies
  de données dans un emplacement de test ; `--stdout` ne valide pas ces étapes.
- Simuler les erreurs d’écriture et d’archivage avec `unittest.mock` et `tempfile` ;
  vérifier la restauration octet pour octet et le rendu avec/sans `--details`.
- Vérifier les kilomètres interpolés, interruptions, régressions, pentes ±3 %,
  FC partielle et données absentes sur des records synthétiques ; compléter sur
  copies de FIT course/trail/vélo/natation sans toucher aux originaux.
- Indiquer les commandes exécutées et les limites de validation ; ne pas
  présenter l’affichage de l’aide comme un test complet de conversion.
- Graphiques : contrôler largeur, constantes, trous, axes régressifs, unités,
  vitesse nulle en allure et cardio/vitesse sans GPS ni distance.
- Historique : vérifier la déduplication FIT/gzip, le tri UTC, la relecture stable,
  les collisions de liens, le chemin réservé et la préservation du registre sur erreur.

## Conventions et précautions

- Garder les changements ciblés, les fonctions en `snake_case` et les
  responsabilités dans les modules indiqués. Mettre à jour la documentation
  concernée si le comportement ou la CLI change.
- Toujours utiliser `StandardUnitsDataProcessor()` ; respecter les unités
  renvoyées par champ et ne pas reconvertir les coordonnées déjà en degrés.
  Le processeur fournit les vitesses en km/h, `record.distance` en km et
  `session.total_distance` en m. Utiliser `numeric_field()` pour convertir les
  unités et `preferred_number()` pour privilégier un champ `enhanced_*` valide.
- Extraire les champs génériquement dans les messages traités, ignorer
  `unknown_XXX` et gérer les valeurs absentes sans faire échouer le rendu.
- Garder les titres et libellés utilisateur en français, les unités explicites
  et les sections facultatives conditionnées par les données disponibles.
- HRV : rendre RMSSD et SDNN, jamais les intervalles RR bruts.
- Les kilomètres et le terrain utilisent la distance FIT, pas une distance GPS
  reconstruite. Ne pas interpoler les interruptions ; signaler les analyses incomplètes.
  Supprimer les analyses kilométriques si les horodatages ou la distance reculent.
- Terrain : médiane de cinq points par portion continue, tronçons de 50 m, seuils
  ±3 %, dénivelé estimé. Les FC de ces analyses sont pondérées par les durées valides,
  contrairement aux synthèses d’échantillons de `--details`.
  N’utiliser pour la FC que les intervalles dont les deux extrémités sont valides,
  et afficher la distance analysée.
- Ne pas confondre durée chronométrée, durée enregistrée et mouvement réel ; ne
  pas inventer de puissance, de SWOLF ou d’interprétation des champs propriétaires.
- Partager le seuil d’interruption entre analyses et graphiques ; ne pas tracer
  à travers les trous. En allure, plus haut = plus rapide ; `·` = vitesse nulle.
  Les bornes des graphiques concernent les valeurs tracées, pas les extrema bruts.
  Le seuil de `_time_intervals()` vaut `max(10 s, 5 × médiane des intervalles
  temporels positifs)`. Interpoler seulement entre records adjacents valides.
  Les graphiques ont 60 positions régulièrement espacées, extrémités comprises,
  avec axes début/milieu/fin ; un espace représente une valeur non tracée.
  Signaler les séries constantes ou indisponibles. Cardio et vitesse/allure ne
  nécessitent ni GPS ni distance. Un recul temporel invalide tous les graphiques ;
  un recul de distance invalide uniquement celui d’altitude.
- Décompresser uniquement en mémoire ; préserver l’extension composée `.fit.gz`
  à l’archivage (`name.lower().endswith(".fit.gz")`).
- Historique : SHA-256 des octets FIT décompressés, sans seconde lecture pour le
  hachage. Conserver les identifiants cachés même sans lien. Ne pas réparer ou
  écraser un registre invalide, symbolique ou d’une version inconnue.
  Le tableau v1 conserve dix colonnes fixes, des valeurs de présentation arrondies
  et un marqueur final avec le nombre de lignes. Trier par début UTC décroissant,
  puis identifiant croissant ; placer les dates absentes à la fin. Le début vient
  de `session.start_time`, sinon du premier record horodaté valide dans l’ordre du
  fichier, jamais du nommage ou de la date du jour. Garder la précision disponible.
  La déduplication porte sur les octets FIT identiques, pas sur les séances réelles.
- Le registre généré est remplacé atomiquement sans `--force`, après l’export et
  hors de sa transaction. Cette exception ne concerne aucun Markdown individuel.
  Une sortie qui désigne le registre est refusée avant publication, même avec `--force`.
  Les liens sont relatifs au registre et encodés dans le Markdown. Si une sortie
  est réaffectée, retirer l’ancien lien en conservant l’identité et les métriques.
  Aucun indexage automatique des exports existants ni réparation n’est prévu.
  Une erreur ou un arrêt après export peut laisser une entrée absente ; après
  `--force`, un échec du registre peut laisser un lien périmé.
- Utiliser `export_activity()` pour le lot Markdown/GPX/archive ; supprimer la
  source en dernier et restaurer les sorties sur erreur gérée. Conserver les
  sauvegardes et signaler leurs chemins si la restauration échoue elle-même.
  Cette protection ne couvre ni arrêt brutal ni écritures concurrentes.
- GPX : latitude/longitude valides, altitude et heure si disponibles ; pas
  d’extensions FC, cadence ou puissance, ni de fichier sans points exploitables.
- Ne jamais versionner les données sportives personnelles. `import/`, `export/`
  et les formats d’activité sont ignorés ; seuls leurs `.gitkeep` sont suivis.
- Limites actuelles : une activité par appel, multisession non gérée, validation
  indoor limitée ; ne pas élargir ce périmètre sans demande.
- Suivre les Conventional Commits, habituellement en français, sauf message
  explicitement demandé par l’utilisateur.
