# 🧩 SPEC.md — Technical Living Spec — fit-extractor

> ⚠️ Document maintenu en rétro-spécification.
> Sert de **référence unique pour comprendre, modifier et faire évoluer le système**.
> Doit rester **simple, à jour et exploitable par une IA**.

---

## 0. Statut

| Champ | Valeur |
|-------|--------|
| Phase | Draft v2 |
| Branch courante | `main` |
| Dernière session IA | 2026-05-13 |
| Prochaine action | Implémenter `extractor.py` et valider sur les 3 fichiers de test réels |

---

## 1. Overview

**Project name** : `fit-extractor`
**Objective** : Extraire les données d'un fichier `.fit` (montre ou GPS vélo) et les convertir en Markdown structuré, **optimisé pour être envoyé à une IA (ChatGPT, Claude) pour du coaching sportif assisté**.
**Main stack** : Python 3.10+, `fitparse`, stdlib uniquement
**Last update** : 2026-05-13

### High-level behavior
- **Inputs** : un fichier `.fit` (ou `.fit.gz`) — Suunto Spartan Ultra (running/trail) ou GPS Garmin Edge (vélo)
- **Outputs** : un fichier `.md` lisible par un humain et dense en informations pour une IA de coaching
- **Core use case principal** : copier-coller le `.md` dans ChatGPT ou Claude pour obtenir une analyse de séance, des conseils d'entraînement, un suivi de charge
- **Core use cases secondaires** :
  - Extraction CLI simple : `python extractor.py mon_activite.fit`
  - Archivage personnel d'activités (vault Obsidian)

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
├── requirements.txt      # fitparse uniquement
├── SPEC.md               # Ce document
├── README.md             # Usage rapide
└── examples/
    ├── trail.fit         # Fichier de test Suunto running/trail
    ├── velo.fit          # Fichier de test Garmin vélo
    └── course.fit        # Fichier de test Suunto course à pied
```

### Data flow
```
fichier.fit (.gz)
  → décompression si .gz (gzip stdlib)
  → parsing FitFile (fitparse + StandardUnitsDataProcessor)
  → extraction générique de TOUS les messages connus
      session / lap / record / hrv / device_info /
      user_profile / zones_target / developer_fields
  → détection du profil matériel (Suunto vs Garmin vs autre)
  → formatage Markdown conditionnel par sections
      (sections absentes si données non disponibles)
  → écriture fichier .md
```

---

## 3. Components

### `extractor.py`

- **Role** : Script CLI unique — parsing générique, transformation, écriture
- **Files** : `extractor.py`
- **Public interface** :
  ```
  python extractor.py <input.fit> [--output chemin/sortie.md] [--gps] [--gps-limit N] [--stdout]
  ```
- **Dependencies** : `fitparse`, `gzip`, `pathlib`, `argparse`, `datetime`, `math`, `collections`
- **Side effects** : crée un fichier `.md` sur le disque (ou stdout si `--stdout`)

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

---

## 5. Contracts & Interfaces

### CLI
```
python extractor.py <input>  [options]

Arguments :
  input                 Chemin vers le fichier .fit ou .fit.gz

Options :
  --output PATH         Chemin du fichier .md de sortie
                        (défaut : même dossier que l'input, même nom, extension .md)
  --stdout              Afficher le Markdown dans le terminal (pour pipe ou copier-coller)
  --gps                 Inclure une section avec les points GPS échantillonnés
  --gps-limit N         Nombre max de points GPS à inclure (défaut : 30)
  --force               Écraser le fichier de sortie s'il existe déjà
```

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

| Argument | Usage | Défaut |
|----------|-------|--------|
| `--output` | Chemin de sortie du `.md` | `<input_stem>.md` |
| `--stdout` | Afficher dans le terminal | désactivé |
| `--gps` | Inclure les points GPS échantillonnés | désactivé |
| `--gps-limit` | Nb max de points GPS | 30 |
| `--force` | Écraser le fichier de sortie existant | désactivé |

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
- **Ne jamais écraser silencieusement un fichier `.md` existant** — erreur ou `--force` requis
- **Les champs `None` ne doivent jamais provoquer une exception** — fallback `"-"` systématique
- **Le Markdown doit rester lisible sans rendu** — tableaux GFM simples, pas de HTML

---

## 10. Out of Scope

- Pas de visualisation graphique
- Pas d'export CSV/JSON/HTML — uniquement Markdown
- Pas d'envoi automatique à une IA (pas d'appel API ChatGPT/Claude depuis le script)
- Pas de traitement batch multi-fichiers (une seule activité par appel)
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
