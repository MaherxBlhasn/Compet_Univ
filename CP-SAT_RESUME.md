# Résumé CP-SAT (Constraint Programming SAT Solver)

---

## 🧮 Fonctionnement général CP-SAT

```mermaid
graph TD
    A[Définir variables de décision] --> B[Ajouter contraintes HARD (obligatoires)]
    B --> C[Ajouter contraintes SOFT (optimisables)]
    C --> D[Définir fonction objectif]
    D --> E[Appeler solveur CP-SAT]
    E --> F[Obtenir solution optimale ou faisable]
```

---

## 🔒 Contraintes HARD (obligatoires)
- **Doivent être respectées**
- Exemples :
  - Couverture totale (ex : chaque créneau doit avoir X surveillants)
  - Quotas max (ex : un enseignant ne peut surveiller plus que son quota)
  - Équité stricte (ex : écart max entre enseignants)

**Code (Python/OR-Tools)** :
```python
model.Add(x1 + x2 == 2)  # Couverture
model.Add(x3 <= quota)    # Quota max
```

---

## 🎨 Contraintes SOFT (optimisables)
- **Peuvent être violées si nécessaire**
- Sont ajoutées dans la fonction objectif avec un poids
- Exemples :
  - Dispersion (éviter séances consécutives)
  - Préférence (favoriser certains enseignants)

**Code (Python/OR-Tools)** :
```python
penalty = model.NewIntVar(0, 100, 'penalty')
model.Add(penalty == (x1 + x2) * 10)
objective_terms.append(penalty * 3)  # Poids 3
```

---

## 🎯 Fonction objectif
- **Minimiser la somme des pénalités soft + écarts**
- Exemple :
```python
model.Minimize(sum(objective_terms))
```

---

## ⚡ Résolution
- Appel du solveur :
```python
solver = cp_model.CpSolver()
status = solver.Solve(model)
```
- Statut : OPTIMAL, FEASIBLE, INFEASIBLE
- Extraction de la solution :
```python
if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
    # Lire les valeurs des variables
```

---

## 📚 Documentation rapide
- **Variables** : model.NewBoolVar(), model.NewIntVar()
- **Contraintes HARD** : model.Add(...)
- **Contraintes SOFT** : model.Add(...), objective_terms.append(...)
- **Objectif** : model.Minimize(...)
- **Solveur** : cp_model.CpSolver()

---

## 🔗 Référence
- [OR-Tools CP-SAT](https://developers.google.com/optimization/cp/cp_solver)
