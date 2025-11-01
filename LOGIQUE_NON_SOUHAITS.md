# 🧮 Logique de Calcul des Non-Souhaits Autorisés

## 📋 Contexte et Objectif

### **Problème à résoudre:**
- Un enseignant peut **ne PAS souhaiter** certains créneaux (contrairement aux voeux = souhaits)
- Si trop de non-souhaits sont autorisés → problème **INFAISABLE** (pas assez de disponibilités)
- Si pas assez de non-souhaits autorisés → enseignants **trop contraints** (pas de flexibilité)

### **Objectif:**
Calculer le **nombre optimal de créneaux de non-souhaits autorisés par grade** pour **garantir l'existence d'une solution** lors de l'optimisation.

---

## 🎯 Logique Implémentée

### **Principe de base:**
> **Plus le quota d'un grade est élevé, plus il faut autoriser de non-souhaits**

**Pourquoi?**
- Grade bas (PR, MC, V): quota = 2 → peu de surveillances → forte probabilité de trouver une solution même avec peu de créneaux disponibles
- Grade élevé (AC, PTC, PES): quota = 12 → beaucoup de surveillances → besoin de plus de flexibilité pour trouver une solution

---

## 📊 Formule Détaillée

```python
def calculate_non_souhaits_allowance(self, quotas: Dict) -> Dict[str, int]:
    nb_creneaux_total = 311  # Exemple: nombre total de créneaux dans la session
    max_ratio = 0.30  # 30% max des créneaux peuvent être non-souhaités
    
    for grade, data in quotas.items():
        quota = data['quota']  # Ex: MA = 5 surveillances
        
        # CALCUL EN 3 ÉTAPES:
        
        # 1. Limite par ratio global (30% des créneaux)
        max_by_ratio = floor(max_ratio × nb_creneaux_total)
        # Exemple: floor(0.30 × 311) = 93 créneaux
        
        # 2. Limite par quota (proportionnelle au quota)
        max_by_quota = ceil(quota × 1.5)
        # Exemple MA: ceil(5 × 1.5) = 8 créneaux
        # Exemple PTC: ceil(12 × 1.5) = 18 créneaux
        
        # 3. Prendre le minimum des deux + minimum absolu de 2
        allowed = max(2, min(max_by_ratio, max_by_quota))
        
        non_souhaits_allowance[grade] = allowed
```

---

## 🔢 Exemple Concret (Session 1)

### **Données:**
- **311 créneaux** au total
- **Ratio max: 30%** → max 93 créneaux non-souhaités
- **Quotas par grade:**

| Grade | Quota | Calcul | Non-souhaits autorisés |
|-------|-------|--------|------------------------|
| **V** | 2 | min(93, ceil(2×1.5)) = min(93, 3) = **3** | ✅ 3 créneaux |
| **PR** | 2 | min(93, ceil(2×1.5)) = min(93, 3) = **3** | ✅ 3 créneaux |
| **MC** | 2 | min(93, ceil(2×1.5)) = min(93, 3) = **3** | ✅ 3 créneaux |
| **MA** | 5 | min(93, ceil(5×1.5)) = min(93, 8) = **8** | ✅ 8 créneaux |
| **AS** | 9 | min(93, ceil(9×1.5)) = min(93, 14) = **14** | ✅ 14 créneaux |
| **EX** | 9 | min(93, ceil(9×1.5)) = min(93, 14) = **14** | ✅ 14 créneaux |
| **AC** | 12 | min(93, ceil(12×1.5)) = min(93, 18) = **18** | ✅ 18 créneaux |
| **PTC** | 12 | min(93, ceil(12×1.5)) = min(93, 18) = **18** | ✅ 18 créneaux |
| **PES** | 12 | min(93, ceil(12×1.5)) = min(93, 18) = **18** | ✅ 18 créneaux |

### **Interprétation:**
- **Professeurs (PR)**: Seulement 2 surveillances → 3 non-souhaits suffisent (97.5% des créneaux disponibles)
- **Assistants Contractuels (AC)**: 12 surveillances → 18 non-souhaits nécessaires (94.5% des créneaux disponibles)

---

## 🧠 Justification Mathématique

### **Formule: `allowed = min(30% × nb_creneaux, quota × 1.5)`**

