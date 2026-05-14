# Spec fonctionnelle d'évolution — Gestion des dossiers import/export

## 0. Identification

| Champ | Valeur |
|---|---|
| **Nom de l'évolution** | Gestion des dossiers `import/` et `export/` |
| **Fichier feature** | `features/file_manager_change.md` |
| **Date de rédaction** | 2026-05-14 |
| **Statut** | `Brouillon` |
| **Priorité** | `Must` |

---

## 1. Contexte et motivation

### Situation actuelle

Le projet `fit-extractor` permet de convertir un fichier `.fit` ou `.fit.gz` en fichier Markdown structuré, optimisé pour une analyse par IA de coaching sportif.

Comportement actuel :
- l'utilisateur fournit explicitement le chemin d'un fichier `.fit` ;
- le fichier `.md` généré est créé par défaut à côté du fichier `.fit` source ;
- l'option `--output` permet de préciser manuellement un chemin de sortie ;
- l'option `--stdout` permet d'écrire le Markdown dans le terminal au lieu d'un fichier ;
- l'option `--force` est nécessaire pour écraser un fichier `.md` existant.

Limite ou manque identifié :
- les fichiers entrants et sortants ne sont pas séparés clairement ;
- les fichiers `.fit` déjà traités restent dans le dossier d'import ;
- le nommage des exports n'est pas normalisé pour un usage d'archivage ;
- il existe un risque d'écrasement ou de confusion entre plusieurs activités traitées le même jour.

### Objectif de l'évolution

Structurer le cycle de traitement autour de deux dossiers standards : `import/` pour les fichiers entrants et `export/` pour les fichiers produits ou archivés.

Après traitement, chaque fichier `.fit` ou `.fit.gz` doit être déplacé dans `export/`, renommé selon une convention stable, et placé à côté du fichier `.md` généré.

---

## 2. Besoin fonctionnel

### Cas d'usage principal

```text
En tant qu'utilisateur du fit-extractor,
Quand je dépose un ou plusieurs fichiers .fit dans le dossier import/
Je veux que l'outil lise les fichiers depuis import/, génère les fichiers Markdown dans export/,
puis déplace les fichiers .fit traités dans export/ avec un nom cohérent,
Afin de disposer d'un dossier d'export propre contenant à la fois les données sources traitées et les analyses Markdown associées.
```

### Comportement attendu

Le projet doit gérer deux dossiers standards à la racine :

```text
fit-extractor/
├── import/
│   └── activité_source.fit
├── export/
│   ├── 2026-05-14_trail_001.fit
│   └── 2026-05-14_trail_001.md
├── extractor.py
├── README.md
└── SPEC.md
```

Lorsqu'un fichier `.fit` est traité :

1. le fichier source est lu depuis `import/` ;
2. le fichier Markdown est généré dans `export/` ;
3. le fichier `.fit` source est déplacé dans `export/` ;
4. le fichier `.fit` déplacé est renommé avec le même préfixe que le `.md` généré ;
5. le fichier `.fit` et le fichier `.md` doivent donc se retrouver côte à côte dans `export/`.

Exemple de rendu terminal attendu :

```text
Fichier source : import/Trail_le_matin.fit
Activité détectée : trail
Date activité : 2026-05-14
Export Markdown : export/2026-05-14_trail_001.md
Archive FIT : export/2026-05-14_trail_001.fit
Traitement terminé.
```

### Règles métier

- Tous les fichiers `.fit` et `.fit.gz` à traiter doivent être recherchés dans le dossier `import/`.
- Tous les fichiers générés ou déplacés après traitement doivent être déposés dans le dossier `export/`.
- Le dossier `import/` doit être créé automatiquement s'il n'existe pas.
- Le dossier `export/` doit être créé automatiquement s'il n'existe pas.
- Après traitement réussi, le fichier `.fit` ou `.fit.gz` source est déplacé de `import/` vers `export/`.
- Le fichier source n'est déplacé que si le Markdown a été généré avec succès.
- Le fichier source et le fichier Markdown doivent partager le même nom de base.
- Le nom cible doit suivre le format :

```text
YYYY-MM-DD_<nom_activite>_<indice>.<extension>
```

Exemple :

```text
2026-05-14_trail_001.fit
2026-05-14_trail_001.md
```

