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
python3 extractor.py mon_activite.fit --stdout   # n'écrit aucun fichier
```

## Invariants à respecter

Ces règles portent la conception du projet — une PR qui les enfreint sera refusée, sauf discussion préalable en issue :

- **Une seule dépendance** : `fitparse`. Le GPX est généré avec `xml.etree.ElementTree` de la stdlib — pas de `gpxpy` ni d'équivalent.
- **Extraction générique** : itérer sur tous les champs d'un message FIT, jamais sur une liste de noms figée (compatibilité avec les futurs matériels).
- **Toujours passer `StandardUnitsDataProcessor()`** à fitparse (km/h, mètres).
- **Ignorer les champs `unknown_XXX`** : propriétaires, non documentés, bruit pour une IA.
- **HRV : RMSSD et SDNN uniquement** — jamais les intervalles RR bruts, qui dépassent 10 000 points.
- **`None` → `"-"`** : une donnée manquante ne doit jamais faire échouer le rendu.
- **Ne jamais écrire un `.fit` décompressé sur disque** : un `.fit.gz` est décompressé en mémoire.
- **Ne jamais écraser un fichier existant** sans `--force`.
- **Tous les labels de sortie en français.**
- **Séparation des modules** : chemins / nommage / archivage dans `file_manager.py`, GPS / GPX dans `gpx_exporter.py`, parsing + formatage + CLI dans `extractor.py`.
- **Le `.fit` source n'est déplacé qu'après écriture réussie du `.md`.**

La liste complète et son rationale sont dans [`docs/SPEC.md`](docs/SPEC.md) et [`CLAUDE.md`](CLAUDE.md).

## Style

- Python 3.10+, bibliothèque standard privilégiée.
- Code et commentaires alignés sur l'existant ; messages de commit en français, format [Conventional Commits](https://www.conventionalcommits.org/fr/) (`feat(gpx): …`, `fix(file_manager): …`).

## Licence

En contribuant, vous acceptez que votre code soit distribué sous [licence MIT](LICENSE).
