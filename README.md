# 🎓 Système Intelligent de Planification des Surveillances d'Examens

<div align="center">

![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)
![Flask](https://img.shields.io/badge/Flask-3.0+-green.svg)
![OR-Tools](https://img.shields.io/badge/OR--Tools-CP--SAT-orange.svg)
![SQLite](https://img.shields.io/badge/SQLite-3-lightgrey.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

**Solution d'optimisation avancée pour l'attribution équitable des surveillances d'examens universitaires**

[Fonctionnalités](#-fonctionnalités-principales) • [Algorithme](#-algorithme-doptimisation) • [Installation](#-installation) • [Documentation](#-documentation-api)

</div>

---

## 📋 Description

Système automatisé de planification des surveillances d'examens universitaires utilisant **OR-Tools CP-SAT** pour une optimisation intelligente. Le système garantit une **équité absolue** entre enseignants tout en respectant les contraintes institutionnelles et les préférences individuelles.

### 🎯 Problématique Résolue

Dans un contexte universitaire, l'attribution manuelle des surveillances pose plusieurs défis :
- ⚖️ **Inéquité** : Répartition déséquilibrée des charges entre enseignants
- 📊 **Complexité** : Gestion de centaines d'enseignants et créneaux
- 🔄 **Répétitivité** : Tâche chronophage à chaque session d'examens
- 📅 **Conflits** : Non-respect des vœux et surcharges

Notre solution apporte une **automatisation intelligente** avec garanties mathématiques d'équité.

---

## ✨ Fonctionnalités Principales

### 🤖 Optimisation Intelligente (OR-Tools CP-SAT)

| Fonctionnalité | Description |
|----------------|-------------|
| **Équité Absolue** | Tous les enseignants d'un même grade ont **exactement** le même nombre de surveillances (différence = 0) |
| **Participation Universelle** | Garantie que **100% des enseignants** participants ont au moins 1 surveillance |
| **Quotas Dynamiques** | Calcul automatique des quotas optimaux respectant les limites de grade |
| **Équilibrage Inter-Grades** | Distribution équilibrée entre grades (ex: MA à 6/7, VA à 3/4) |
| **Respect des Vœux** | Prise en compte maximale des préférences de non-surveillance |
| **Concentration Temporelle** | Minimisation du nombre de jours de surveillance par enseignant |

### 📊 Gestion Complète des Données

- 📁 **Import/Export** : Support Excel, CSV avec normalisation automatique
- 👥 **Gestion Enseignants** : Profils complets avec grades et quotas
- 📅 **Gestion Sessions** : Dates automatiques basées sur les créneaux
- 🏫 **Gestion Salles** : Attribution intelligente avec responsables
- ✉️ **Notifications** : Génération automatique de convocations par email

### 📈 Analyse et Reporting

- 📊 **Statistiques Détaillées** : Répartition par grade, jour, séance
- 📋 **Exports Multiples** : CSV global, par jour, par enseignant
- 🔍 **Diagnostic** : Analyse de faisabilité en temps réel
- 📉 **Historique** : Suivi multi-sessions avec quotas ajustés

---

## 🧮 Algorithme d'Optimisation

### Architecture CP-SAT (Constraint Programming - SAT Solver)

Notre algorithme utilise **Google OR-Tools CP-SAT**, un solveur de contraintes de classe mondiale, avec une hiérarchie de contraintes optimisée.

### 🔒 Contraintes HARD (Éliminatoires)

Ces contraintes **DOIVENT** être satisfaites, sinon le problème est déclaré infaisable :

| ID | Contrainte | Description |
|----|------------|-------------|
| **H1** | Couverture Complète | Chaque créneau reçoit exactement le nombre requis de surveillants (2 titulaires/salle + réserves) |
| **H2** | Non-Responsabilité | Un enseignant ne peut pas surveiller une salle dont il est responsable |
| **H3** | Quotas Maximum | Aucun enseignant ne dépasse son quota (calculé ≤ quota_grade) |
| **H4** | Équité Absolue | Tous les enseignants d'un même grade ont **exactement** le même nombre de surveillances |
| **H5** | Participation Minimale | Tous les enseignants participants ont **AU MOINS 1** surveillance |

### 🎯 Contraintes SOFT (Optimisation)

Ces contraintes sont optimisées par ordre de priorité décroissante :

| Priorité | Poids | Contrainte | Objectif |
|----------|-------|------------|----------|
| **S1** | 100 | Respect des Vœux | Maximiser le respect des préférences de non-surveillance |
| **S2** | 50 | Concentration Jours | Minimiser le nombre de jours différents par enseignant |
| **S3** | 30 | Équilibrage Grades | Équilibrer les ratios (réalisé/quota) entre tous les grades |
| **S4** | 10 | Écarts Quotas | Minimiser les écarts individuels par rapport aux quotas |
| **S5** | 8 | Priorités Historiques | Favoriser les enseignants ayant moins surveillé auparavant |
| **S6** | 1 | Présence Responsables | Préférence légère pour présence des responsables |

### ⚡ Optimisations de Performance

```python
✓ Calcul de quotas optimaux automatique
✓ Filtrage intelligent (concentration uniquement si quota > 2)
✓ Suppression des variables intermédiaires
✓ Détection de symétries (niveau 2)
✓ SAT inprocessing activé
✓ Temps maximum : 10 minutes
✓ Parallélisation : 8 workers
```

### 📊 Résultats Garantis

L'algorithme garantit les propriétés suivantes :

```
✅ Équité parfaite : diff_max_par_grade = 0
✅ Participation : 100% des enseignants ≥ 1 surveillance
✅ Respect quotas : quota_réalisé ≤ quota_grade (∀ enseignants)
✅ Équilibrage : |ratio_grade_A - ratio_grade_B| ≤ 25%
✅ Faisabilité : Analyse pré-optimisation avec diagnostic détaillé
```

---

## 🚀 Installation

### Prérequis

```bash
Python 3.11+
SQLite 3
Node.js (optionnel, pour le frontend)
```

### Installation Rapide

```bash
# 1. Cloner le dépôt
git clone https://github.com/MaherxBlhasn/Compet_Univ.git
cd Compet_Univ

# 2. Créer l'environnement virtuel
python -m venv venv

# Windows
.\venv\Scripts\activate

# Unix/macOS
source venv/bin/activate

# 3. Installer les dépendances
pip install -r requirements.txt

# 4. Lancer l'application
python app.py
```

L'application sera accessible sur `http://localhost:5000` 🎉

### Installation des Dépendances Principales

```bash
pip install flask==3.0.0
pip install pandas==2.1.3
pip install ortools==9.8.3296
pip install openpyxl==3.1.2
```

---

## 📁 Architecture du Projet

```
Compet_Univ/
│
├── 🚀 app.py                          # Application Flask principale
├── ⚙️  config.py                       # Configuration globale
├── 📦 requirements.txt                 # Dépendances Python
├── 📄 README.md                        # Documentation
│
├── 💾 database/                        # Couche Base de Données
│   ├── create_database.py              # Schéma et initialisation
│   ├── database.py                     # Connexion et gestion
│   └── surveillance.db                 # Base SQLite (auto-générée)
│
├── 🛣️  routes/                         # API REST Flask
│   ├── session_routes.py               # Gestion des sessions
│   ├── enseignant_routes.py            # Gestion des enseignants
│   ├── creneau_routes.py               # Gestion des créneaux
│   ├── voeu_routes.py                  # Gestion des vœux
│   ├── affectation_routes.py           # Résultats d'affectation
│   ├── optimize_routes.py              # 🎯 Lancement optimisation
│   ├── quota_enseignant_routes.py      # Calcul et export quotas
│   ├── upload_routes.py                # Import Excel/CSV
│   ├── email_routes.py                 # Envoi de convocations
│   └── statistics_routes.py            # Statistiques et analyses
│
├── 🧮 scripts/                         # Algorithmes et Utilitaires
│   ├── optimize_example.py             # 🔥 Algorithme CP-SAT principal
│   ├── surveillance_stats.py           # Génération statistiques
│   ├── quota_enseignant_module.py      # Calcul quotas par enseignant
│   ├── generate_jour_seance.py         # Génération mappings jour/séance
│   ├── diagnostic.py                   # Analyse de faisabilité
│   ├── infeasibility_diagnostic.py     # Diagnostic problèmes
│   └── check_quotas.py                 # Vérification cohérence
│
├── 📊 results/                         # Résultats d'Optimisation
│   ├── quota_enseignant.csv            # Quotas par enseignant
│   ├── affectations_global.csv         # Toutes les affectations
│   ├── affectations_jour_X.csv         # Affectations par jour
│   └── convocation_csv/                # Convocations individuelles
│       └── session_X/
│           └── convocation_[ID]_[NOM]_session_X.csv
│
├── 📤 uploads/                         # Fichiers Importés
│   ├── enseignants.xlsx                # Import enseignants
│   ├── creneaux.xlsx                   # Import créneaux
│   └── voeux.xlsx                      # Import vœux
│
├── 🧪 tests/                           # Tests Unitaires
│   └── test_optimization.py            # Tests algorithme
│
└── 🎨 assets/                          # Ressources Statiques
    └── templates/                      # Templates email
```

### 🔑 Fichiers Clés

| Fichier | Rôle | Importance |
|---------|------|------------|
| `scripts/optimize_example.py` | **Cœur de l'algorithme CP-SAT** | ⭐⭐⭐⭐⭐ |
| `routes/optimize_routes.py` | API de lancement d'optimisation | ⭐⭐⭐⭐ |
| `database/create_database.py` | Schéma base de données | ⭐⭐⭐⭐ |
| `routes/upload_routes.py` | Import automatisé des données | ⭐⭐⭐ |

## Utilisation

1. Lancez l'application Flask :
```bash
python app.py
```
L'application créera automatiquement la base de données si elle n'existe pas.

2. Pour lancer l'optimisation manuellement :
```bash
python scripts/optimize_example.py
```

3. Les résultats seront générés dans le dossier `results/` sous forme de fichiers CSV :
   - `affectations_global.csv` : Toutes les affectations
   - `affectations_jour_X.csv` : Affectations par jour
   - `convocation_[NOM]_[PRENOM].csv` : Convocations individuelles

## Format des créneaux

Les créneaux sont organisés en 4 séances :
- S1 : 08h00 - 09h30
- S2 : 10h00 - 11h30
- S3 : 12h00 - 13h30
- S4 : 14h00 - 16h00

## Contraintes et règles d'affectation

- Chaque grade a un quota maximum de surveillances
- Les enseignants peuvent soumettre des vœux de non-surveillance
- Un enseignant ne peut pas surveiller deux examens en même temps
- Une répartition équitable est privilégiée entre les enseignants
- Les responsables d'examen sont automatiquement affectés à leurs salles

## Export des résultats

Les résultats sont exportés sous plusieurs formats :
1. Fichier global avec toutes les affectations
2. Fichiers par jour d'examen
3. Convocations individuelles par enseignant
4. Rapport d'équité montrant la répartition des surveillances

## Licence

[Type de licence]

## Auteurs

[Vos noms et contacts]