- `YYYY-MM-DD` correspond à la date de l'activité extraite du fichier FIT si elle est disponible.
- Si aucune date d'activité fiable n'est disponible, utiliser la date du traitement.
- `<nom_activite>` est dérivé des données de session FIT si disponibles : `sport`, `sub_sport` ou équivalent.
- Si aucun nom d'activité fiable n'est disponible, utiliser le nom du fichier source normalisé.
- `<indice>` sert à distinguer plusieurs activités ayant la même date et le même type.
- L'indice doit être stable et lisible : `001`, `002`, `003`, etc.
- Si le fichier FIT contient un identifiant ou index exploitable d'activité, il peut être utilisé pour produire l'indice.
- Si aucun indice exploitable n'existe dans le FIT, l'indice est calculé à partir des fichiers déjà présents dans `export/`.
- Le renommage ne doit jamais écraser silencieusement un fichier existant.
- En cas de conflit de nom, l'outil doit :
  - soit incrémenter automatiquement l'indice jusqu'à trouver un nom libre ;
  - soit refuser l'écriture si `--force` n'est pas fourni.
- L'option `--stdout` doit continuer à fonctionner sans générer de fichier Markdown.
- En mode `--stdout`, le fichier source ne doit pas être déplacé par défaut, afin d'éviter un effet de bord inattendu.
- L'option `--output` reste possible mais devient un cas avancé.
- Si `--output` est fourni, le comportement de déplacement du fichier FIT doit rester explicite et documenté.

---

## 3. Impact sur l'architecture existante

### Composants modifiés

| Composant | Nature de la modification | Impact estimé |
|---|---|---|
| `extractor.py` | Ajout de la gestion des dossiers `import/` et `export/` | Moyen |
| `extractor.py` | Modification de la résolution du chemin d'entrée par défaut | Moyen |
| `extractor.py` | Modification de la résolution du chemin de sortie par défaut | Moyen |
| `extractor.py` | Ajout du déplacement/renommage du fichier source après succès | Moyen |
| `README.md` | Mise à jour de l'usage CLI et des exemples | Faible |
| `SPEC.md` | Mise à jour architecture, CLI, core logic, invariants, historique | Moyen |
| `CLAUDE.md` | Mise à jour des consignes de développement IA | Faible |

### Nouveaux composants

Aucun nouveau composant obligatoire en V1.

Option recommandée si le script commence à grossir :

| Composant | Rôle | Fichier |
|---|---|---|
| `file_manager.py` | Centraliser la résolution des chemins, le nommage, le déplacement des fichiers | `file_manager.py` |

Décision V1 proposée : conserver une implémentation dans `extractor.py`, avec fonctions dédiées, pour rester cohérent avec l'architecture actuelle en script unique.

### Modifications de configuration

Aucune variable `.env`.

Nouveaux dossiers standards :

```text
import/
export/
```

Ces dossiers peuvent être créés automatiquement à l'exécution.

Recommandation `.gitignore` :

```gitignore
/import/*
/export/*
!/import/.gitkeep
!/export/.gitkeep
```

Objectif :
- éviter de commiter des fichiers sportifs personnels ;
- permettre de versionner la structure des dossiers via `.gitkeep`.

---

## 4. Spécification technique

### Nouveaux modules / fonctions

#### `ensure_workdirs()`

- **Role** : garantir l'existence des dossiers `import/` et `export/`.
- **Public interface** :

```python
def ensure_workdirs(import_dir: Path, export_dir: Path) -> None:
    ...
```

- **Dependencies** : `pathlib`
- **Side effects / specifics** :
  - crée les dossiers si absents ;
  - ne supprime jamais de fichier existant.

#### `resolve_input_path()`

- **Role** : résoudre le fichier FIT à traiter.
- **Public interface** :

```python
def resolve_input_path(input_arg: str | None, import_dir: Path) -> Path:
    ...
```

- **Comportement attendu** :
  - si un chemin explicite est fourni, l'utiliser ;
  - si seul un nom de fichier est fourni, chercher dans `import/` ;
  - si aucun input n'est fourni, le comportement batch n'est pas activé en V1 : retourner une erreur explicite.

#### `build_activity_basename()`

- **Role** : construire le nom de base commun aux fichiers `.fit` et `.md`.
- **Public interface** :

```python
def build_activity_basename(parsed_data: dict, source_path: Path, export_dir: Path) -> str:
    ...
```

- **Format retourné** :

```text
YYYY-MM-DD_<nom_activite>_<indice>
```

- **Exemple** :

```text
2026-05-14_trail_001
```

#### `sanitize_filename_part()`

- **Role** : normaliser les parties de nom de fichier.
- **Public interface** :

```python
def sanitize_filename_part(value: str) -> str:
    ...
```

- **Règles** :
  - minuscules ;
  - espaces remplacés par `_` ;
  - accents supprimés si possible via stdlib ;
  - caractères spéciaux supprimés ;
  - fallback `activite` si valeur vide.

#### `next_available_index()`