#### **Partie 1: `30% × nb_creneaux`**
- Limite **globale** pour éviter que les enseignants bloquent trop de créneaux
- Si tous les enseignants d'un grade mettent le maximum → ne bloque que 30% des créneaux

#### **Partie 2: `quota × 1.5`**
- Limite **proportionnelle** au quota
- Coefficient 1.5 = marge de sécurité
- **Logique:**
  - Si quota = 5 → besoin de 5 créneaux disponibles minimum
  - Avec 1.5: `5 × 1.5 = 7.5 → 8 créneaux` non-souhaités autorisés
  - Reste: `311 - 8 = 303` créneaux disponibles (largement suffisant)

#### **Partie 3: `max(2, ...)`**
- Minimum absolu de **2 non-souhaits** pour garantir une flexibilité minimale
- Même pour les grades avec quota = 1

---

## 💾 Modification Manuelle par l'Utilisateur

### **Méthode 1: Via CSV (Recommandée)**

1. **Génération du fichier:**
```bash
GET /api/decision-support/recommendations/1?export_csv=true
```

2. **Fichier généré:** `results/quotas_proposes_session_1.csv`
```csv
code_smartex_ens,nom_ens,prenom_ens,email_ens,grade_code_ens,quota_propose
100,Dupont,Jean,jean.dupont@,MA,5
101,Martin,Marie,marie.martin@,PR,2
```

3. **Modification manuelle:**
- L'utilisateur peut ouvrir le CSV dans Excel
- Modifier la colonne `quota_propose` pour chaque enseignant
- Exemple: Augmenter le quota de Jean Dupont de 5 à 7

4. **Réimportation:**
```python
# À implémenter dans le frontend
# Upload du CSV modifié → met à jour les quotas individuels
```

### **Méthode 2: Via API (Application directe)**

```bash
# Appliquer les quotas par grade
POST /api/decision-support/apply/1
Content-Type: application/json
{
  "quotas": {
    "MA": 6,    # Modifié: 5 → 6
    "PR": 3,    # Modifié: 2 → 3
    "MC": 2,
    "AS": 9,
    "AC": 12,
    "PTC": 12,
    "PES": 12,
    "V": 2,
    "EX": 9
  }
}
```

### **Méthode 3: Via Interface (Frontend)**

**Workflow proposé:**

1. **Page: "Module d'Aide à la Décision"**
   ```
   [Bouton: Générer Recommandations]
   ```

2. **Affichage des recommandations:**
   ```
   ┌─────────────────────────────────────────────────────┐
   │ Recommandations pour Session 1                      │
   ├─────────────┬─────────┬──────────┬──────────────────┤
   │ Grade       │ Actuel  │ Proposé  │ Non-souhaits max │
   ├─────────────┼─────────┼──────────┼──────────────────┤
   │ PR          │    2    │    2     │        3         │
   │ MC          │    2    │    2     │        3         │
   │ V           │    2    │    2     │        3         │
   │ MA          │    7    │    5 ⬇️  │        8         │
   │ AS          │    9    │    9     │       14         │
   │ EX          │    9    │    9     │       14         │
   │ AC          │   12    │   12     │       18         │
   │ PTC         │   12    │   12     │       18         │
   │ PES         │   12    │   12     │       18         │
   └─────────────┴─────────┴──────────┴──────────────────┘
   
   Capacité actuelle: 777 surveillances
   Capacité requise:  716 surveillances
   Excédent:          +61 surveillances ✅
   
   [Modifier manuellement] [Appliquer recommandations]
   ```

3. **Mode édition:**
   - Cliquer sur "Modifier manuellement"
   - Les champs deviennent éditables
   - Validation en temps réel (quota ≥ 1, capacité ≥ requise)

4. **Application:**
   - Bouton "Appliquer" → appelle `POST /api/decision-support/apply/1`
   - Confirmation: "Quotas mis à jour avec succès!"

---

## 🎓 Exemple Complet avec Modification Manuelle

### **Scénario:**
L'université décide que les Maîtres Assistants (MA) doivent faire **6 surveillances** au lieu de 5.

### **Étape 1: Voir les recommandations**
```bash
curl http://localhost:5000/api/decision-support/recommendations/1
```
**Résultat:** MA = 5 (recommandé)

