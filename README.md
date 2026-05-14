# fit-extractor

Convertit un fichier `.fit` (Suunto Spartan Ultra, Garmin Edge) en Markdown dense, prêt à coller dans ChatGPT ou Claude pour du coaching sportif.

## Installation

```bash
pip install -r requirements.txt
```

Python 3.10+ requis. Dépendance unique : `fitparse`.

## Utilisation

```bash
python3 extractor.py <fichier.fit>
```

Génère `<fichier>.md` dans le même dossier que l'input.

### Options

| Option | Effet |
|--------|-------|
| `--output PATH` | Chemin du `.md` de sortie (défaut : à côté du `.fit`) |
| `--stdout` | Affiche le Markdown dans le terminal au lieu d'écrire un fichier |
| `--gps` | Ajoute une section avec les points GPS échantillonnés |
| `--gps-limit N` | Nombre max de points GPS à inclure (défaut : 30) |
| `--force` | Écrase le fichier `.md` existant |

### Exemples

```bash
# Conversion simple
python3 extractor.py import/Trail_le_matin.fit

# Copier-coller direct dans ChatGPT
python3 extractor.py import/Trail_le_matin.fit --stdout | pbcopy

# Avec points GPS (jusqu'à 50)
python3 extractor.py import/Trail_le_matin.fit --gps --gps-limit 50

# Chemin de sortie personnalisé, écrasement autorisé
python3 extractor.py import/Trail_le_matin.fit --output activites/trail.md --force
```

Les fichiers `.fit.gz` sont décompressés à la volée — pas besoin de les extraire au préalable.

## Sections générées

Les sections n'apparaissent que si les données sont disponibles :

- **Résumé général** : distance, durée, FC, dénivelé, calories, allure/VAM, TSS, TE…
- **Zones d'entraînement** : temps en zones FC + aérobie/anaérobie
- **Métriques avancées (Suunto)** : récupération, EPOC, ressenti, seuil aérobie…
- **HRV** : RMSSD et SDNN calculés depuis les intervalles RR (Suunto uniquement)
- **Profil utilisateur** (Garmin) : âge, poids, FC repos…
- **Zones cibles** (Garmin) : FTP, seuil FC
- **Tours / Laps** : tableau par lap
- **Points GPS** : uniquement avec `--gps`

Tous les labels sont en français. La spec technique complète est dans `docs/SPEC.md`.
