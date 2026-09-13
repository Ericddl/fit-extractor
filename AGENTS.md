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
- `file_manager.py` : chemins, nommage, collisions et archivage des sources.
- `gpx_exporter.py` : filtrage GPS et génération XML avec `xml.etree.ElementTree`.
- Python 3.10+ ; seule dépendance externe : `fitparse>=1.2.0` dans `requirements.txt`.
  Privilégier la bibliothèque standard ; justifier toute nouvelle dépendance.

Flux : lecture → décompression en mémoire → parsing → Markdown → GPX éventuel
→ déplacement du FIT source. Les dossiers `import/` et `export/` sont ancrés à
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
.venv/bin/python -B extractor.py mon_activite.fit --stdout --gps --gps-limit 30
.venv/bin/python extractor.py mon_activite.fit
```

- Un nom seul est recherché d’abord tel quel, puis dans `import/`.
- La conversion normale écrit dans `export/` et **déplace la source**.
- `--stdout` ne génère pas d’export et ne déplace rien, mais peut créer les
  dossiers `import/` et `export/`. `-B` évite les caches Python.
- `--output chemin/seance.md` place aussi le GPX et la source archivée à côté.
- `--force` permet d’écraser le Markdown et le GPX. Une collision d’archive FIT
  entraîne un suffixe `_dupN`, pas un écrasement.
- `--gps` et `--gps-limit` concernent seulement le Markdown ; le GPX conserve
  toute la trace exploitable. Utiliser une limite strictement positive.

## Validation

Aucune suite de tests automatisés, CI ou configuration de lint n’est présente.
Le dossier `examples/` évoqué dans la spécification n’existe pas dans le dépôt.

- Vérifier l’aide CLI et le rendu `--stdout` sur un FIT approprié si disponible.
- Pour une évolution fonctionnelle, vérifier si possible Suunto et Garmin,
  une activité avec GPS et une sans GPS, ainsi que `.fit.gz` si concerné.
- Tester les écritures, collisions et déplacements uniquement sur des copies
  de données dans un emplacement de test ; `--stdout` ne valide pas ces étapes.
- Indiquer les commandes exécutées et les limites de validation ; ne pas
  présenter l’affichage de l’aide comme un test complet de conversion.

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
- Décompresser uniquement en mémoire ; préserver l’extension composée `.fit.gz`
  à l’archivage (`name.lower().endswith(".fit.gz")`).
- Ne déplacer la source qu’après succès des écritures précédentes ; préserver
  les protections contre l’écrasement. Les sorties ne sont pas transactionnelles :
  un échec GPX peut laisser un Markdown déjà écrit.
- GPX : latitude/longitude valides, altitude et heure si disponibles ; pas
  d’extensions FC, cadence ou puissance, ni de fichier sans points exploitables.
- Ne jamais versionner les données sportives personnelles. `import/`, `export/`
  et les formats d’activité sont ignorés ; seuls leurs `.gitkeep` sont suivis.
- Limites actuelles : une activité par appel, multisession non gérée, validation
  indoor limitée ; ne pas élargir ce périmètre sans demande.
- Suivre les Conventional Commits, habituellement en français, sauf message
  explicitement demandé par l’utilisateur.
