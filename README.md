# fit-extractor

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

CLI Python qui convertit un fichier `.fit` (montre Suunto, compteur Garmin) en **Markdown dense**, prêt à coller dans ChatGPT ou Claude pour de l'analyse et du coaching sportif — plus un **fichier GPX 1.1** de la trace complète.

Une séance de trail de 1h30 (11 000 intervalles RR, 5 500 points GPS) tient en ~2 Ko de Markdown lisible : tout ce qu'une IA a besoin de savoir, rien qui sature son contexte.

```
import/Trail_le_matin.fit
        │
        ▼
export/2026-05-14_running_trail_001.md    ← Markdown pour l'IA
export/2026-05-14_running_trail_001.gpx   ← trace GPS complète
export/2026-05-14_running_trail_001.fit   ← source archivée
```

## Pourquoi

Les fichiers `.fit` sont binaires et illisibles. Les exports CSV classiques crachent des dizaines de milliers de lignes — inexploitable par une IA. `fit-extractor` fait le tri : il agrège les séries temporelles en métriques utiles (RMSSD/SDNN plutôt que 11 000 intervalles RR bruts), garde tout ce qui est signifiant pour l'entraînement, et écarte le reste.

## Installation

```bash
git clone https://github.com/Ericddl/fit-extractor.git
cd fit-extractor
pip install -r requirements.txt
```

