# fit-extractor

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

CLI Python qui convertit un fichier `.fit` (montre Suunto, compteur Garmin) en **Markdown dense**, prêt à coller dans ChatGPT ou Claude pour de l'analyse et du coaching sportif — plus un **fichier GPX 1.1** de la trace complète.

Les séries brutes sont remplacées par des résumés et des tableaux : allures adaptées
au sport, kilomètres, terrain et qualité de l’enregistrement. La taille du Markdown
dépend notamment du nombre de tours et de kilomètres, sans dérouler les intervalles RR.

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
3. le `.fit` source est archivé dans `export/`, puis supprimé de son emplacement initial uniquement après publication réussie de toutes les sorties ;
4. les trois fichiers partagent le basename `YYYY-MM-DD_<activité>_<indice>`, sauf suffixe `_dupN` sur une archive en conflit.

Une activité sans GPS (intérieur, home trainer) ne produit que le `.md` ; un message explicite l'indique. Les fichiers `.fit.gz` sont décompressés **en mémoire uniquement** (jamais sur disque) et conservent leur extension `.fit.gz` à l'archivage.

Les contenus sont préparés avant publication. En cas d’erreur d’écriture ou d’archivage,
les nouveaux fichiers sont retirés et les sorties remplacées sont restaurées ; la source
reste à sa place. Si la restauration échoue elle-même, le message indique les fichiers
concernés et le dossier `.fit-export-*` contenant les sauvegardes à récupérer.
Les dossiers créés peuvent rester présents après un échec. Cette protection concerne
les erreurs gérées pendant une exécution isolée, pas une coupure électrique, un arrêt
forcé ou des conversions concurrentes vers les mêmes destinations.

## Utilisation

```bash
python3 extractor.py <fichier.fit> [options]
```

Un nom seul est recherché d’abord tel quel, puis dans `import/`. Un chemin explicite (`./ailleurs/course.fit`) est utilisé tel quel.

### Options