- **Role** : déterminer le prochain indice disponible dans `export/`.
- **Public interface** :

```python
def next_available_index(date_part: str, activity_part: str, export_dir: Path) -> str:
    ...
```

- **Exemple** :
  - fichiers existants :
    - `2026-05-14_trail_001.md`
    - `2026-05-14_trail_001.fit`
  - nouvel export :
    - `2026-05-14_trail_002.md`
    - `2026-05-14_trail_002.fit`

#### `move_processed_fit()`

- **Role** : déplacer le fichier FIT source vers `export/` après succès.
- **Public interface** :

```python
def move_processed_fit(source_path: Path, target_path: Path, force: bool = False) -> None:
    ...
```

- **Règles** :
  - appelé uniquement après génération réussie du Markdown ;
  - refuse l'écrasement sauf `--force` ;
  - conserve l'extension d'origine : `.fit` ou `.fit.gz`.

### Modifications dans les modules existants

#### `extractor.py`

- Changement apporté :
  - ajout d'une gestion standardisée des dossiers `import/` et `export/` ;
  - modification du chemin de sortie Markdown par défaut ;
  - ajout du renommage du `.md` selon la convention `YYYY-MM-DD_<activité>_<indice>.md` ;
  - ajout du déplacement et renommage du `.fit` traité dans `export/`.

- Raison :
  - rendre l'outil plus exploitable au quotidien ;
  - séparer clairement les fichiers entrants et sortants ;
  - faciliter l'archivage dans Obsidian ou dans un dossier de suivi sportif ;
  - éviter les collisions de fichiers.

### Nouveau modèle de données

Optionnel mais recommandé pour clarifier le code :

```python
@dataclass
class ActivityFileNaming:
    date: str
    activity_name: str
    index: str
    basename: str
    markdown_path: Path
    source_archive_path: Path
```

---

## 5. Logique métier critique

### Résolution de la date

Ordre de priorité :

1. date de début de l'activité extraite depuis le FIT ;
2. date de session si disponible ;
3. date du traitement si aucune date fiable n'est disponible.

Format obligatoire :

```text
YYYY-MM-DD
```

### Résolution du nom d'activité

Ordre de priorité :

1. `sport` + éventuellement `sub_sport` si disponible ;
2. type d'activité détecté dans les données de session ;
3. nom du fichier source nettoyé ;
4. fallback `activite`.

Exemples :

```text
running
trail
cycling
velo
course
activite
```

### Résolution de l'indice

Objectif : éviter les collisions et permettre plusieurs activités le même jour.

Règle V1 :

- chercher les fichiers existants dans `export/` qui matchent :

```text
YYYY-MM-DD_<nom_activite>_*.md
YYYY-MM-DD_<nom_activite>_*.fit
YYYY-MM-DD_<nom_activite>_*.fit.gz
```

- extraire les indices numériques existants ;
- prendre l'indice suivant ;
- formater sur 3 chiffres.

Exemple :

```text
001
002
003
```

### Déplacement du fichier source

Le fichier source est déplacé uniquement après génération réussie du Markdown.

Si la génération Markdown échoue :
- le fichier source reste dans `import/` ;
- aucun fichier partiel ne doit être laissé dans `export/`, ou alors il doit être clairement supprimé/ignoré.

### Gestion de `--stdout`

En mode `--stdout` :
- le Markdown est affiché dans le terminal ;
- aucun fichier `.md` n'est généré ;
- le fichier `.fit` source n'est pas déplacé ;
- les dossiers `import/` et `export/` peuvent être créés mais aucun archivage n'est réalisé.

### Gestion de `--output`

En mode `--output` :
- l'utilisateur force explicitement le chemin du `.md` ;
- le nommage automatique peut être court-circuité pour le Markdown ;
- le déplacement du `.fit` reste à définir explicitement.

Décision V1 recommandée :
- si `--output` est fourni, générer le Markdown à l'emplacement demandé ;
- ne pas déplacer automatiquement le `.fit`, sauf option dédiée ultérieure ;
- afficher un message clair.

---

## 6. Décisions techniques

| Décision | Pourquoi | Alternative rejetée |
|---|---|---|
| Utiliser `import/` comme dossier d'entrée standard | Simple, explicite, adapté à un usage manuel | Demander un chemin complet à chaque exécution |
| Utiliser `export/` comme dossier unique de sortie et d'archive | Centralise le `.md` et le `.fit` traité | Garder le `.fit` dans `import/` après traitement |
| Renommer `.fit` et `.md` avec le même basename | Permet d'associer immédiatement source et résultat | Conserver le nom source du `.fit` |
| Utiliser `YYYY-MM-DD_<activité>_<indice>` | Lisible, triable, compatible archivage | Nom aléatoire ou timestamp complet |
| Calculer l'indice à partir du contenu de `export/` si nécessaire | Évite les collisions sans dépendance externe | Stocker un fichier d'état local |
| Ne pas déplacer le `.fit` en mode `--stdout` | Évite un effet de bord dans un mode pensé pour le copier-coller | Archiver systématiquement même sans génération fichier |
| Rester en stdlib uniquement | Respecte la philosophie du projet | Ajouter une dépendance de gestion de fichiers |

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

