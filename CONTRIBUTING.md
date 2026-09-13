# Contribuer à fit-extractor

Merci de l'intérêt porté au projet. C'est un outil personnel rendu public : les contributions sont bienvenues, mais restent soumises à quelques règles simples.

## Signaler un bug

Ouvrez une [issue](https://github.com/Ericddl/fit-extractor/issues) en précisant :

- le **matériel** qui a produit le `.fit` (marque, modèle) ;
- la **commande** exécutée et le message d'erreur complet ;
- la version de Python (`python3 --version`).

⚠️ **Ne joignez jamais un `.fit` ou un `.gpx` personnel à une issue** : ils contiennent vos coordonnées GPS, domicile compris, ainsi que vos données de fréquence cardiaque. Décrivez plutôt le comportement observé.

## Proposer une modification

1. Forkez le dépôt et créez une branche (`feature/ma-fonctionnalite`).
2. Testez votre modification sur un vrai `.fit` — idéalement une activité outdoor **et** une activité indoor (sans GPS).
3. Ouvrez une pull request en décrivant le comportement avant / après.

Aucune suite de tests automatisés n'existe à ce jour. La vérification manuelle minimale :

```bash
python3 -B extractor.py --help
python3 -B extractor.py mon_activite.fit --stdout
python3 -B extractor.py mon_activite.fit --stdout --details --gps --gps-limit 30
```

`--stdout` ne crée ni export ni dossier et ne déplace pas la source ; `-B` évite
les caches Python. Aucun dossier `examples/` ni jeu de FIT de test n’est versionné.
L’aide CLI seule ne valide pas une conversion.

Pour vérifier les écritures, utiliser des données synthétiques ou des copies dans
des dossiers temporaires. Contrôler `.fit` et `.fit.gz`, avec et sans GPS, les
collisions, `--force` et la suppression d’un ancien GPX devenu sans objet.
Simuler les erreurs de préparation, publication et suppression de la source :
les octets de la source et des anciennes sorties doivent rester identiques après
restauration. Vérifier aussi la conservation des sauvegardes si celle-ci échoue.
Les contrôles ponctuels peuvent utiliser `unittest.mock` et `tempfile` de la stdlib.

Vérifier les limites GPS invalides (code 2, avant parsing), les échecs d’export
(code 1), l’absence de doublons en mode détaillé et la stabilité du rendu standard.
Documenter les commandes exécutées et ce qui n’a pas pu être vérifié.

## Invariants à respecter

Ces règles portent la conception du projet — une PR qui les enfreint sera refusée, sauf discussion préalable en issue :

- **Une seule dépendance** : `fitparse`. Le GPX est généré avec `xml.etree.ElementTree` de la stdlib — pas de `gpxpy` ni d'équivalent.
- **Extraction générique** : itérer sur les champs des types de messages traités ; le rendu standard sélectionne les métriques, `--details` le complète.
- **Toujours passer `StandardUnitsDataProcessor()`** à fitparse et respecter les unités par champ (`distance` en km, `total_distance` en m, vitesses en km/h).
- **Ignorer les champs `unknown_XXX`** : propriétaires, non documentés, bruit pour une IA.
- **HRV : RMSSD et SDNN uniquement** — jamais les intervalles RR bruts, qui dépassent 10 000 points.
- **`None` → `"-"`** : une donnée manquante ne doit jamais faire échouer le rendu.
- **Ne jamais écrire un `.fit` décompressé sur disque** : un `.fit.gz` est décompressé en mémoire.
- **Ne jamais écraser un fichier existant** sans `--force`.
- **Tous les labels de sortie en français.**
- **Séparation des modules** : chemins / nommage / archivage dans `file_manager.py`, GPS / GPX dans `gpx_exporter.py`, parsing + formatage + CLI dans `extractor.py`.
- **Publier et archiver via `export_activity()`** : annuler les sorties et restaurer les anciennes en cas d’erreur gérée, archivage compris. Ne supprimer la source qu’en dernier.
- **`--details` reste optionnel** : pas de RR bruts ni de séries intégrales ; moyennes d’échantillons explicitement non pondérées.

La liste complète et son rationale sont dans [`docs/SPEC.md`](docs/SPEC.md) et [`CLAUDE.md`](CLAUDE.md).

## Style

- Python 3.10+, bibliothèque standard privilégiée.
- Code et commentaires alignés sur l'existant ; messages de commit en français, format [Conventional Commits](https://www.conventionalcommits.org/fr/) (`feat(gpx): …`, `fix(file_manager): …`).

## Licence

En contribuant, vous acceptez que votre code soit distribué sous [licence MIT](LICENSE).
