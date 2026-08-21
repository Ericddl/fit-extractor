# Spec fonctionnelle d'évolution — Export GPX depuis les points GPS FIT

## 0. Identification

| Champ | Valeur |
|---|---|
| **Nom de l'évolution** | Génération d'un fichier GPX à partir des points GPS du FIT |
| **Fichier feature** | `docs/gpx.md` |
| **Date de rédaction** | 2026-05-14 |
| **Statut** | `Livré` (fusionné dans `main`) |
| **Priorité** | `Must` |

---

## 1. Contexte et motivation

### Situation actuelle

Le projet `fit-extractor` convertit un fichier `.fit` ou `.fit.gz` en Markdown structuré, optimisé pour être envoyé à une IA de coaching sportif.

Comportement actuel :
- le script parse les fichiers FIT avec `fitparse` ;
- les messages `record` sont extraits dans le flux générique ;
- une option `--gps` permet déjà d'ajouter au Markdown une section avec des points GPS échantillonnés ;
- cette section GPS est limitée au Markdown et ne produit pas de fichier exploitable par un outil cartographique ;
- les fichiers générés doivent suivre la logique de classement `import/` → `export/` et la convention de nommage commune définie dans l'évolution `file_manager_change.md`.

Limite ou manque identifié :
- le Markdown est utile pour l'analyse textuelle, mais peu adapté à la visualisation cartographique ;
- les points GPS inclus dans le Markdown sont volontairement limités par `--gps-limit`, donc insuffisants pour représenter précisément la trace ;
- l'utilisateur souhaite pouvoir fournir à une IA ou à un outil tiers un couple cohérent :
  - un fichier `.md` contenant les métriques et l'analyse structurée ;
  - un fichier `.gpx` contenant la trace complète de l'activité.

### Objectif de l'évolution

Générer automatiquement un fichier GPX à partir des points GPS présents dans le fichier FIT, en utilisant la même logique de nommage et de classement que le Markdown et le FIT archivé.

Le résultat attendu est d'avoir, dans `export/`, trois fichiers associés à une même activité :

```text
2026-05-14_trail_001.fit
2026-05-14_trail_001.md
2026-05-14_trail_001.gpx
```

---

## 2. Besoin fonctionnel

### Cas d'usage principal

```text
En tant qu'utilisateur du fit-extractor,
Quand je traite une activité .fit contenant des points GPS,
Je veux que l'outil génère un fichier Markdown et un fichier GPX portant le même nom de base,
Afin de pouvoir donner à mon IA à la fois les métriques structurées et la trace GPS complète de la sortie.
```

### Comportement attendu

Lorsqu'un fichier FIT contient des points GPS exploitables :

1. le fichier `.fit` est lu depuis `import/` ;
2. le Markdown est généré dans `export/` ;
3. le GPX est généré dans `export/` ;
4. le fichier FIT traité est déplacé dans `export/` ;
5. les trois fichiers partagent exactement le même nom de base.

Exemple de rendu terminal attendu :

```text
Fichier source : import/Trail_le_matin.fit
Activité détectée : trail
Date activité : 2026-05-14
Export Markdown : export/2026-05-14_trail_001.md
Export GPX : export/2026-05-14_trail_001.gpx
Archive FIT : export/2026-05-14_trail_001.fit
Points GPX exportés : 10284
Traitement terminé.
```

Structure cible :

```text
fit-extractor/
├── import/
├── export/
│   ├── 2026-05-14_trail_001.fit
│   ├── 2026-05-14_trail_001.md
│   └── 2026-05-14_trail_001.gpx
├── extractor.py
├── README.md
└── SPEC.md
```

### Règles métier

- Le fichier GPX doit être généré uniquement si le fichier FIT contient des points GPS exploitables.
- Un point GPS exploitable doit contenir au minimum :
  - `position_lat` ;
  - `position_long`.
- Si le point contient une altitude, elle doit être exportée dans `<ele>`.
- Si le point contient un timestamp, il doit être exporté dans `<time>`.
- Le GPX généré doit utiliser le format GPX 1.1.
- Le GPX doit représenter l'activité sous forme de trace :
  - `<trk>` pour la trace ;
  - `<trkseg>` pour le segment ;
  - `<trkpt>` pour chaque point GPS.
- Le fichier `.gpx` doit porter le même nom de base que le `.md` et le `.fit` archivé.
- Le fichier `.gpx` doit être écrit dans `export/`.
- Le GPX doit contenir la trace complète disponible dans le FIT, sans appliquer `--gps-limit`.
- L'option `--gps-limit` ne concerne que l'échantillonnage des points GPS dans le Markdown.
- Le fichier GPX ne doit jamais contenir les champs propriétaires ou `unknown_XXX`.
- En l'absence de points GPS exploitables :
  - le Markdown doit rester généré normalement ;
  - aucun fichier GPX vide ne doit être généré ;
  - un message explicite doit être affiché dans le terminal.
