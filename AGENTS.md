# Instructions pour Codex

## Projet et références

`fit-extractor` convertit une activité `.fit` ou `.fit.gz` en Markdown dense pour
le coaching sportif par IA, et en GPX 1.1 si des coordonnées sont disponibles.
Le traitement est local, sans appel réseau ni API d’IA.

- `README.md` : installation et usage ; `CONTRIBUTING.md` : contributions.
- `docs/SPEC.md` : spécification principale, décisions et limites connues.
- `docs/file_manager_change.md` et `docs/gpx.md` : spécifications historiques,
  dont certaines propositions diffèrent du code livré.
- `CLAUDE.md` : contexte complémentaire ; `docs/SPEC_template.md` : modèle de document.
- Vérifier le code avant de tenir un comportement documentaire pour acquis.

## Architecture et dépendances

- `extractor.py` : CLI `argparse`, parsing FIT, calcul HRV et rendu Markdown.
- `activity_analysis.py` : calculs purs d’allure, kilomètres, terrain et qualité, sans accès disque.
- Les séries des graphiques Unicode sont échantillonnées dans `activity_analysis.py` ;
  leur rendu reste dans `extractor.py`.
- `file_manager.py` : chemins, nommage, collisions et archivage des sources.
- `gpx_exporter.py` : filtrage GPS et génération XML avec `xml.etree.ElementTree`.
- Python 3.10+ ; seule dépendance externe : `fitparse>=1.2.0` dans `requirements.txt`.
  Privilégier la bibliothèque standard ; justifier toute nouvelle dépendance.

Flux : lecture → décompression en mémoire → parsing → rendu Markdown/GPX en mémoire
→ préparation des fichiers → publication et archivage avec restauration sur erreur.
Les dossiers `import/` et `export/` sont ancrés à
la racine du projet, indépendamment du répertoire courant.
Nommage automatique : `YYYY-MM-DD_<activité>_<indice>`, avec indice incrémenté
en tenant compte des fichiers `.md`, `.fit`, `.fit.gz` et `.gpx` existants.

## Commandes

Depuis la racine, utiliser le venv existant ou l’installer si nécessaire :

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -B extractor.py --help
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
- `--output chemin/seance.md` place aussi le GPX et la source archivée à côté.
- `--force` permet d’écraser le Markdown et le GPX. Une collision d’archive FIT
  entraîne un suffixe `_dupN`, pas un écrasement.
- Avec `--output --force`, retirer l’ancien GPX si l’activité n’a plus de GPS.
- `--gps` et `--gps-limit` concernent seulement le Markdown ; le GPX conserve
  toute la trace exploitable. Une limite non positive est refusée avant parsing.
- Codes de sortie : 0 succès, 1 erreur de traitement, 2 arguments invalides.
- Les analyses sportives sont affichées par défaut ; `--details` ajoute seulement
  les compléments techniques. Course : min/km ; natation : min/100 m ; vélo : km/h.
- Les graphiques Unicode sont inclus par défaut : altitude/distance, cardio/temps,
  vitesse ou allure/temps, sur 60 caractères et avec des échelles indépendantes.

## Validation

Aucune suite de tests automatisés, CI ou configuration de lint n’est présente.
Il n’y a ni dossier `examples/` ni jeu de FIT de test versionné.

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

## Conventions et précautions

- Garder les changements ciblés, les fonctions en `snake_case` et les
  responsabilités dans les modules indiqués. Mettre à jour la documentation
  concernée si le comportement ou la CLI change.
- Toujours utiliser `StandardUnitsDataProcessor()` ; respecter les unités
  renvoyées par champ et ne pas reconvertir les coordonnées déjà en degrés.
- Extraire les champs génériquement dans les messages traités, ignorer
  `unknown_XXX` et gérer les valeurs absentes sans faire échouer le rendu.
- Garder les titres et libellés utilisateur en français, les unités explicites
  et les sections facultatives conditionnées par les données disponibles.
- HRV : rendre RMSSD et SDNN, jamais les intervalles RR bruts.
- Les kilomètres et le terrain utilisent la distance FIT, pas une distance GPS
  reconstruite. Ne pas interpoler les interruptions ; signaler les analyses incomplètes.
- Terrain : médiane de cinq points par portion continue, tronçons de 50 m, seuils
  ±3 %, dénivelé estimé. Les FC de ces analyses sont pondérées par les durées valides,
  contrairement aux synthèses d’échantillons de `--details`.
- Ne pas confondre durée chronométrée, durée enregistrée et mouvement réel ; ne
  pas inventer de puissance, de SWOLF ou d’interprétation des champs propriétaires.
- Partager le seuil d’interruption entre analyses et graphiques ; ne pas tracer
  à travers les trous. En allure, plus haut = plus rapide ; `·` = vitesse nulle.
  Les bornes des graphiques concernent les valeurs tracées, pas les extrema bruts.
- Décompresser uniquement en mémoire ; préserver l’extension composée `.fit.gz`
  à l’archivage (`name.lower().endswith(".fit.gz")`).
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
