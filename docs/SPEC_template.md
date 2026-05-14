# 🧩 SPEC.md — Technical Living Spec

> ⚠️ Document maintenu en rétro-spécification.
> Sert de **référence unique pour comprendre, modifier et faire évoluer le système**.
> Doit rester **simple, à jour et exploitable par une IA**.

---

## 1. Overview

**Project name** :
**Objective** : (le "pourquoi", 1-3 phrases max)
**Main stack** :
**Last update** : YYYY-MM-DD

### High-level behavior
- Inputs :
- Outputs :
- Core use cases :

---

## 2. Architecture

### Project structure
```
project/
├── src/
│   └── ...
└── ...
```

### Data flow
Entrée → traitement → sortie (décrire simplement)

---

## 3. Components

### `module-name`

- **Role** :
- **Files** :
- **Public interface** :
- **Dependencies** :
- **Side effects / specifics** :

---

## 4. Core Logic (CRITICAL)

Décrire ici **les règles métier et logiques importantes**.

- Règle 1 :
- Règle 2 :
- Algorithmes clés :
- Hypothèses :

👉 Cette section évite que l’IA réécrive n’importe quoi.

---

## 5. Contracts & Interfaces

### API / Endpoints
```
VERB /route
Body: { ... }
Response: { ... }
```

### Data model
```ts
// Types principaux
```

---

## 6. Configuration

### Environment variables
| Variable | Usage | Default |
|----------|-------|---------|

---

## 7. Technical Decisions (ADR light)

| Decision | Why | Alternative rejected |
|----------|-----|---------------------|

---

## 8. Patterns & Conventions

- Naming :
- Error handling :
- Architecture patterns :
- Code organization rules :

---

## 9. Invariants (VERY IMPORTANT)

Ce qui **ne doit jamais être cassé** :

- Invariant 1
- Invariant 2
- Contrainte critique

👉 C’est la protection contre les dérives de l’IA.

---

## 10. Out of Scope

- Pas de X (raison)
- Pas de Y

---

## 11. Known Issues & Tech Debt

- [ ] Point fragile
- [ ] Refactor à prévoir

---

## 12. Evolution History

| Date | Change |
|------|--------|

---

## 13. Next Improvements

- Idée 1
- Optimisation possible

---

## 14. AI Instructions (MANDATORY)

### How to update this project
- Toujours respecter les invariants
- Ne pas casser les interfaces existantes
- Faire des modifications minimales et ciblées

### Before coding
- Lire ce document
- Identifier les composants impactés

### When modifying code
- Mettre à jour cette spec
- Justifier les changements importants

### Forbidden
- Réécrire entièrement un module sans raison
- Introduire une dépendance lourde sans justification