- Le comportement ne doit pas introduire de dépendance externe supplémentaire.
- Le fichier GPX ne doit jamais écraser silencieusement un fichier existant.
- L'option `--force` autorise l'écrasement explicite du `.md`, du `.gpx` et du fichier FIT archivé si nécessaire.

---

## 3. Impact sur l'architecture existante

### Composants modifiés

| Composant | Nature de la modification | Impact estimé |
|---|---|---|
| `extractor.py` | Extraction complète des points GPS depuis les messages `record` | Moyen |
| `extractor.py` | Ajout de la génération GPX | Moyen |
| `extractor.py` | Écriture d'un fichier `.gpx` dans `export/` | Moyen |
| `extractor.py` | Extension de la logique de nommage commune `.fit` / `.md` / `.gpx` | Moyen |
| `README.md` | Mise à jour de l'usage et des exemples | Faible |
| `SPEC.md` | Mise à jour architecture, CLI, core logic, invariants, out of scope et historique | Moyen |
| `CLAUDE.md` | Mise à jour des consignes IA sur la génération GPX | Faible |

### Nouveaux composants

Aucun nouveau composant obligatoire en V1.

Option recommandée si l'architecture est découpée :

| Composant | Rôle | Fichier |
|---|---|---|
| `gpx_exporter.py` | Générer le XML GPX 1.1 à partir des points GPS extraits | `gpx_exporter.py` |

Décision V1 proposée :
- si le projet reste en script unique, implémenter la génération GPX dans `extractor.py` via fonctions dédiées ;
- si l'évolution `file_manager_change.md` introduit déjà un découpage, ajouter un module `gpx_exporter.py`.

### Modifications de configuration

Aucune variable `.env`.

Aucune nouvelle dépendance externe.

La génération GPX doit utiliser la bibliothèque standard Python, par exemple :

```python
xml.etree.ElementTree
```

Nouveaux fichiers générés :

```text
export/YYYY-MM-DD_<activité>_<indice>.gpx
```

---

## 4. Spécification technique

### Nouveaux modules / fonctions

#### `extract_gps_points()`

- **Role** : extraire les points GPS exploitables depuis les messages `record`.
- **Public interface** :

```python
def extract_gps_points(records: list[dict]) -> list[dict]:
    ...
```

- **Entrée attendue** :
  - liste des records déjà extraits depuis le FIT.

- **Sortie attendue** :

```python
[
    {
        "timestamp": datetime | None,
        "lat": float,
        "lon": float,
        "ele": float | None,
        "heart_rate": int | None,
        "speed": float | None,
    }
]
```

- **Règles** :
  - ignorer tout record sans latitude ou longitude ;
  - conserver l'ordre chronologique naturel du FIT ;
  - ne pas inclure les points invalides ;
  - ne pas limiter le nombre de points.

#### `has_gps_points()`

- **Role** : vérifier si une activité contient au moins un point GPS exploitable.
- **Public interface** :

```python
def has_gps_points(gps_points: list[dict]) -> bool:
    ...
```

- **Règle** :
  - retourne `True` si au moins un point contient latitude et longitude.

#### `format_gpx_time()`

- **Role** : formater un timestamp Python en timestamp GPX compatible ISO 8601.
- **Public interface** :

```python
def format_gpx_time(value: datetime) -> str:
    ...
```

- **Format attendu** :

```text
YYYY-MM-DDTHH:MM:SSZ
```

#### `build_gpx()`

- **Role** : construire le contenu XML GPX 1.1 à partir des points GPS.
- **Public interface** :

```python
def build_gpx(
    gps_points: list[dict],
    activity_name: str,
    creator: str = "fit-extractor"
) -> str:
    ...
```

- **Sortie** :
  - chaîne XML complète du fichier GPX.

- **Structure minimale attendue** :

```xml
<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="fit-extractor" xmlns="http://www.topografix.com/GPX/1/1">
  <trk>
    <name>2026-05-14_trail_001</name>
    <trkseg>
      <trkpt lat="45.123456" lon="6.123456">
        <ele>1234.5</ele>
        <time>2026-05-14T08:12:34Z</time>
      </trkpt>
    </trkseg>
  </trk>
</gpx>
```

#### `write_gpx_file()`

- **Role** : écrire le GPX sur disque.
- **Public interface** :

```python
def write_gpx_file(gpx_content: str, output_path: Path, force: bool = False) -> None:
    ...
```

- **Règles** :
  - refuser l'écrasement si le fichier existe et que `force=False` ;
  - écrire en UTF-8 ;
  - ne rien écrire si `gpx_content` est vide.

### Modifications dans les modules existants

#### `extractor.py`