Nouveaux invariants introduits par cette évolution :

- [ ] Un fichier `.fit` traité avec succès ne reste pas dans `import/`, sauf mode `--stdout` ou `--output` explicite.
- [ ] Un fichier `.fit` n'est jamais déplacé si la génération Markdown échoue.
- [ ] Le fichier `.fit` archivé et le fichier `.md` généré partagent toujours le même basename.
- [ ] Tous les exports automatiques sont écrits dans `export/`.
- [ ] Tous les imports automatiques sont lus depuis `import/`.
- [ ] Aucun fichier existant dans `export/` n'est écrasé silencieusement.
- [ ] Les dossiers `import/` et `export/` sont créés automatiquement si absents.
- [ ] Le nommage produit des noms compatibles avec la plupart des systèmes de fichiers.

---

## 8. Hors périmètre (Out of Scope)

Cette évolution ne couvre pas :

- le traitement batch complet de tous les fichiers présents dans `import/` ;
- l'analyse multi-activité ou charge hebdomadaire ;
- la génération d'un index global des activités ;
- la création de frontmatter YAML Obsidian ;
- l'export CSV, JSON ou HTML ;
- l'envoi automatique vers ChatGPT ou Claude ;
- la synchronisation avec Strava, Suunto ou Garmin ;
- la suppression automatique des fichiers présents dans `export/`.

Note : le traitement batch reste une amélioration future possible.

---

## 9. Critères d'acceptation

- [ ] Au lancement, les dossiers `import/` et `export/` sont créés s'ils n'existent pas.
- [ ] Un fichier `.fit` placé dans `import/` peut être traité sans préciser de chemin de sortie.
- [ ] Le fichier `.md` généré est créé dans `export/`.
- [ ] Après traitement réussi, le fichier `.fit` source est déplacé dans `export/`.
- [ ] Le fichier `.fit` déplacé et le fichier `.md` généré ont le même basename.
- [ ] Le nom généré respecte le format `YYYY-MM-DD_<activité>_<indice>`.
- [ ] Deux activités du même type le même jour ne s'écrasent pas.
- [ ] L'indice est incrémenté correctement si un fichier existe déjà.
- [ ] En cas d'échec de parsing FIT, le fichier source reste dans `import/`.
- [ ] En cas d'échec d'écriture Markdown, le fichier source reste dans `import/`.
- [ ] En mode `--stdout`, aucun fichier `.md` n'est généré et le `.fit` n'est pas déplacé.
- [ ] En cas de conflit de fichier, aucun écrasement silencieux n'a lieu.
- [ ] L'option `--force` conserve son rôle explicite d'autorisation d'écrasement.
- [ ] Le comportement existant de parsing, de génération Markdown et de filtrage des champs reste inchangé.
- [ ] `README.md` est mis à jour avec le nouveau workflow.
- [ ] `SPEC.md` est mis à jour.
- [ ] `CLAUDE.md` est mis à jour si les consignes IA doivent refléter le nouveau workflow.

---

## 10. Mise à jour SPEC.md requise

| Section SPEC.md | Mise à jour requise |
|---|---|
| 2 — Architecture / Project structure | Ajouter les dossiers `import/` et `export/` |
| 2 — Architecture / Data flow | Ajouter lecture depuis `import/`, écriture dans `export/`, puis déplacement du `.fit` |
| 3 — Components | Ajouter les responsabilités de gestion de fichiers dans `extractor.py` |
| 4 — Core Logic | Ajouter les règles de nommage, déplacement et non-écrasement |
| 5 — Contracts & Interfaces | Mettre à jour le comportement CLI par défaut |
| 6 — Configuration | Ajouter les dossiers standards `import/` et `export/` |
| 7 — Technical Decisions | Ajouter les décisions liées au workflow import/export |
| 9 — Invariants | Ajouter les nouveaux invariants de gestion de fichiers |
| 10 — Out of Scope | Clarifier que le batch reste hors périmètre de cette évolution |
| 12 — Evolution History | Ajouter une ligne à la livraison de cette évolution |
| 14 — AI Instructions | Ajouter les consignes de respect du workflow import/export |

---
