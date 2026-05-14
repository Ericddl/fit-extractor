# fit-extractor

Convertit un fichier `.fit` (Suunto Spartan Ultra, Garmin Edge) en Markdown dense, prêt à coller dans ChatGPT ou Claude pour du coaching sportif.

## Installation

```bash
pip install -r requirements.txt
```

Python 3.10+ requis. Dépendance unique : `fitparse`.

## Workflow

Le projet s'articule autour de deux dossiers à la racine :

```
fit-extractor/
├── import/     ← déposer ici les .fit / .fit.gz à traiter
└── export/     ← reçoit le .md généré + le .fit archivé renommé
```

Les deux dossiers sont créés automatiquement au premier lancement.

Après traitement d'un fichier `.fit` :

1. le `.md` est généré dans `export/`,
2. un `.gpx` (trace GPS complète, GPX 1.1) est généré dans `export/` si le FIT contient des points GPS exploitables,
3. le `.fit` source est déplacé dans `export/`,
4. les trois fichiers partagent le même basename `YYYY-MM-DD_<activité>_<indice>` (ex. `2026-05-14_trail_001.md` + `2026-05-14_trail_001.gpx` + `2026-05-14_trail_001.fit`).

Une activité sans GPS (intérieur, home trainer) ne produit que le `.md` ; un message explicite l'indique.

## Utilisation

```bash
python3 extractor.py <fichier.fit>
```

Un nom seul est résolu depuis `import/` : `python3 extractor.py Trail_le_matin.fit` cherche `import/Trail_le_matin.fit`.

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
# → Markdown généré : export/2026-05-14_trail_001.md
# → GPX généré : export/2026-05-14_trail_001.gpx (10284 points)
# → Archive FIT : export/2026-05-14_trail_001.fit

# Copier-coller direct dans ChatGPT (rien n'est écrit, .fit reste dans import/)
python3 extractor.py Trail_le_matin.fit --stdout | pbcopy

# Avec points GPS (jusqu'à 50)
python3 extractor.py Trail_le_matin.fit --gps --gps-limit 50

# Chemin de sortie personnalisé : le .md va à l'emplacement demandé,
# et le .fit est déplacé à côté avec le même basename
python3 extractor.py Trail_le_matin.fit --output activites/trail.md --force
```

Les fichiers `.fit.gz` sont décompressés en mémoire (jamais sur disque) et conservent leur extension `.fit.gz` lors de l'archivage.

## Sections générées

Les sections n'apparaissent que si les données sont disponibles :

- **Résumé général** : distance, durée, FC, dénivelé, calories, allure/VAM, TSS, TE…
- **Zones d'entraînement** : temps en zones FC + aérobie/anaérobie
- **Métriques avancées (Suunto)** : récupération, EPOC, ressenti, seuil aérobie…
- **HRV** : RMSSD et SDNN calculés depuis les intervalles RR (Suunto uniquement)
- **Profil utilisateur** (Garmin) : âge, poids, FC repos…
- **Zones cibles** (Garmin) : FTP, seuil FC
- **Tours / Laps** : tableau par lap
- **Points GPS** (Markdown échantillonné) : uniquement avec `--gps`. Le `.gpx` produit en parallèle contient toujours la trace complète.

Tous les labels sont en français. La spec technique complète est dans `docs/SPEC.md`.