| Option | Effet |
|--------|-------|
| `--output PATH` | Chemin du `.md` de sortie (court-circuite le nommage auto ; `.gpx` et `.fit` sont déposés à côté avec le même basename) |
| `--stdout` | Affiche le Markdown ; **aucun export, déplacement ni création de dossier** |
| `--details` | Ajoute les champs complémentaires et les synthèses des mesures enregistrées |
| `--gps` | Ajoute une section GPS échantillonnée dans le Markdown (n'affecte pas le `.gpx`) |
| `--gps-limit N` | Entier strictement positif, défaut : 30. Limite seulement les points GPS du Markdown. |
| `--force` | Avec `--output`, autorise l'écrasement du `.md` et du `.gpx` cibles |

En mode auto (sans `--output`), l'indice s'incrémente automatiquement si un fichier (`.md`, `.fit`, `.fit.gz` ou `.gpx`) existe déjà avec la même date et le même type d'activité : pas besoin de `--force`.

Avec `--output --force`, un ancien GPX associé est retiré si la nouvelle activité
n’a pas de GPS. Une archive existante n’est jamais écrasée : la nouvelle reçoit
`_dupN`. Une source déjà à sa destination d’archive reste en place. Les sorties qui
désignent la source, se confondent entre elles ou sont des liens symboliques sont refusées.

Codes de sortie : **0** succès, **1** erreur de lecture, rendu ou export, **2** arguments
invalides. `--gps-limit 0` est refusé même sans `--gps`, avant toute lecture du FIT.

### Exemples

```bash
# Conversion simple (lit import/Trail_le_matin.fit, écrit .md + .gpx dans export/)
python3 extractor.py Trail_le_matin.fit

# Copier-coller direct dans ChatGPT (rien n'est écrit, le .fit reste dans import/)
python3 extractor.py Trail_le_matin.fit --stdout | xclip -selection clipboard   # Linux
python3 extractor.py Trail_le_matin.fit --stdout | pbcopy                       # macOS

# Avec points GPS dans le Markdown (jusqu'à 50)
python3 extractor.py Trail_le_matin.fit --gps --gps-limit 50

# Champs complémentaires et synthèses, sans export ni cache Python
python3 -B extractor.py Trail_le_matin.fit --stdout --details

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
| # | Distance | Durée | FC moy | FC max | Allure | Dénivelé+ | Temp. |
|---|----------|-------|--------|--------|---------|-----------|-------|
| 1 | 3.36 km | 00:30:15 | 133 bpm | 163 bpm | 9:00 /km | 92 m | 16 °C |
```

## Sections générées

Les sections n'apparaissent que si les données correspondantes existent dans le FIT :

- **Résumé général** : distance, durée, FC, dénivelé, calories, allure/VAM, TSS, TE…
- **Graphiques de la séance** : altitude, cardio et vitesse/allure en Unicode, après le résumé
- **Zones d'entraînement** : temps et pourcentages en zones FC, catégories aérobie/anaérobie séparées
- **Métriques avancées (Suunto)** : récupération, EPOC, ressenti, seuil aérobie…
- **HRV** : RMSSD et SDNN calculés depuis les intervalles RR (Suunto uniquement)
- **Profil utilisateur** (Garmin) : âge, poids, FC repos…
- **Zones cibles** (Garmin) : FTP, seuil FC
- **Tours / Laps** : tableau par lap
- **Découpage kilométrique** : course et trail, avec allure, FC et dénivelé estimé
- **Répartition du terrain** : montée/plat/descente en course, trail et vélo
- **Qualité de l’enregistrement** : couverture FC/GPS/altitude, interruptions et données manquantes
- **Points GPS** (Markdown échantillonné) : uniquement avec `--gps`

Tous les labels sont en français.

### Présentation adaptée au sport

Le résumé et les tours affichent des min/km en course et trail, des min/100 m
en natation, et des km/h en vélo ou pour les autres sports. Le choix dépend du
sport, pas de la marque. L’allure utilise distance et durée chronométrée si elles
sont positives, sinon la vitesse moyenne FIT disponible.

La durée chronométrée est distinguée de la durée totale. Leur différence est
affichée comme **temps hors chronomètre**, pas comme une mesure de tous les arrêts.
Les pourcentages FC utilisent la somme des durées de zones valides, sans inventer
de seuils cardiaques. Les catégories aérobie/anaérobie ne participent pas à cette somme.

En natation, le type de nage, les cycles et la cadence sont affichés si disponibles,
sans conversion cycles/bras ni calcul de SWOLF. Le Training Effect anaérobie est
repris lorsqu’il est fourni. La VAM est présentée en m/h. Les altitudes minimale
et maximale privilégient les champs de séance `enhanced_*`, puis standards ;
le repli sur les records est signalé dans le libellé.

### Analyses de parcours par défaut

Ces analyses sont incluses sans `--details` lorsqu’elles sont calculables :

- **Kilomètres** : limites interpolées dans la distance cumulée FIT, y compris le
  dernier segment plus court. La durée enregistrée, issue des horodatages, peut
  inclure des arrêts. Les kilomètres traversant une interruption restent marqués
  incomplets, sans allure calculée ; une régression de temps ou de distance rend
  le tableau indisponible. Aucun recalcul de distance depuis le GPS.
- **Terrain** : altitude filtrée par médiane glissante de cinq points, puis pente
  estimée sur des tronçons de 50 m. Montée au-dessus de +3 %, descente sous −3 %,
  plat entre ces seuils. Les portions interrompues, trop courtes ou sans altitude
  sont exclues ; la distance effectivement analysée est indiquée.
- **Qualité** : proportions des records avec FC strictement positive, coordonnées
  GPS valides et altitude finie ; horodatages manquants ou non croissants, distances
  invalides ou régressives. Une interruption est un écart supérieur au maximum de
  10 secondes et de cinq fois l’intervalle médian positif, sans présumer sa cause.

Les FC des tableaux kilométriques et de terrain sont pondérées par le temps des
intervalles où les deux mesures FC sont présentes. Le dénivelé calculé est une
**estimation**, distincte du total fourni par l’appareil. Une section indisponible
est expliquée dans la qualité ; l’absence de GPS n’empêche pas ces calculs si les
distances et horodatages sont disponibles.

### Graphiques Unicode

La section « Graphiques de la séance » est incluse par défaut, aussi avec
`--stdout`. Elle affiche trois tracés de 60 caractères dans des blocs de code :
altitude selon la distance FIT, cardio et vitesse/allure selon le temps enregistré.
Les repères indiquent le début, le milieu et la fin de chaque axe.

Les caractères `▁▂▃▄▅▆▇█` utilisent une échelle propre à chaque graphique, dont les
bornes décrivent les valeurs tracées, pas les extrema bruts de la séance.
Une barre haute signifie plus haut en altitude, plus élevé en cardio, ou **plus
rapide** pour vitesse/allure. Les allures sont affichées en min/km en course,
min/100 m en natation ; les autres sports utilisent des km/h.

L’échantillonnage est régulier, avec interpolation entre records consécutifs
valides seulement. Les interruptions et mesures absentes restent des espaces ;
`·` signifie une vitesse nulle sur un graphique d’allure. Une série constante est
signalée et dessinée à hauteur intermédiaire. Une série inexploitable est expliquée
à la place du tracé. Cardio et vitesse n’exigent ni GPS ni distance.

Ces aperçus peuvent manquer un pic bref entre deux positions échantillonnées.
Ils ne changent ni le GPX ni les calculs sportifs ; `--gps-limit` ne les limite pas.
L’alignement dépend du support Unicode et de la police monospace du lecteur Markdown.

### Mode détaillé

`--details` conserve le résumé habituel et ajoute, si disponibles, les champs de
séance et de tours non déjà affichés, les informations complémentaires du matériel,
et une synthèse des séries de mesures (puissance, cadence, métriques Suunto, etc.).
Les tableaux indiquent le nom technique FIT et l’unité renvoyée par le parsing.

Les séries numériques sont résumées par effectif, minimum, maximum et moyenne
arithmétique des échantillons valides, **non pondérée par le temps**. Les valeurs
textuelles ou structurées sont seulement comptées. Booléens, valeurs non finies,
coordonnées, horodatages et RR bruts sont exclus de ces synthèses. Les listes de
plus de 16 éléments dans les champs complémentaires sont résumées, pas déroulées.
Les variantes standard/enhanced ne sont pas répétées.

### Compatibilité matérielle

| Section | Suunto Spartan Ultra | Garmin Edge |
|---|:---:|:---:|
| HRV (RMSSD/SDNN) | ✓ | — |
| Champs développeur (ressenti, récupération, EPOC…) | ✓ | — |
| Cadence course / foulées | ✓ | — |
| Profil utilisateur (âge, poids, FC repos/max) | — | ✓ |
| Zones cibles (FTP, seuil FC) | — | ✓ |
| VAM | — | ✓ |

L'extraction des champs est **générique dans les types de messages traités** :
`session`, `lap`, `record`, `hrv`, `device_info`, `user_profile`, `zones_target`.
Le rendu standard sélectionne les métriques affichées ; `--details` complète cette
restitution sans exporter toutes les données brutes. La compatibilité avec d’autres
matériels dépend des messages disponibles et du support de `fitparse`.

## Architecture

Quatre modules, sans framework :

| Module | Rôle |
|---|---|
| [`extractor.py`](extractor.py) | Parsing FIT, calcul HRV, formatage Markdown, CLI |
| [`activity_analysis.py`](activity_analysis.py) | Calculs purs : unités, allures, kilomètres, terrain et qualité |
| [`file_manager.py`](file_manager.py) | Chemins, nommage `YYYY-MM-DD_<activité>_<indice>`, archivage du `.fit` |
| [`gpx_exporter.py`](gpx_exporter.py) | Extraction des points GPS, génération du GPX 1.1 (`xml.etree.ElementTree`) |

## Documentation

| Document | Contenu |
|---|---|
| [`docs/SPEC.md`](docs/SPEC.md) | Spécification technique complète : schéma de sortie, rationale des décisions, limitations connues |
| [`docs/file_manager_change.md`](docs/file_manager_change.md) | Spec de l'évolution « dossiers `import/` → `export/` » |
| [`docs/gpx.md`](docs/gpx.md) | Spec de l'évolution « export GPX » |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | Comment contribuer, invariants à respecter |
| [`AGENTS.md`](AGENTS.md) | Instructions et référence pour Codex |
| [`CLAUDE.md`](CLAUDE.md) | Contexte destiné aux assistants de code (Claude Code) |

## Vie privée

Vos données d'entraînement ne quittent jamais votre machine : le traitement est 100 % local, sans appel réseau. Les dossiers `import/` et `export/` sont exclus du dépôt par `.gitignore`, ainsi que tout fichier `.fit`, `.gpx` ou `.tcx` où qu'il se trouve dans l'arborescence.

Attention en revanche à ce que vous collez ensuite dans une IA : un fichier GPX contient vos coordonnées GPS précises, domicile compris.

## Licence

[MIT](LICENSE).

Projet indépendant, sans aucun lien avec Suunto, Garmin, OpenAI ou Anthropic. « FIT » est un format défini par Garmin ; les marques citées appartiennent à leurs détenteurs respectifs.
