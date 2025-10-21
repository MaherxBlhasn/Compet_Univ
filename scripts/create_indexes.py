#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Script pour créer des index sur la base de données
afin d'accélérer les requêtes d'optimisation

Exécuter ce script une seule fois pour créer les index
"""

import sqlite3
import sys
import os

# Ajouter le dossier parent au path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DB_NAME = 'surveillance.db'


def create_performance_indexes():
    """Créer les index pour améliorer les performances"""
    print("\n" + "="*60)
    print("CRÉATION DES INDEX DE PERFORMANCE")
    print("="*60)
    
    if not os.path.exists(DB_NAME):
        print(f"\n❌ Base de données '{DB_NAME}' introuvable!")
        return False
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    indexes = [
        # Index sur affectation
        ("idx_affectation_session", "affectation", "(id_session, code_smartex_ens)"),
        ("idx_affectation_creneau", "affectation", "(creneau_id)"),
        
        # Index sur creneau
        ("idx_creneau_session", "creneau", "(id_session, dateExam, h_debut)"),
        ("idx_creneau_enseignant", "creneau", "(enseignant)"),
        
        # Index sur voeu
        ("idx_voeu_session", "voeu", "(id_session, code_smartex_ens)"),
        ("idx_voeu_jour_seance", "voeu", "(jour, seance)"),
        
        # Index sur salle_par_creneau
        ("idx_salle_par_creneau_session", "salle_par_creneau", "(id_session, dateExam, h_debut)"),
        
        # Index sur quota_enseignant
        ("idx_quota_session", "quota_enseignant", "(id_session, code_smartex_ens)"),
    ]
    
    created = 0
    already_exists = 0
    errors = 0
    
    for index_name, table_name, columns in indexes:
        try:
            # Vérifier si l'index existe déjà
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='index' AND name=?
            """, (index_name,))
            
            if cursor.fetchone():
                print(f"   ⏭️  Index '{index_name}' existe déjà")
                already_exists += 1
            else:
                # Créer l'index
                sql = f"CREATE INDEX {index_name} ON {table_name} {columns}"
                cursor.execute(sql)
                print(f"   ✓ Index '{index_name}' créé sur {table_name}{columns}")
                created += 1
                
        except sqlite3.Error as e:
            print(f"   ❌ Erreur pour '{index_name}': {e}")
            errors += 1
    
    conn.commit()
    conn.close()
    
    print("\n" + "="*60)
    print("RÉSUMÉ")
    print("="*60)
    print(f"✓ {created} index créés")
    print(f"⏭️  {already_exists} index existants")
    if errors > 0:
        print(f"❌ {errors} erreurs")
    print("\n💡 Les requêtes SQL devraient maintenant être plus rapides!")
    print("="*60 + "\n")
    
    return errors == 0


def analyze_database_performance():
    """Analyser les performances de la base de données"""
    print("\n" + "="*60)
    print("ANALYSE DES PERFORMANCES")
    print("="*60)
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Taille de la base
    cursor.execute("SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size()")
    size_bytes = cursor.fetchone()[0]
    size_mb = size_bytes / (1024 * 1024)
    print(f"\n📊 Taille de la base : {size_mb:.2f} MB")
    
    # Nombre d'enregistrements par table
    tables = ['enseignant', 'creneau', 'affectation', 'voeu', 'session', 'quota_enseignant']
    
    print("\n📋 Nombre d'enregistrements :")
    for table in tables:
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            print(f"   - {table:20s} : {count:6d} lignes")
        except sqlite3.Error:
            print(f"   - {table:20s} : Table non trouvée")
    
    # Sessions disponibles
    cursor.execute("SELECT id_session, libelle_session FROM session ORDER BY id_session")
    sessions = cursor.fetchall()
    
    print(f"\n📅 Sessions disponibles : {len(sessions)}")
    for sid, libelle in sessions:
        # Nombre d'affectations par session
        cursor.execute("SELECT COUNT(*) FROM affectation WHERE id_session = ?", (sid,))
        nb_aff = cursor.fetchone()[0]
        
        # Nombre de créneaux par session
        cursor.execute("SELECT COUNT(*) FROM creneau WHERE id_session = ?", (sid,))
        nb_cre = cursor.fetchone()[0]
        
        print(f"   [{sid}] {libelle:30s} : {nb_cre:3d} créneaux, {nb_aff:4d} affectations")
    
    conn.close()
    
    print("="*60 + "\n")


def main():
    """Point d'entrée principal"""
    print("\n🚀 OPTIMISATION DES PERFORMANCES DE LA BASE DE DONNÉES\n")
    
    # Analyser d'abord
    if os.path.exists(DB_NAME):
        analyze_database_performance()
    
    # Créer les index
    success = create_performance_indexes()
    
    if success:
        print("✅ Optimisation terminée avec succès!")
        print("\n💡 Relancez votre optimisation, elle devrait être plus rapide.\n")
    else:
        print("⚠️  Optimisation terminée avec des erreurs.")
        print("   Vérifiez les messages ci-dessus.\n")


if __name__ == "__main__":
    main()
