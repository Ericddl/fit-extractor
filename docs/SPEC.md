# 🧩 SPEC.md — Technical Living Spec — fit-extractor

> ⚠️ Document maintenu en rétro-spécification.
> Sert de **référence unique pour comprendre, modifier et faire évoluer le système**.
> Doit rester **simple, à jour et exploitable par une IA**.

---

## 0. Statut

| Champ | Valeur |
|-------|--------|
| Phase | Draft v2 + évolutions file_manager & gpx |
| Branch courante | `feature/gpx` |
| Dernière session IA | 2026-05-14 |
| Prochaine action | Valider la génération GPX sur les 3 fichiers de test réels (outdoor + indoor) |

---

## 1. Overview

**Project name** : `fit-extractor`
**Objective** : Extraire les données d'un fichier `.fit` (montre ou GPS vélo) et les convertir en Markdown structuré, **optimisé pour être envoyé à une IA (ChatGPT, Claude) pour du coaching sportif assisté**.
**Main stack** : Python 3.10+, `fitparse`, stdlib uniquement
**Last update** : 2026-05-13

### High-level behavior
- **Inputs** : un fichier `.fit` (ou `.fit.gz`) — Suunto Spartan Ultra (running/trail) ou GPS Garmin Edge (vélo)
- **Outputs** :
  - un fichier `.md` lisible par un humain et dense en informations pour une IA de coaching ;
  - un fichier `.gpx` 1.1 contenant la trace GPS complète (généré automatiquement si points GPS exploitables).
- **Core use case principal** : copier-coller le `.md` dans ChatGPT ou Claude pour obtenir une analyse de séance, des conseils d'entraînement, un suivi de charge
- **Core use cases secondaires** :
  - Extraction CLI simple : `python extractor.py mon_activite.fit`
  - Archivage personnel d'activités (vault Obsidian)
  - Visualisation cartographique de la trace via le `.gpx` dans un outil tiers

### Cible utilisateur
L'utilisateur colle le Markdown dans une IA de coaching. Le Markdown doit donc être :
- **Complet** : ne rien perdre d'utile (métriques physiologiques, zones, developer fields)
- **Lisible par une IA** : sections claires, labels explicites, unités systématiques
- **Sans bruit** : pas de champs `unknown_XXX`, pas de données GPS brutes sauf demande explicite
- **En français** : labels et titres de sections en français

---

## 2. Architecture

### Project structure
```
fit-extractor/
├── extractor.py          # Script principal, point d'entrée CLI
├── file_manager.py       # Résolution des chemins, nommage, déplacement
├── gpx_exporter.py       # Extraction des points GPS et génération du GPX 1.1
├── requirements.txt      # fitparse uniquement
├── docs/SPEC.md          # Ce document
├── README.md             # Usage rapide
├── import/               # Fichiers .fit / .fit.gz à traiter (créé automatiquement)
│   └── .gitkeep
├── export/               # .md générés + .fit archivés (créé automatiquement)
│   └── .gitkeep
└── examples/
    ├── trail.fit         # Fichier de test Suunto running/trail
    ├── velo.fit          # Fichier de test Garmin vélo
    └── course.fit        # Fichier de test Suunto course à pied
```

### Data flow
```
import/fichier.fit (.gz)
  → résolution du chemin (depuis import/ si nom nu)
  → décompression en mémoire si .gz (gzip stdlib)
  → parsing FitFile (fitparse + StandardUnitsDataProcessor)
  → extraction générique de TOUS les messages connus
      session / lap / record / hrv / device_info /
      user_profile / zones_target / developer_fields
  → détection du profil matériel (Suunto vs Garmin vs autre)
  → planification du basename normalisé
      YYYY-MM-DD_<activité>_<indice>
  → formatage Markdown conditionnel par sections
  → écriture export/<basename>.md
  → extraction des points GPS exploitables depuis les records
  → si points GPS présents : écriture export/<basename>.gpx (GPX 1.1)
  → déplacement de la source .fit / .fit.gz vers export/<basename>.<ext>
      (uniquement après succès de l'écriture .md)
```