- Changement apporté :
  - conserver tous les records contenant `position_lat` et `position_long` ;
  - générer un fichier GPX à partir de ces points ;
  - écrire le GPX dans `export/` ;
  - utiliser le même basename que le `.md` et le `.fit`.

- Raison :
  - fournir à l'utilisateur un artefact cartographique exploitable ;
  - permettre à une IA ou à un outil tiers de reconstruire la trace complète ;
  - éviter de polluer le Markdown avec des milliers de points GPS.

### Nouveau modèle de données

Optionnel mais recommandé :

```python
@dataclass
class GpsPoint:
    timestamp: datetime | None
    lat: float
    lon: float
    ele: float | None = None
    heart_rate: int | None = None
    speed: float | None = None
```

Optionnel si le nommage est déjà centralisé par l'évolution précédente :

```python
@dataclass
class ActivityArtifacts:
    basename: str
    fit_path: Path
    markdown_path: Path
    gpx_path: Path | None
```

---

## 5. Logique métier critique

### Extraction des coordonnées

Les coordonnées doivent être extraites depuis les records FIT.

Champs attendus :
- `position_lat`
- `position_long`
- `altitude`
- `timestamp`
- éventuellement `heart_rate`
- éventuellement `speed`

Avec `StandardUnitsDataProcessor()`, les coordonnées doivent déjà être converties en degrés. Il ne faut donc pas refaire manuellement la conversion semicircles → degrés si `fitparse` a déjà appliqué le processor.

### Filtrage des points

Un point est exportable si :
- latitude non nulle ;
- longitude non nulle ;
- latitude et longitude numériques ;
- latitude comprise entre `-90` et `90` ;
- longitude comprise entre `-180` et `180`.

Un point est ignoré si :
- latitude absente ;
- longitude absente ;
- coordonnées invalides ;
- record vide ou partiel.

### Génération du GPX

Le GPX doit :
- utiliser GPX 1.1 ;
- contenir une trace `<trk>` ;
- contenir un segment `<trkseg>` ;
- contenir un `<trkpt>` par point GPS ;
- inclure `lat` et `lon` comme attributs ;
- inclure `<ele>` si l'altitude est disponible ;
- inclure `<time>` si le timestamp est disponible.

### Données non exportées en V1

Le GPX V1 ne doit pas exporter :
- fréquence cardiaque ;
- vitesse ;
- cadence ;
- puissance ;
- température ;
- métriques Suunto developer fields ;
- extensions propriétaires GPX.

Ces données restent dans le Markdown.

### Comportement en absence de GPS

Si aucun point GPS exploitable n'est trouvé :

```text
Aucun point GPS exploitable trouvé : GPX non généré.
```

Le traitement reste considéré comme réussi si le Markdown a été généré.

### Relation avec `--gps` et `--gps-limit`

- `--gps` contrôle uniquement l'ajout d'un extrait GPS dans le Markdown.
- `--gps-limit` contrôle uniquement le nombre de points GPS affichés dans le Markdown.
- La génération GPX utilise toujours tous les points GPS disponibles.
- La génération GPX doit être activée par défaut si des points GPS existent.

Décision V1 proposée :
- générer automatiquement le GPX dès qu'il y a des points GPS ;
- ajouter éventuellement une option future `--no-gpx` si l'utilisateur veut désactiver cette génération.

---

## 6. Décisions techniques

| Décision | Pourquoi | Alternative rejetée |
|---|---|---|
| Générer un fichier GPX 1.1 | Format standard, lisible par les outils cartographiques et les IA | Format propriétaire ou JSON |
| Utiliser `<trk>` / `<trkseg>` / `<trkpt>` | Représente correctement une trace d'activité sportive | Utiliser des waypoints indépendants |
| Générer le GPX automatiquement si GPS présent | Répond au besoin principal sans option supplémentaire | Obliger l'utilisateur à ajouter une option `--gpx` |
| Ne pas appliquer `--gps-limit` au GPX | Le GPX doit contenir la trace complète | Exporter seulement l'échantillon Markdown |
| Ne pas exporter FC/vitesse en extensions GPX en V1 | Rester simple, standard et robuste | Ajouter des extensions Garmin ou propriétaires |
| Utiliser `xml.etree.ElementTree` | Stdlib, pas de dépendance externe | Ajouter `gpxpy` |
| Ne pas générer de GPX vide | Évite les artefacts inutiles et trompeurs | Créer un fichier GPX sans trace |
| Même basename pour `.fit`, `.md`, `.gpx` | Association immédiate des artefacts d'une activité | Nommage séparé par type de fichier |

---

## 7. Invariants à préserver

Invariants existants à préserver :

