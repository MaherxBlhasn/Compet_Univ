# Système de Planification des Surveillances d'Examens

Ce projet est un système automatisé de planification des surveillances d'examens utilisant SQLite comme base de données. Il permet d'optimiser l'attribution des surveillances aux enseignants en tenant compte de différentes contraintes comme les quotas par grade, les vœux des enseignants, et les créneaux horaires.

## Fonctionnalités

- Attribution automatique des surveillances d'examens
- Gestion des contraintes par grade d'enseignant
- Prise en compte des vœux de non-surveillance
- Export des résultats en format CSV
- Génération de plannings par jour et par enseignant
- Gestion des séances (S1, S2, S3, S4) et des jours d'examen
- Optimisation avec OR-Tools pour une répartition équitable

## Configuration requise

- Python 3.11 ou supérieur
- SQLite3
- Les packages Python listés dans `requirements.txt`

## Installation

1. Clonez le dépôt :
```bash
git clone https://github.com/MaherxBlhasn/Compet_Univ.git
cd SQLite
```

2. Créez un environnement virtuel Python :
```bash
python -m venv venv
source venv/bin/activate  # Sur Unix/macOS
# ou
.\venv\Scripts\activate  # Sur Windows
```

3. Installez les dépendances :
```bash
pip install -r requirements.txt
```

## Structure du projet

```
├── app.py                    # Application Flask principale
├── config.py                 # Configuration du projet
├── requirements.txt          # Dépendances Python
├── database/                 # Modules de base de données
│   ├── create_database.py    # Création de la base de données
│   └── database.py           # Connexion et initialisation
├── routes/                   # Routes API Flask
│   ├── affectation_routes.py
│   ├── creneau_routes.py
│   ├── enseignant_routes.py
│   ├── grade_routes.py
│   ├── optimize_routes.py
│   ├── quota_enseignant_routes.py
│   ├── salle_par_creneau_routes.py
│   ├── session_routes.py
│   ├── upload_routes.py
│   └── voeu_routes.py
├── scripts/                  # Scripts utilitaires
│   ├── optimize_example.py   # Algorithme d'optimisation CP-SAT
│   ├── generate_jour_seance.py
│   ├── check_quotas.py
│   ├── check_tables.py
│   ├── diagnostic.py
│   ├── infeasibility_diagnostic.py
│   ├── surveillance_stats.py
│   └── quota_enseignant_module.py
├── exports/                  # Scripts d'export
│   └── export_tables_to_csv.py
├── deprecated/               # Fichiers obsolètes
├── results/                  # Résultats d'optimisation (CSV)
├── uploads/                  # Fichiers uploadés
├── tests/                    # Tests unitaires
└── assets/                   # Ressources statiques
```

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