---

## 3. Components

### `extractor.py`

- **Role** : Point d'entrée CLI — orchestration parsing / formatage / écriture / archivage
- **Files** : `extractor.py`
- **Public interface** :
  ```
  python extractor.py <input.fit> [--output chemin/sortie.md] [--gps] [--gps-limit N] [--stdout] [--force]
  ```
- **Dependencies** : `fitparse`, `gzip`, `pathlib`, `argparse`, `math`, `file_manager`
- **Side effects** :
  - crée les dossiers `import/` et `export/` s'ils n'existent pas
  - écrit le `.md` dans `export/` (ou à l'emplacement `--output`, ou stdout)
  - déplace le `.fit` source vers `export/` après succès (sauf `--stdout`)

### `gpx_exporter.py`

- **Role** : Extraire les points GPS exploitables et produire un fichier GPX 1.1 sans dépendance externe
- **Files** : `gpx_exporter.py`
- **Public interface** :
  ```python
  extract_gps_points(records: list[dict]) -> list[dict]
  has_gps_points(gps_points: list[dict]) -> bool
  format_gpx_time(dt: datetime) -> str
  build_gpx(gps_points, track_name, creator="fit-extractor") -> str
  write_gpx_file(gpx_content: str, output_path: Path, force: bool = False) -> None
  ```
- **Dependencies** : `xml.etree.ElementTree`, `datetime`, `pathlib` (stdlib uniquement)
- **Side effects** : `write_gpx_file` écrit le `.gpx` dans `export/` (ou à côté de `--output`)

### `file_manager.py`

- **Role** : Gérer les dossiers standards et la convention de nommage `YYYY-MM-DD_<activité>_<indice>`
- **Files** : `file_manager.py`
- **Public interface** :
  ```python
  ensure_workdirs() -> None
  sanitize_filename_part(text, fallback="activite") -> str
  resolve_input_path(user_arg: Path) -> Path
  resolve_activity_date(session: dict) -> date
  resolve_activity_name(session: dict) -> str
  next_available_index(directory, date_str, activity) -> int
  build_activity_basename(date, activity, index) -> str
  plan_output_paths(session, fallback_source) -> tuple[Path, str]
  move_processed_fit(source: Path, md_target: Path) -> Path
  ```
- **Dependencies** : `pathlib`, `shutil`, `unicodedata`, `re`, `datetime` (stdlib uniquement)
- **Side effects** :
  - `ensure_workdirs` : crée `import/` et `export/` si absents
  - `move_processed_fit` : déplace le fichier source via `shutil.move`

---

## 4. Core Logic (CRITICAL)

### Règles de parsing

- **`StandardUnitsDataProcessor()`** : à toujours passer à `FitFile()`. Convertit vitesses en km/h, distances en mètres, altitudes en mètres. **Obligatoire, ne jamais retirer.**
- **Semicircles → degrés** : avec `StandardUnitsDataProcessor`, la conversion des coordonnées GPS est automatique — ne pas la refaire manuellement.
- **Fichiers `.fit.gz`** : décompresser en mémoire (module `gzip`) avant parsing. Ne jamais écrire de `.fit` intermédiaire sur le disque.
- **Champs `None`** : très fréquents selon le matériel. Toujours tester `is not None`. Fallback `"-"` systématique dans le Markdown.
- **Champs `unknown_XXX`** : **ignorer complètement**. Champs propriétaires non documentés, sans valeur pour une IA de coaching.

### Extraction générique (pas de liste figée de champs)

Le script doit itérer sur **tous les champs présents** dans chaque message, pas sur une liste codée en dur. Cela garantit la compatibilité avec tout matériel futur.

```python
# Principe : extraction dynamique
for msg in fitfile.get_messages("session"):
    for field in msg:
        if field.value is not None and not field.name.startswith("unknown_"):
            data[field.name] = (field.value, field.units)
```

### Developer fields (Suunto)

Les developer fields sont des métriques propriétaires Suunto injectées dans le fichier FIT. Documentés via les messages `field_description`, ils contiennent des données à haute valeur pour le coaching :

| Field name | Description | Présent sur |
|------------|-------------|-------------|
| `recovery_time` | Temps de récupération estimé (s) | Trail + Course |
| `peak_epoc` | EPOC peak — dette O2 (l/kg) | Trail + Course |
| `cumulative_baseline` | Baseline de forme cumulée | Trail + Course |
| `aerobic_threshold` | Seuil aérobie (bpm) | Course |
| `aerobic_baseline` | Baseline aérobie | Course |
| `ddfa` | DFA alpha — variabilité cardiaque par point record | Trail + Course |
| `time_in_aerobic_zone` | Temps en zone aérobie (s) | Trail + Course |
| `time_in_anaerobic_zone` | Temps en zone anaérobie (s) | Trail + Course |
| `time_in_vo2max_zone` | Temps en zone VO2max (s) | Trail + Course |
| `feeling` | Ressenti subjectif post-activité (1-5) | Trail uniquement |

Ces champs doivent être extraits et affichés dans une section dédiée "Métriques avancées".

### HRV (Suunto uniquement)

Le message `hrv` contient les intervalles RR battement par battement (en secondes). Il peut contenir **10 000+ mesures** — ne jamais les inclure raw dans le Markdown. Calculer uniquement RMSSD et SDNN :

```python
import math
def compute_hrv(rr_intervals):
    # Filtrer les valeurs aberrantes (< 0.3s ou > 2.0s)
    rr = [t for t in rr_intervals if 0.3 <= t <= 2.0]
    if len(rr) < 2:
        return None, None
    diffs = [rr[i+1] - rr[i] for i in range(len(rr)-1)]
    rmssd = math.sqrt(sum(d**2 for d in diffs) / len(diffs)) * 1000  # ms
    sdnn = math.sqrt(sum((r - sum(rr)/len(rr))**2 for r in rr) / len(rr)) * 1000  # ms
    return round(rmssd, 1), round(sdnn, 1)
```

### Détection du profil matériel

Lire le champ `manufacturer` du premier message `device_info` :
- `"suunto"` → activer sections HRV + developer fields Suunto
- `"garmin"` → activer sections user_profile + zones_target
- autre → extraction générique sans sections spécifiques

### Calculs dérivés

- **Durée** : `total_elapsed_time` (s) → `HH:MM:SS` via `timedelta`
- **Allure running** : `60 / avg_speed` (km/h) → `MM:SS /km`
- **Temps de récupération** : `recovery_time` (s) → `Xh YYmin`
- **Zones FC** : `time_in_hr_zone` est un tuple `(z1, z2, z3, z4, z5)` en secondes → formater chaque zone

### Workflow import/ → export/

- **Résolution input** : un chemin absolu/relatif est utilisé tel quel ; un nom nu introuvable mais présent dans `import/` est résolu vers `import/<nom>`.
- **Date de l'activité** : priorité `session.start_time` → `session.timestamp` → `session.date` → `date.today()`. Toujours formaté `YYYY-MM-DD`.
- **Nom d'activité** : `sport` + `sub_sport` (si distinct, non générique) après sanitisation (NFD-strip accents, lowercase, `[a-z0-9_]` only). Fallback : nom du fichier source sanitisé, puis `activite`.
- **Indice** : scan de `export/` pour les fichiers `^{date}_{activity}_(\d{3})\.(md|fit|fit\.gz)$` ; on prend `max+1`, formaté sur 3 chiffres. Auto-incrément, pas de `--force` nécessaire.
- **Déplacement** : `shutil.move` de la source `.fit`/`.fit.gz` vers `export/<basename>.<ext>`. L'extension `.fit.gz` composée est détectée via `name.lower().endswith(".fit.gz")` (pas via `Path.suffix`). Garde-fou anti-race : suffixe `_dupN` si la destination existe déjà au moment du move.
- **Échec d'écriture .md** : exception levée avant l'étape de déplacement → la source reste intacte dans `import/`.
- **Échec de move** : warning stderr, le `.md` reste écrit dans `export/`, la source reste à sa place.

### Génération du GPX

- **Filtrage des points** : un record est conservé si `position_lat` et `position_long` sont présents, convertibles en float, et dans les plages valides (`-90 ≤ lat ≤ 90`, `-180 ≤ lon ≤ 180`). Avec `StandardUnitsDataProcessor`, ces valeurs sont déjà en degrés — pas de conversion semicircles manuelle.
- **Format** : GPX 1.1, namespace `http://www.topografix.com/GPX/1/1`, structure `<gpx>/<trk>/<trkseg>/<trkpt>`. La balise `<name>` du `<trk>` contient le basename complet (`YYYY-MM-DD_<activité>_<indice>`).
- **Champs par point** : `lat`/`lon` comme attributs, `<ele>` si altitude présente, `<time>` si timestamp présent (ISO 8601 UTC, suffixe `Z`).
- **Champs non exportés en V1** : fréquence cardiaque, vitesse, cadence, puissance, température, developer fields. Ces données restent dans le Markdown.
- **Pas de `--gps-limit`** sur le GPX : trace complète. `--gps`/`--gps-limit` n'affectent que la section GPS du Markdown.
- **Pas de fichier vide** : si aucun point exploitable, message stderr "Aucun point GPS exploitable trouvé : GPX non généré." et le traitement reste considéré comme réussi.
- **Collision** : en mode auto, la regex de `next_available_index` inclut `gpx` donc l'indice évite les collisions. En mode `--output`, `--force` autorise l'écrasement du `.gpx` (cohérent avec le `.md`).

---

## 5. Contracts & Interfaces

### CLI
```
python extractor.py <input>  [options]

Arguments :
  input                 Chemin vers le fichier .fit ou .fit.gz.
                        Un nom nu est résolu depuis import/ s'il y existe.

Options :
  --output PATH         Chemin du .md de sortie. Court-circuite le nommage auto.
                        Le .fit source est alors déplacé à côté de --output
                        avec le même basename (mais en .fit / .fit.gz).
                        Sans --output, le .md va dans
                        export/YYYY-MM-DD_<activité>_<indice>.md
                        et le .fit source est déplacé dans export/ avec le même basename.
  --stdout              Afficher le Markdown dans le terminal.
                        Aucun fichier écrit, le .fit n'est pas déplacé.
  --gps                 Inclure une section avec les points GPS échantillonnés
  --gps-limit N         Nombre max de points GPS à inclure (défaut : 30)
  --force               Avec --output, autorise l'écrasement d'un .md existant.
                        Sans --output, inutile : l'indice s'auto-incrémente.
                        Couvre également l'écrasement du .gpx en mode --output.
```

### Comportement par défaut du GPX

Un fichier `.gpx` est généré automatiquement à côté du `.md` (mode auto ou `--output`) dès que le FIT contient des points GPS exploitables. Aucune option `--gpx` / `--no-gpx` en V1.

- `--gps` et `--gps-limit` affectent uniquement la section GPS échantillonnée du Markdown.
- Le GPX contient toujours la trace complète, indépendamment de `--gps-limit`.
- `--stdout` désactive toute écriture, y compris du `.gpx`.

### Structure du Markdown produit

Chaque section est **conditionnelle** — elle n'apparaît que si les données sont disponibles.

```markdown
# Activité — {sport} ({sub_sport}) — {date}
**Matériel** : {product_name} ({manufacturer})

---

## Résumé général
| Métrique | Valeur |
|----------|--------|
| Distance | 14.52 km |
| Durée totale | 02:51:23 |
| Durée en mouvement | 02:51:22 |
| Dénivelé + | 626 m |
| Dénivelé - | 601 m |
| Vitesse moyenne | 5.1 km/h |
| Allure moyenne | 11:48 /km |        ← running uniquement
| FC moyenne | 120 bpm |
| FC max | 143 bpm |
| FC min | 66 bpm |
| Calories | 1781 kcal |
| Température moy. | 22 °C |
| Cadence moy. | 65 foulées/min |     ← running uniquement
| VAM | 0.1 m/s |                     ← vélo uniquement
| Training Stress Score | 115.8 TSS |
| Training Effect | 2.4 |

---

## Zones d'entraînement    ← si time_in_hr_zone disponible
| Zone | Durée |
|------|-------|
| Zone 1 | 00:35:59 |
| Zone 2 | 01:42:31 |
| Zone 3 | 00:32:52 |
| Aérobie | 02:37:53 |
| Anaérobie | 00:03:32 |

---

## Métriques avancées (Suunto)    ← si developer fields présents
| Métrique | Valeur |
|----------|--------|
| Temps de récupération | 21h 49min |
| EPOC peak | 26.8 l/kg |
| Baseline cumulative | -0.042 |
| Seuil aérobie | 124.5 bpm |
| Ressenti | 5/5 |
| Temps zone aérobie | 02:37:53 |
| Temps zone anaérobie | 00:03:32 |

---

## HRV    ← Suunto uniquement, si message hrv présent
| Métrique | Valeur |
|----------|--------|
| RMSSD | 42.3 ms |
| SDNN | 51.7 ms |
| Nb intervalles RR | 10284 |

---

## Profil utilisateur    ← Garmin uniquement, si user_profile présent
| Champ | Valeur |
|-------|--------|
| Âge | ... |
| Poids | ... kg |
| FC repos | ... bpm |
| FC max configurée | ... bpm |

---

## Zones cibles    ← Garmin uniquement, si zones_target présent
| Champ | Valeur |
|-------|--------|
| FTP | ... W |
| Seuil FC | ... bpm |

---

## Tours / Laps
| # | Distance | Durée | FC moy | FC max | Vitesse | Dénivelé+ | Temp. |
|---|----------|-------|--------|--------|---------|-----------|-------|
| 1 | 1.00 km | 11:48 | 118 bpm | 132 bpm | 5.1 km/h | 42 m | 22 °C |

---

## Points GPS    ← uniquement si --gps
| Temps | Lat | Long | Alt (m) | FC | Vitesse |
...

---
*Généré depuis `fichier.fit` — {N} points GPS — {product_name}*
```

---

## 6. Configuration

### Dossiers standards

| Dossier | Rôle |
|---------|------|
| `import/` | Fichiers `.fit` / `.fit.gz` à traiter — créé automatiquement |
| `export/` | `.md` + `.gpx` générés + `.fit` archivés sous `YYYY-MM-DD_<activité>_<indice>` — créé automatiquement |

Le `.gitignore` versionne la structure via `.gitkeep` mais ignore le contenu :

```
/import/*
/export/*
!/import/.gitkeep
!/export/.gitkeep
```

### Arguments CLI

| Argument | Usage | Défaut |
|----------|-------|--------|
| `input` | Chemin du `.fit` ou nom nu cherché dans `import/` | requis |
| `--output` | Chemin de sortie du `.md` ; `.fit` déplacé à côté avec même basename | `export/<basename>.md` auto |
| `--stdout` | Afficher dans le terminal, pas d'écriture, pas de déplacement | désactivé |
| `--gps` | Inclure les points GPS échantillonnés | désactivé |
| `--gps-limit` | Nb max de points GPS | 30 |
| `--force` | Avec `--output`, autorise l'écrasement du `.md` cible | désactivé |

---

## 7. Technical Decisions (ADR light)

| Décision | Pourquoi | Alternative rejetée |
|----------|----------|---------------------|
| `fitparse` seule dépendance externe | Légère, bien maintenue | `garmin-fit-sdk` (trop lourd) |
| Extraction générique (pas de liste figée) | Compatible tout matériel futur, découvert sur données réelles | Liste de champs codée en dur (casse dès nouveau matériel) |
| Ignorer les `unknown_XXX` | Pas de valeur pour une IA de coaching, bruit pur | Les inclure (illisible) |
| HRV résumé (RMSSD/SDNN) plutôt que raw | 10 000+ points = context overflow pour une IA | Export raw (inutilisable) |
| Sections conditionnelles | Suunto ≠ Garmin — forcer toutes les sections = sections vides | Template fixe |
| Labels en français | Cible utilisateur francophone, meilleure lisibilité dans ChatGPT | Anglais |
| `--stdout` disponible | Permet copier-coller direct sans fichier intermédiaire | Toujours fichier |
| Markdown pur (tableaux GFM) | Rendu parfait dans ChatGPT, Claude, Obsidian | JSON (moins lisible par humain) |
| `StandardUnitsDataProcessor` activé | Unités cohérentes, lisibles par une IA | Unités brutes (source d'erreurs) |
| Dossiers standards `import/` et `export/` | Sépare entrants/sortants, facilite l'archivage | Demander un chemin complet à chaque appel |
| Basename normalisé `YYYY-MM-DD_<activité>_<indice>` partagé `.md`/`.fit` | Lisible, triable, associe immédiatement source et résultat | Conserver le nom source ou un timestamp brut |
| Auto-incrément de l'indice depuis `export/` | Évite les collisions sans état persistant | Stocker un compteur local |
| Module `file_manager.py` dédié | Sépare les responsabilités I/O du parsing/formatage | Tout garder dans `extractor.py` |
| Pas de déplacement en mode `--stdout` | Évite un effet de bord sur un mode pensé pour copier-coller | Archiver systématiquement |
| Génération GPX automatique si points GPS présents | Répond au besoin principal sans option supplémentaire | Obliger un `--gpx` explicite |
| GPX 1.1 `<trk>`/`<trkseg>`/`<trkpt>` | Format standard, lu par tous les outils cartographiques | Format propriétaire ou JSON |
| Pas d'extensions FC/vitesse/cadence en V1 | Reste simple, standard, sans dépendance | Extensions Garmin/TrackPointExtension |
| Trace GPX complète (pas de `--gps-limit`) | La trace n'a de sens qu'entière | Échantillonner comme le Markdown |
| `xml.etree.ElementTree` (stdlib) | Pas de dépendance externe | Ajouter `gpxpy` |
| Pas de GPX vide | Évite les artefacts trompeurs | Créer un fichier sans trace |
| Module `gpx_exporter.py` dédié | Sépare la génération XML du parsing FIT | Tout garder dans `extractor.py` |

---

## 8. Patterns & Conventions

- **Naming** : snake_case, fonctions nommées par verbe (`parse_fit`, `format_markdown`, `compute_hrv`, `detect_device`)
- **Error handling** : `try/except` sur le parsing FIT avec message explicite ; champs manquants → `"-"`
- **Architecture** : fonctions séparées par responsabilité — `parse_fit()`, `detect_device()`, `compute_hrv()`, `format_markdown()`, `main()`
- **Filtrage** : tout champ dont le nom commence par `unknown_` est ignoré à l'extraction
- **Unités** : toujours afficher l'unité dans le Markdown (km, bpm, m, °C, ms, kcal, W...)

---

## 9. Invariants (VERY IMPORTANT)

- **Ne jamais écrire de fichier `.fit` intermédiaire** sur le disque
- **Toujours utiliser `StandardUnitsDataProcessor()`** — ne jamais retirer
- **Ne jamais inclure les champs `unknown_XXX`** dans le Markdown
- **Ne jamais inclure les intervalles HRV bruts** — uniquement RMSSD et SDNN calculés
- **Ne jamais écraser silencieusement un fichier `.md` existant** — auto-incrément par défaut, ou `--force` avec `--output`
- **Les champs `None` ne doivent jamais provoquer une exception** — fallback `"-"` systématique
- **Le Markdown doit rester lisible sans rendu** — tableaux GFM simples, pas de HTML
- **Un `.fit` traité avec succès ne reste pas dans `import/`** — sauf `--stdout`
- **Un `.fit` n'est jamais déplacé si la génération `.md` échoue** — la source reste intacte
- **Le `.fit` archivé et le `.md` généré partagent toujours le même basename**
- **Tout export automatique va dans `export/`** ; tout import automatique vient de `import/`
- **Les dossiers `import/` et `export/` sont créés automatiquement** si absents
- **Le nommage produit toujours des noms compatibles** avec la plupart des systèmes de fichiers (ASCII, `[a-z0-9_]`)
- **Le `.gpx` partage toujours le même basename** que le `.md` et le `.fit`
- **Le `.gpx` est toujours écrit dans `export/`** (ou à côté de `--output`)
- **Aucun `.gpx` vide n'est généré** — si aucun point GPS exploitable, pas de fichier
- **Le GPX ne contient que des points lat/lon valides** (numériques, dans les plages)
- **`--gps-limit` ne limite jamais le GPX** — uniquement la section GPS du Markdown
- **L'absence de GPS n'empêche pas la génération du Markdown** — message stderr explicite, traitement réussi
- **Aucune dépendance externe pour le GPX** — stdlib `xml.etree.ElementTree` uniquement
- **Les extensions propriétaires GPX (FC, vitesse, cadence)** sont hors périmètre V1

---

## 10. Out of Scope

- Pas de visualisation graphique (carte rendue, image de parcours)
- Pas d'export CSV/JSON/HTML — sorties limitées à Markdown et GPX
- Pas d'extensions GPX (FC, cadence, vitesse, puissance, TrackPointExtension Garmin/Strava/Suunto)
- Pas de simplification ou compression de trace GPX
- Pas de découpage du GPX en plusieurs segments en cas de pause ou perte GPS
- Pas de correction ni d'interpolation des points GPS manquants
- Pas d'import du GPX dans Strava/Garmin/Suunto/autre plateforme
- Pas d'envoi automatique à une IA (pas d'appel API ChatGPT/Claude depuis le script)
- Pas de traitement batch multi-fichiers (une seule activité par appel) — explicitement hors périmètre de l'évolution `file_manager`
- Pas de génération d'un index global des activités présentes dans `export/`
- Pas de suppression automatique des fichiers présents dans `export/`
- Pas d'interface GUI
- Pas de frontmatter YAML Obsidian/Dataview (à envisager en v2)

---

## 11. Known Issues & Tech Debt

- [ ] Pas de test sur activités indoor (natation, home trainer) — GPS absent, comportement à vérifier
- [ ] `feeling` (ressenti Suunto 1-5) : mapping valeur numérique → libellé non documenté
- [ ] Multi-session FIT (triathlon) : non géré — hypothèse 1 session par fichier
- [ ] Batch processing non prévu

---

## 12. Evolution History

| Date | Changement |
|------|------------|
| 2026-05-13 | Initialisation du projet et de la spec v1 |
| 2026-05-13 | v2 : analyse réelle de 3 fichiers FIT (Suunto Spartan Ultra + Garmin Edge). Refonte cible (coaching IA), extraction générique, HRV calculé, developer fields Suunto documentés, sections conditionnelles, suppression unknown_XXX |
| 2026-05-14 | Workflow `import/` → `export/` : résolution input depuis `import/`, basename normalisé `YYYY-MM-DD_<activité>_<indice>` partagé `.md`/`.fit`, déplacement du `.fit` source après succès, auto-incrément de l'indice, module `file_manager.py` dédié |
| 2026-05-14 | Génération GPX 1.1 automatique : module `gpx_exporter.py`, `<trk>`/`<trkseg>`/`<trkpt>` avec `<ele>` et `<time>` ISO 8601 UTC, basename partagé avec `.md`/`.fit`, trace complète indépendante de `--gps-limit`, extension de `next_available_index` pour scanner aussi les `.gpx` |

---

## 13. Next Improvements

- Mode **batch** : traiter un dossier entier de `.fit` → un `.md` par activité
- Option `--format obsidian` : frontmatter YAML + naming `YYYY-MM-DD_sport_distance.md`
- Option `--lang en` : labels en anglais pour coaching avec IA anglophone
- Calcul de la **charge hebdomadaire** si plusieurs fichiers fournis

---

## 14. AI Instructions (MANDATORY)

### Context matériel connu
Ce projet a été développé et testé sur deux matériels réels :

**Suunto Spartan Ultra** (running + trail) :
- Contient : `hrv` (10 000+ intervalles RR), developer fields (`feeling`, `recovery_time`, `peak_epoc`, `ddfa`, zones aérobie/anaérobie/VO2max), `avg_running_cadence`, `total_strides`
- Ne contient pas : `user_profile`, `zones_target`, `device_settings`

**Garmin Edge** (GPS vélo) :
- Contient : `user_profile` (âge, poids, FC repos), `zones_target` (FTP, seuil FC), `device_settings`, `avg_vam`, `training_file`
- Ne contient pas : `hrv`, developer fields
- Contient beaucoup de messages `unknown_XXX` → à ignorer

### How to update this project
- Toujours respecter les invariants (section 9)
- Ne pas modifier l'interface CLI sans mettre à jour la section 5
- Les champs `None` doivent toujours être gérés
- Toute nouvelle section Markdown doit être conditionnelle
- Toute logique de chemin / nommage / déplacement appartient à `file_manager.py`, pas à `extractor.py`
- Toute logique d'extraction GPS / génération XML GPX appartient à `gpx_exporter.py`, pas à `extractor.py`
- Respecter le workflow `import/` → `export/` : ne pas réintroduire d'écriture par défaut à côté du `.fit` source
- Le GPX doit rester en stdlib (`xml.etree.ElementTree`) — pas d'ajout de dépendance `gpxpy` ou autre

### Before coding
- Lire ce document en entier
- Identifier quel matériel est concerné (section 14 Context)
- Vérifier les invariants (section 9)

### When modifying code
- Mettre à jour la section 12 (Evolution History)
- Justifier tout changement de dépendance dans la section 7

### Forbidden
- Introduire une dépendance autre que `fitparse` sans justification
- Écrire des fichiers temporaires `.fit` sur le disque
- Supprimer `StandardUnitsDataProcessor` de l'initialisation de `FitFile`
- Inclure les champs `unknown_XXX` dans le Markdown
- Inclure les intervalles HRV bruts dans le Markdown
- Réécrire entièrement le script sans raison documentée
- Coder en dur une liste de champs à extraire (utiliser l'extraction générique)
- Écrire le `.md` par défaut ailleurs que dans `export/` (sauf `--output` explicite ou `--stdout`)
- Laisser un `.fit` traité avec succès dans `import/` (sauf `--stdout`)
- Détecter `.fit.gz` via `Path.suffix` (qui ne voit que `.gz`) — utiliser `name.lower().endswith(".fit.gz")`
- Inclure FC, cadence, vitesse ou puissance dans le GPX V1
- Générer un fichier GPX vide si aucun point GPS exploitable n'existe
- Appliquer `--gps-limit` au fichier GPX
- Ajouter une dépendance externe pour le GPX (utiliser `xml.etree.ElementTree` stdlib)