- [ ] Ne jamais écrire de fichier `.fit` intermédiaire sur le disque.
- [ ] Toujours utiliser `StandardUnitsDataProcessor()`.
- [ ] Ne jamais inclure les champs `unknown_XXX` dans le Markdown.
- [ ] Ne jamais inclure les intervalles HRV bruts dans le Markdown.
- [ ] Ne jamais écraser silencieusement un fichier `.md` existant.
- [ ] Les champs `None` ne doivent jamais provoquer une exception.
- [ ] Le Markdown doit rester lisible sans rendu.
- [ ] Aucun fichier existant dans `export/` n'est écrasé silencieusement.
- [ ] Le fichier `.fit` archivé et le fichier `.md` généré partagent toujours le même basename.

Nouveaux invariants introduits par cette évolution :

- [ ] Le fichier `.gpx` partage toujours le même basename que le `.md` et le `.fit`.
- [ ] Le fichier `.gpx` est toujours écrit dans `export/`.
- [ ] Aucun fichier `.gpx` vide n'est généré.
- [ ] Le GPX contient uniquement des points avec latitude et longitude valides.
- [ ] Le GPX n'est généré que si le FIT contient des points GPS exploitables.
- [ ] `--gps-limit` ne limite jamais le fichier GPX.
- [ ] La génération GPX ne doit pas empêcher la génération Markdown si les points GPS sont absents.
- [ ] La génération GPX ne doit pas introduire de dépendance externe.
- [ ] Les extensions propriétaires GPX sont hors périmètre V1.

---

## 8. Hors périmètre (Out of Scope)

Cette évolution ne couvre pas :

- l'export GPX enrichi avec fréquence cardiaque, cadence, puissance ou vitesse ;
- les extensions GPX Garmin, Strava, Suunto ou TrackPointExtension ;
- la simplification ou compression de trace ;
- le découpage en plusieurs segments GPX en cas de pause ou perte GPS ;
- la correction ou interpolation de points GPS manquants ;
- l'analyse cartographique ;
- la génération d'une carte ou d'une image de parcours ;
- l'import du GPX dans Strava, Garmin, Suunto ou autre plateforme ;
- la gestion avancée des activités multi-sport ou multi-session ;
- la comparaison entre trace FIT et trace GPX externe.

---

## 9. Critères d'acceptation

- [ ] Un fichier FIT contenant des points GPS génère un fichier `.gpx`.
- [ ] Le fichier `.gpx` est écrit dans `export/`.
- [ ] Le fichier `.gpx` porte le même basename que le `.md` et le `.fit` archivé.
- [ ] Le GPX contient une racine `<gpx>` en version `1.1`.
- [ ] Le GPX contient une trace `<trk>`.
- [ ] Le GPX contient un segment `<trkseg>`.
- [ ] Chaque point GPS exporté est représenté par un `<trkpt>`.
- [ ] Chaque `<trkpt>` contient des attributs `lat` et `lon`.
- [ ] L'altitude est exportée dans `<ele>` quand elle est disponible.
- [ ] Le timestamp est exporté dans `<time>` quand il est disponible.
- [ ] Un FIT sans GPS ne génère pas de fichier `.gpx`.
- [ ] Un FIT sans GPS continue à générer le Markdown normalement.
- [ ] Aucun fichier GPX vide n'est généré.
- [ ] Aucun fichier existant n'est écrasé sans `--force`.
- [ ] `--gps-limit` ne limite pas le nombre de points dans le GPX.
- [ ] Le comportement existant de génération Markdown reste inchangé.
- [ ] `README.md` est mis à jour avec le nouveau comportement.
- [ ] `SPEC.md` est mis à jour.
- [ ] `CLAUDE.md` est mis à jour si nécessaire.

---

## 10. Mise à jour SPEC.md requise

| Section SPEC.md | Mise à jour requise |
|---|---|
| 1 — Overview | Ajouter le GPX comme sortie secondaire |
| 2 — Architecture / Project structure | Ajouter les fichiers `.gpx` dans `export/` |
| 2 — Architecture / Data flow | Ajouter extraction GPS complète puis génération GPX |
| 3 — Components | Ajouter la responsabilité de génération GPX |
| 4 — Core Logic | Ajouter les règles d'extraction GPS et de génération GPX |
| 5 — Contracts & Interfaces | Documenter le comportement GPX par défaut |
| 6 — Configuration | Clarifier la relation entre `--gps`, `--gps-limit` et le GPX |
| 7 — Technical Decisions | Ajouter les décisions liées au format GPX 1.1 |
| 9 — Invariants | Ajouter les invariants GPX |
| 10 — Out of Scope | Retirer l'exclusion stricte “uniquement Markdown” ou la reformuler |
| 12 — Evolution History | Ajouter une ligne à la livraison de cette évolution |
| 14 — AI Instructions | Ajouter les consignes de génération GPX sans dépendance externe |

---
