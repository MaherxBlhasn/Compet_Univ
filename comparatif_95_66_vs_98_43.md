# Comparatif des configurations CP-SAT (95.66% vs 98.43%)

Ce document détaille les différences majeures entre les deux versions du planificateur de surveillances CP-SAT :
- `optimize_95_66_stable_version.py` (score : **95.66%**)
- `optimize_98_43_non_tested.py` (score : **98.43%**)

---

## 1. Ordre des contraintes HARD

| Version 95.66%                      | Version 98.43%                      |
|-------------------------------------|-------------------------------------|
| H1 : Couverture créneaux            | H1 : Couverture créneaux            |
| H3A : Respect quotas max (ajustés)  | H2A : Équité stricte par grade      |
| H2A : Équité stricte par grade      | H3A : Respect quotas max (ajustés)  |
| H2B/H2C : Pré-filtres               | H2B/H2C : Pré-filtres               |

- **95.66%** : H1 > H3A > H2A
- **98.43%** : H1 > H2A > H3A

---

## 2. Poids des contraintes SOFT (fonction de minimisation)

| Terme                | 95.66% | 98.43% |
|----------------------|--------|--------|
| abs_delta (Δquota)   |   7    |   9    |
| S1 (dispersion)      |   5    |   6    |
| S2 (présence resp.)  |   1    |  10    |
| S3 (priorité quotas) |  10    |   8    |

- **95.66%** : abs_delta×7, S1×5, S2×1, S3×10
- **98.43%** : abs_delta×9, S1×6, S2×10, S3×8

---

## 3. Fonction de minimisation

Les deux versions minimisent une somme pondérée de pénalités :

- **abs_delta** : Écart absolu entre quota affecté et quota cible pour chaque enseignant
- **S1** : Dispersion des surveillances dans la même journée
- **S2** : Pénalité si le responsable de salle n'est pas affecté à son créneau
- **S3** : Pénalité pour affecter trop les enseignants avec quotas ajustés faibles

La différence réside dans les **poids** attribués à chaque terme (voir tableau ci-dessus).

---

## 4. Implémentation des contraintes

- **HARD** :
  - Les deux versions appliquent H2B (vœux) et H2C (responsable) comme pré-filtres lors de la création des variables.
  - La version 98.43% renforce H3A avec un check post-somme (aucun enseignant ne dépasse son quota après toutes affectations).

- **SOFT** :
  - Les deux versions utilisent les mêmes pénalités, mais la version 98.43% accorde une importance beaucoup plus forte à la présence des responsables (S2).

---

## 5. Résumé des différences majeures

- **Ordre des contraintes HARD** :
  - 95.66% : Priorité à la couverture puis quotas, puis équité
  - 98.43% : Priorité à la couverture puis équité, puis quotas
- **Poids des pénalités SOFT** :
  - 98.43% accorde plus d'importance à la présence des responsables et à l'écart de quota
- **Renforcement H3A** :
  - 98.43% ajoute un contrôle post-somme sur le quota enseignant

---

## 6. Impact sur le score

- **95.66%** : Moins de priorité à l'équité et à la présence responsable
- **98.43%** : Meilleure équité et meilleure couverture des responsables, d'où un score global supérieur

---

## 7. Fichiers comparés
- `scripts/optimize_95_66_stable_version.py`
- `scripts/optimize_98_43_non_tested.py`

---

*Document généré automatiquement le 18/10/2025.*