### **Étape 2: Modifier manuellement**
```bash
curl -X POST http://localhost:5000/api/decision-support/apply/1 \
  -H "Content-Type: application/json" \
  -d '{
    "quotas": {
      "MA": 6,
      "PR": 2,
      "MC": 2,
      "AS": 9,
      "AC": 12,
      "PTC": 12,
      "PES": 12,
      "V": 2,
      "EX": 9
    }
  }'
```

### **Étape 3: Vérifier la nouvelle capacité**
```bash
curl http://localhost:5000/api/decision-support/statistics/1
```
**Résultat:**
- Capacité avant: 57 × 5 = 285 (MA)
- Capacité après: 57 × 6 = 342 (MA)
- Capacité totale: 776 + 57 = **833 surveillances** (encore largement suffisant)

### **Étape 4: Recalculer les non-souhaits**
Le système recalcule automatiquement:
- MA: `min(93, ceil(6×1.5)) = min(93, 9) = 9` créneaux non-souhaités autorisés (au lieu de 8)

---

## 📊 Validation de la Logique

### **Test 1: Grade avec quota bas (PR = 2)**
```
Quota = 2 surveillances
Non-souhaits autorisés = 3 créneaux
Créneaux disponibles = 311 - 3 = 308
Probabilité de faisabilité = 308/2 = 154× le quota ✅ EXCELLENTE
```

### **Test 2: Grade avec quota moyen (MA = 5)**
```
Quota = 5 surveillances
Non-souhaits autorisés = 8 créneaux
Créneaux disponibles = 311 - 8 = 303
Probabilité de faisabilité = 303/5 = 60.6× le quota ✅ TRÈS BONNE
```

### **Test 3: Grade avec quota élevé (PTC = 12)**
```
Quota = 12 surveillances
Non-souhaits autorisés = 18 créneaux
Créneaux disponibles = 311 - 18 = 293
Probabilité de faisabilité = 293/12 = 24.4× le quota ✅ BONNE
```

### **Conclusion:**
Même dans le pire cas (PTC), il y a **24 fois plus de créneaux disponibles que de surveillances requises** → garantit la faisabilité!

---

## 🔧 Paramètres Configurables

### **Dans le code:**
```python
class DecisionSupportModule:
    def __init__(self, session_id):
        # Paramètres modifiables
        self.max_non_souhaits_ratio = 0.30  # 30% max
        self.quota_multiplier = 1.5          # Coefficient pour max_by_quota
```

### **Via API:**
```bash
GET /api/decision-support/recommendations/1?max_non_souhaits_ratio=0.40
```

---

## 🎯 Résumé de la Logique

| Aspect | Méthode | Résultat |
|--------|---------|----------|
| **Calcul auto** | `min(30%×nb_creneaux, quota×1.5)` | Non-souhaits optimaux par grade |
| **Modification manuelle** | CSV exporté → édition → réimport | Quotas personnalisés par enseignant |
| **Application** | API `POST /apply` | Mise à jour table `grade` |
| **Validation** | Recalcul capacité vs requis | Garantie faisabilité |
| **Flexibilité** | Paramètres configurables | Adaptation par contexte |

---

## ✅ Avantages de cette Approche

1. **Automatique:** Calcul intelligent sans intervention manuelle
2. **Proportionnelle:** Plus le quota est élevé, plus de flexibilité
3. **Sécurisée:** Limites min/max pour éviter les extrêmes
4. **Flexible:** Modification manuelle possible après génération
5. **Garantie:** Assure la faisabilité mathématique du problème
6. **Transparente:** Tous les calculs sont explicités et vérifiables

---

## 🚀 Prochaines Améliorations (Optionnelles)

1. **Analyse des voeux existants:**
   - Calculer combien de non-souhaits sont déjà présents
   - Ajuster les limites en conséquence

2. **Simulation de faisabilité:**
   - Avant d'appliquer, simuler si le problème est faisable
   - Alerter si capacité insuffisante

3. **Historique:**
   - Sauvegarder l'historique des modifications
   - Permettre de revenir en arrière

4. **Optimisation par enseignant:**
   - Au lieu de quotas par grade, calculer des quotas individuels optimaux
   - Prendre en compte les préférences spécifiques