Python 3.10+ requis. Dépendance unique : [`fitparse`](https://github.com/dtcooper/python-fitparse). Le GPX est généré avec la bibliothèque standard, sans dépendance supplémentaire.

## Démarrage rapide

```bash
# 1. Déposer le .fit dans import/  (le dossier est créé au premier lancement)
cp ~/Downloads/Trail_le_matin.fit import/

# 2. Convertir
python3 extractor.py Trail_le_matin.fit
```

```
→ Markdown généré : export/2026-05-14_running_trail_001.md
→ GPX généré : export/2026-05-14_running_trail_001.gpx (5596 points)
→ Archive FIT : export/2026-05-14_running_trail_001.fit
```

Il ne reste qu'à coller le contenu du `.md` dans ChatGPT ou Claude.

## Workflow

Le projet s'articule autour de deux dossiers à la racine, créés automatiquement :

```
fit-extractor/
├── import/     ← déposer ici les .fit / .fit.gz à traiter
└── export/     ← reçoit le .md + le .gpx + le .fit archivé renommé
```

Après traitement d'un fichier `.fit` :

1. le `.md` est généré dans `export/` ;
2. un `.gpx` (trace GPS complète, GPX 1.1) est généré dans `export/` si le FIT contient des points GPS exploitables ;
3. le `.fit` source est déplacé dans `export/` — uniquement après écriture réussie du `.md` ;
4. les trois fichiers partagent le même basename `YYYY-MM-DD_<activité>_<indice>`.

Une activité sans GPS (intérieur, home trainer) ne produit que le `.md` ; un message explicite l'indique. Les fichiers `.fit.gz` sont décompressés **en mémoire uniquement** (jamais sur disque) et conservent leur extension `.fit.gz` à l'archivage.

## Utilisation

```bash
python3 extractor.py <fichier.fit> [options]
```

Un nom seul est résolu depuis `import/` : `python3 extractor.py Trail_le_matin.fit` cherche `import/Trail_le_matin.fit`. Un chemin explicite (`./ailleurs/course.fit`) est utilisé tel quel.

### Options

| Option | Effet |
|--------|-------|
| `--output PATH` | Chemin du `.md` de sortie (court-circuite le nommage auto ; `.gpx` et `.fit` sont déposés à côté avec le même basename) |
| `--stdout` | Affiche le Markdown dans le terminal ; **aucun fichier écrit, ni `.gpx` ni déplacement du `.fit`** |
| `--gps` | Ajoute une section GPS échantillonnée dans le Markdown (n'affecte pas le `.gpx`) |
| `--gps-limit N` | Nombre max de points GPS dans le Markdown (défaut : 30). Le `.gpx` contient toujours la trace complète. |
| `--force` | Avec `--output`, autorise l'écrasement du `.md` et du `.gpx` cibles |

En mode auto (sans `--output`), l'indice s'incrémente automatiquement si un fichier (`.md`, `.fit`, `.fit.gz` ou `.gpx`) existe déjà avec la même date et le même type d'activité : pas besoin de `--force`.

### Exemples

```bash
# Conversion simple (lit import/Trail_le_matin.fit, écrit .md + .gpx dans export/)
python3 extractor.py Trail_le_matin.fit

# Copier-coller direct dans ChatGPT (rien n'est écrit, le .fit reste dans import/)
python3 extractor.py Trail_le_matin.fit --stdout | xclip -selection clipboard   # Linux
python3 extractor.py Trail_le_matin.fit --stdout | pbcopy                       # macOS

# Avec points GPS dans le Markdown (jusqu'à 50)
python3 extractor.py Trail_le_matin.fit --gps --gps-limit 50

# Chemin de sortie personnalisé : le .md va à l'emplacement demandé,
# et le .fit est déplacé à côté avec le même basename
python3 extractor.py Trail_le_matin.fit --output activites/trail.md --force
```

## Aperçu de la sortie

```markdown
# Activité — running (trail) — 2026-05-14 08:34
**Matériel** : Suunto Spartan Ultra (suunto)

---

## Résumé général
| Métrique | Valeur |
|----------|--------|
| Distance | 8.98 km |
| Durée totale | 01:33:16 |
| Dénivelé + | 426 m |
| Allure moyenne | 10:23 /km |
| FC moyenne | 136 bpm |
| Training Stress Score | 83.2 TSS |

---

## HRV
| Métrique | Valeur |
|----------|--------|
| RMSSD | 237.9 ms |
| SDNN | 189.5 ms |
| Nb intervalles RR | 11302 |

---

## Tours / Laps
| # | Distance | Durée | FC moy | FC max | Vitesse | Dénivelé+ | Temp. |
|---|----------|-------|--------|--------|---------|-----------|-------|
| 1 | 3.36 km | 00:30:15 | 133 bpm | 163 bpm | 6.7 km/h | 92 m | 16 °C |
```

## Sections générées

Les sections n'apparaissent que si les données correspondantes existent dans le FIT :

- **Résumé général** : distance, durée, FC, dénivelé, calories, allure/VAM, TSS, TE…
- **Zones d'entraînement** : temps en zones FC + aérobie/anaérobie
- **Métriques avancées (Suunto)** : récupération, EPOC, ressenti, seuil aérobie…
- **HRV** : RMSSD et SDNN calculés depuis les intervalles RR (Suunto uniquement)
- **Profil utilisateur** (Garmin) : âge, poids, FC repos…
- **Zones cibles** (Garmin) : FTP, seuil FC
- **Tours / Laps** : tableau par lap
- **Points GPS** (Markdown échantillonné) : uniquement avec `--gps`

Tous les labels sont en français.

### Compatibilité matérielle

| Section | Suunto Spartan Ultra | Garmin Edge |
|---|:---:|:---:|
| HRV (RMSSD/SDNN) | ✓ | — |
| Champs développeur (ressenti, récupération, EPOC…) | ✓ | — |
| Cadence course / foulées | ✓ | — |
| Profil utilisateur (âge, poids, FC repos/max) | — | ✓ |
| Zones cibles (FTP, seuil FC) | — | ✓ |
| VAM | — | ✓ |

L'extraction est **générique** : elle itère sur tous les champs de chaque message FIT plutôt que sur une liste figée. D'autres montres et compteurs produisent donc une sortie exploitable, même si les sections spécifiques ci-dessus ne s'activent pas.

## Architecture

Trois modules, sans framework :

| Module | Rôle |
|---|---|
| [`extractor.py`](extractor.py) | Parsing FIT, calcul HRV, formatage Markdown, CLI |
| [`file_manager.py`](file_manager.py) | Chemins, nommage `YYYY-MM-DD_<activité>_<indice>`, archivage du `.fit` |
| [`gpx_exporter.py`](gpx_exporter.py) | Extraction des points GPS, génération du GPX 1.1 (`xml.etree.ElementTree`) |

## Documentation

| Document | Contenu |
|---|---|
| [`docs/SPEC.md`](docs/SPEC.md) | Spécification technique complète : schéma de sortie, rationale des décisions, limitations connues |
| [`docs/file_manager_change.md`](docs/file_manager_change.md) | Spec de l'évolution « dossiers `import/` → `export/` » |
| [`docs/gpx.md`](docs/gpx.md) | Spec de l'évolution « export GPX » |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | Comment contribuer, invariants à respecter |
| [`CLAUDE.md`](CLAUDE.md) | Contexte destiné aux assistants de code (Claude Code) |

## Vie privée

Vos données d'entraînement ne quittent jamais votre machine : le traitement est 100 % local, sans appel réseau. Les dossiers `import/` et `export/` sont exclus du dépôt par `.gitignore`, ainsi que tout fichier `.fit`, `.gpx` ou `.tcx` où qu'il se trouve dans l'arborescence.

Attention en revanche à ce que vous collez ensuite dans une IA : un fichier GPX contient vos coordonnées GPS précises, domicile compris.

## Licence

[MIT](LICENSE).

Projet indépendant, sans aucun lien avec Suunto, Garmin, OpenAI ou Anthropic. « FIT » est un format défini par Garmin ; les marques citées appartiennent à leurs détenteurs respectifs.
