#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Script pour exporter toutes les tables de surveillance.db en fichiers CSV
"""

import os
import sqlite3
import pandas as pd

# Configuration
DB_NAME = 'surveillance.db'
OUTPUT_DIR = 'exports'

def get_db_connection():
    """Créer une connexion à la base de données"""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def get_all_tables(conn):
    """Récupérer la liste de toutes les tables dans la base de données"""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT name 
        FROM sqlite_master 
        WHERE type='table'
        ORDER BY name
    """)
    return [row[0] for row in cursor.fetchall()]

def export_table_to_csv(conn, table_name, output_dir):
    """Exporter une table en fichier CSV"""
    print(f"Exportation de la table '{table_name}'...")
    
    try:
        # Lire la table avec pandas
        df = pd.read_sql_query(f"SELECT * FROM {table_name}", conn)
        
        # Créer le chemin de sortie
        output_path = os.path.join(output_dir, f"{table_name}.csv")
        
        # Exporter en CSV
        df.to_csv(output_path, index=False, encoding='utf-8')
        print(f"✅ {len(df)} lignes exportées vers {output_path}")
        
    except Exception as e:
        print(f"❌ Erreur lors de l'exportation de {table_name}: {str(e)}")

def main():
    """Fonction principale"""
    print("="*60)
    print("EXPORTATION DES TABLES EN CSV")
    print("="*60)
    
    # Créer le dossier de sortie s'il n'existe pas
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # Se connecter à la base de données
    conn = get_db_connection()
    
    try:
        # Récupérer la liste des tables
        tables = get_all_tables(conn)
        print(f"\nTables trouvées : {len(tables)}")
        
        # Exporter chaque table
        for table in tables:
            export_table_to_csv(conn, table, OUTPUT_DIR)
            
        print("\n✅ Exportation terminée")
        
    except Exception as e:
        print(f"\n❌ Erreur : {str(e)}")
        
    finally:
        conn.close()

if __name__ == "__main__":
    main()