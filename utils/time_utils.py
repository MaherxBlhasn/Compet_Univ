"""
utils/time_utils.py
Utilitaires pour la manipulation et normalisation des heures
"""

import pandas as pd


def parse_time(time_str):
    """
    Extrait et normalise l'heure d'un timestamp ou d'une chaîne de temps
    Convertit tous les formats en "HH:MM"
    
    Formats acceptés:
    - "30/12/1999 08:30:00" -> "08:30"
    - "08:30:00" -> "08:30"
    - "08:30" -> "08:30" (déjà au bon format)
    - "8:30" -> "08:30" (ajoute le zéro devant)
    - Timestamp pandas -> "HH:MM"
    
    Args:
        time_str: Chaîne de caractères ou timestamp représentant une heure
    
    Returns:
        str: Heure au format "HH:MM" ou None si invalide
    """
    if pd.isna(time_str):
        return None
    
    # Convertir en string
    time_str = str(time_str).strip()
    
    # Si vide
    if not time_str:
        return None
    
    # Si c'est déjà au format HH:MM (5 caractères avec :)
    if len(time_str) == 5 and time_str[2] == ':':
        return time_str
    
    # Si c'est un datetime complet (avec date et heure)
    if ' ' in time_str:
        # Extraire la partie heure après l'espace
        time_part = time_str.split(' ')[1]
    else:
        time_part = time_str
    
    # Extraire HH:MM des différents formats (HH:MM:SS, HH:MM, H:MM, etc.)
    if ':' in time_part:
        parts = time_part.split(':')
        if len(parts) >= 2:
            hour = parts[0].zfill(2)  # Assurer 2 chiffres pour l'heure
            minute = parts[1].zfill(2)  # Assurer 2 chiffres pour les minutes
            return f"{hour}:{minute}"
    
    # Si aucun format reconnu, retourner les 5 premiers caractères
    return time_part[:5] if len(time_part) >= 5 else None


def determine_seance_from_time(time_str):
    """
    Détermine S1, S2, S3 ou S4 selon l'heure
    Utilise parse_time pour normaliser d'abord le format
    
    Plages horaires:
    - S1: 08:00 - 09:59
    - S2: 10:00 - 11:59
    - S3: 12:00 - 13:59
    - S4: 14:00 - 16:59
    
    Args:
        time_str: Chaîne de caractères ou timestamp représentant une heure
    
    Returns:
        str: Code de séance ('S1', 'S2', 'S3', 'S4') ou None si invalide
    """
    if pd.isna(time_str):
        return None
    
    # Utiliser parse_time pour normaliser le format
    normalized_time = parse_time(time_str)
    if not normalized_time:
        return None
    
    try:
        hour = int(normalized_time.split(':')[0])
        if 8 <= hour < 10:
            return 'S1'
        elif 10 <= hour < 12:
            return 'S2'
        elif 12 <= hour < 14:
            return 'S3'
        elif 14 <= hour < 17:
            return 'S4'
    except:
        pass
    return None
