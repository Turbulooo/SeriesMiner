import os
import sqlite3
import re
import zipfile
import shutil
import unicodedata # Pour gérer les accents
import io # Ajout pour la gestion des zips en mémoire

# --- CONFIGURATION ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')
DB_PATH = os.path.join(BASE_DIR, 'database', 'series.db')

# Mots vides (Stop Words)
STOP_WORDS = set([
    'le', 'la', 'les', 'de', 'des', 'du', 'un', 'une', 'et', 'à', 'en', 'il', 'elle', 'ils', 'elles',
    'je', 'tu', 'nous', 'vous', 'ce', 'se', 'que', 'qui', 'dans', 'pour', 'sur', 'pas', 'ne',
    'mais', 'ou', 'est', 'sont', 'cette', 'par', 'avec', 'tout', 'faire', 'plus', 'mon', 'ton', 'son',
    'the', 'a', 'an', 'and', 'of', 'to', 'in', 'is', 'it', 'you', 'that', 'he', 'she', 'we', 'they'
])

def remove_accents(input_str):
    """
    Transforme les caractères accentués en caractères normaux.
    Exemple: 'Île' -> 'Ile', 'été' -> 'ete', 'çà' -> 'ca'
    """
    if not isinstance(input_str, str): return str(input_str)
    # Normalisation NFD (décompose les caractères : é devient e + ')
    nfkd_form = unicodedata.normalize('NFKD', input_str)
    # On garde seulement les caractères de base (non combinés)
    return "".join([c for c in nfkd_form if not unicodedata.combining(c)])

def clean_text_content(text):

    # 1. Enlever les accents D'ABORD
    text = remove_accents(text)
    
    # 2. Supprimer les timestamps SRT (00:00:20,000 --> ...)
    text = re.sub(r'\d{2}:\d{2}:\d{2}[,.]\d{3}.*?', ' ', text)
    
    # 3. Supprimer les balises HTML
    text = re.sub(r'<[^>]+>', ' ', text)
    
    # 4. Ne garder que les lettres et chiffres (plus d'accents ici)
    text = re.sub(r'[^a-zA-Z0-9\s]', ' ', text)
    
    # 5. Minuscules et nettoyage espaces
    text = text.lower().strip()
    
    # 6. Filtrer les stop words
    words = text.split()
    meaningful_words = [w for w in words if w not in STOP_WORDS and len(w) > 2]
    
    return " ".join(meaningful_words)

def decode_bytes(content_bytes):
    """Essaie de lire le fichier avec plusieurs encodages."""
    encodings = ['utf-8', 'latin-1', 'cp1252']
    for encoding in encodings:
        try:
            return content_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
    return ""

def init_database():
    """Crée la structure de la base de données (Tables + Index)."""
    print(" Création de la base de données...")
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # On part de zéro pour éviter les conflits
    cursor.execute("DROP TABLE IF EXISTS ratings")
    cursor.execute("DROP TABLE IF EXISTS users")
    cursor.execute("DROP TABLE IF EXISTS series")
    
    # Table SÉRIES
    cursor.execute('''
        CREATE TABLE series (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            cleaned_text TEXT
        )
    ''')
    
    # Table UTILISATEURS
    cursor.execute('''
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    ''')
    
    # Table NOTES (Ratings)
    cursor.execute('''
        CREATE TABLE ratings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            serie_id INTEGER,
            rating INTEGER,
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(serie_id) REFERENCES series(id)
        )
    ''')
    
    # CRÉATION DES INDEX (Pour accélérer les recherches SQL)
    cursor.execute("CREATE INDEX idx_user_rating ON ratings(user_id)")
    cursor.execute("CREATE INDEX idx_serie_rating ON ratings(serie_id)")
    
    # Utilisateur par défaut
    cursor.execute("INSERT INTO users (username, password) VALUES (?, ?)", ('etudiant', '1234'))
    
    conn.commit()
    return conn

# --- NOUVELLE FONCTION POUR LES ZIPS IMBRIQUÉS ---
def read_zip_content(zip_file):
    """Lit récursivement un objet ZipFile."""
    text_content = ""
    for name in zip_file.namelist():
        # Si c'est un fichier texte
        if name.endswith(('.srt', '.txt')) and '__MACOSX' not in name:
            with zip_file.open(name) as zf:
                text_content += " " + decode_bytes(zf.read())
        
        # Si c'est un ZIP imbriqué (Zip dans Zip)
        elif name.endswith('.zip'):
            try:
                with zip_file.open(name) as zf_nested:
                    # On lit le zip imbriqué en mémoire (BytesIO)
                    nested_data = io.BytesIO(zf_nested.read())
                    with zipfile.ZipFile(nested_data) as z_nested:
                        text_content += " " + read_zip_content(z_nested)
            except:
                pass
    return text_content

def process_etl(conn):
    """Parcourt les dossiers, nettoie et insère."""
    print("Traitement des fichiers (ETL)...")
    
    if not os.path.exists(DATA_DIR):
        print(f"❌ Dossier {DATA_DIR} introuvable.")
        return

    cursor = conn.cursor()
    series_dirs = [d for d in os.listdir(DATA_DIR) if os.path.isdir(os.path.join(DATA_DIR, d))]
    
    count = 0
    for serie_name in series_dirs:
        serie_path = os.path.join(DATA_DIR, serie_name)
        full_text = []

        # Parcours récursif
        for root, dirs, files in os.walk(serie_path):
            for file in files:
                raw_content = ""
                file_path = os.path.join(root, file)
                
                # Lecture Fichier
                if file.endswith(('.srt', '.txt')):
                    try:
                        with open(file_path, 'rb') as f:
                            raw_content = decode_bytes(f.read())
                    except: pass
                # Lecture ZIP
                elif file.endswith('.zip'):
                    try:
                        with zipfile.ZipFile(file_path, 'r') as z:
                            # Appel de la fonction récursive ici
                            raw_content += read_zip_content(z)
                    except: pass
                
                if raw_content:
                    full_text.append(clean_text_content(raw_content))

        # Insertion
        final_text = " ".join(full_text)
        if len(final_text) > 50: # On ignore les dossiers vides
            cursor.execute("INSERT INTO series (title, cleaned_text) VALUES (?, ?)", (serie_name, final_text))
            conn.commit()
            print(f"   ✅ {serie_name} indexée.")
            count += 1
        else:
            print(f"   ⚠️ {serie_name} ignorée (vide).")

    print(f"\n SUCCÈS ! {count} séries prêtes dans la base de données.")

if __name__ == '__main__':
    db_conn = init_database()
    process_etl(db_conn)
    db_conn.close()