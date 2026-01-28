from flask import Flask, render_template, request, jsonify, session
import sqlite3
import os
import pandas as pd
import numpy as np
import math
import unicodedata
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# =============================================================================
# CONFIGURATION
# =============================================================================
app = Flask(__name__, template_folder='Interface/Html_Js', static_folder='Interface')
app.secret_key = 'cle_secrete_projet_sae' 

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'database', 'series.db')

# Variables globales (Cache mémoire)
df_series = None
tfidf_matrix = None
vectorizer = None
cosine_sim_matrix = None

# =============================================================================
# FONCTIONS UTILITAIRES
# =============================================================================

def remove_accents(input_str):
    """Normalise le texte (enlève les accents) pour la recherche."""
    if not isinstance(input_str, str): return str(input_str)
    nfkd_form = unicodedata.normalize('NFKD', input_str)
    return "".join([c for c in nfkd_form if not unicodedata.combining(c)])

def get_db_connection():
    """Connecte à SQLite."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_app():
    """Charge le moteur IA au démarrage."""
    global df_series, tfidf_matrix, vectorizer, cosine_sim_matrix
    print("Démarrage du système...")
    
    if not os.path.exists(DB_PATH):
        print("❌ Erreur : Base de données absente. Lancez scripts/setup_etl.py")
        return

    # 1. Chargement des données
    conn = sqlite3.connect(DB_PATH)
    df_series = pd.read_sql_query("SELECT id, title, cleaned_text FROM series", conn)
    conn.close()
    
    # 2. Vectorisation TF-IDF
    vectorizer = TfidfVectorizer(max_features=15000, stop_words='english', 
                                 ngram_range=(1, 2), sublinear_tf=True)
    
    df_series['cleaned_text'] = df_series['cleaned_text'].fillna('')
    tfidf_matrix = vectorizer.fit_transform(df_series['cleaned_text'])
    
    # 3. Matrice de similarité (pour la recommandation)
    cosine_sim_matrix = cosine_similarity(tfidf_matrix, tfidf_matrix)
    
    print(f"✅ Système prêt : {len(df_series)} séries indexées.")

# Initialisation immédiate
init_app()

# =============================================================================
# ROUTES WEB
# =============================================================================

@app.route('/')
def home():
    return render_template('index.html')

# =============================================================================
# API REST (JSON)
# =============================================================================

@app.route('/api/series', methods=['GET'])
def get_all_series():
    """Catalogue complet trié par titre."""
    conn = get_db_connection()
    series = conn.execute('SELECT id, title FROM series ORDER BY title ASC').fetchall()
    conn.close()
    return jsonify([{'id': r['id'], 'title': r['title'], 'score': 0} for r in series])

@app.route('/api/search', methods=['GET'])
def search():
    """
    Recherche intelligente.
    Applique la même normalisation (sans accents) que lors du nettoyage.
    """
    query = request.args.get('q', '')
    if not query: return jsonify([])

    # 1. Nettoyage de la requête (comme dans la base)
    clean_query = remove_accents(query.lower())

    try:
        query_vec = vectorizer.transform([clean_query])
        similarities = cosine_similarity(query_vec, tfidf_matrix).flatten()
    except: return jsonify([])

    # 2. Algorithme de pertinence
    keywords = clean_query.split()
    top_indices = similarities.argsort()[-50:][::-1]
    
    results = []
    for index in top_indices:
        score = similarities[index]
        if score > 0.0:
            row = df_series.iloc[index]
            
            # Bonus si les mots exacts sont présents
            text = row['cleaned_text']
            found = sum(1 for w in keywords if w in text)
            
            # Boost x3 si tout est trouvé
            boost = 3.0 if found == len(keywords) else 1.0
            # Boost fréquentiel logarithmique
            freq_boost = 1 + math.log(1 + text.count(keywords[0])) if keywords else 1
            
            final_score = score * boost * (freq_boost * 0.5)

            results.append({
                'id': int(row['id']),
                'title': row['title'],
                'score': float(round(final_score, 4))
            })
            
    # Tri final
    results = sorted(results, key=lambda x: x['score'], reverse=True)
    return jsonify(results[:10])

@app.route('/api/recommend', methods=['GET'])
def recommend():
    """Recommandation Hybride (Content-Based ou Popularity)."""
    conn = get_db_connection()
    
    # Connecté
    if 'user_id' in session:
        user_id = session['user_id']
        liked = conn.execute('SELECT serie_id FROM ratings WHERE user_id = ? AND rating >= 3', (user_id,)).fetchall()
        
        if not liked:
            conn.close()
            return jsonify([]) # Vide -> Incite à noter

        # Calcul Content-Based
        conn.close()
        total_scores = np.zeros(len(df_series))
        seen_ids = [r['serie_id'] for r in liked]
        
        for r in liked:
            idx = df_series.index[df_series['id'] == r['serie_id']].tolist()
            if idx: total_scores += cosine_sim_matrix[idx[0]]
            
        recos = []
        for idx in total_scores.argsort()[::-1]:
            sid = int(df_series.iloc[idx]['id'])
            if sid not in seen_ids:
                recos.append({'id': sid, 'title': df_series.iloc[idx]['title'], 'score': float(round(total_scores[idx], 2))})
                if len(recos) >= 10: break
        return jsonify(recos)

    # Anonyme (Top Rated)
    query = "SELECT s.id, s.title, AVG(r.rating) as avg FROM ratings r JOIN series s ON r.serie_id = s.id GROUP BY s.id ORDER BY avg DESC LIMIT 10"
    top = conn.execute(query).fetchall()
    conn.close()
    return jsonify([{'id': r['id'], 'title': r['title'], 'score': float(round(r['avg'], 2))} for r in top])

@app.route('/api/my_ratings', methods=['GET'])
def get_user_ratings():
    if 'user_id' not in session: return jsonify([])
    conn = get_db_connection()
    res = conn.execute('SELECT s.id, s.title, r.rating FROM ratings r JOIN series s ON r.serie_id = s.id WHERE r.user_id = ? ORDER BY r.rating DESC', (session['user_id'],)).fetchall()
    conn.close()
    return jsonify([{'id': r['id'], 'title': r['title'], 'rating': r['rating']} for r in res])

@app.route('/api/rate', methods=['POST', 'DELETE'])
def rate():
    if 'user_id' not in session: return jsonify({'error': 'Auth required'}), 401
    conn = get_db_connection()
    uid = session['user_id']
    data = request.json if request.is_json else request.args
    sid = int(data.get('serie_id'))
    
    if request.method == 'DELETE':
        conn.execute('DELETE FROM ratings WHERE user_id=? AND serie_id=?', (uid, sid))
    else:
        rating = int(data.get('rating'))
        conn.execute('DELETE FROM ratings WHERE user_id=? AND serie_id=?', (uid, sid))
        conn.execute('INSERT INTO ratings (user_id, serie_id, rating) VALUES (?, ?, ?)', (uid, sid, rating))
    
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    conn = get_db_connection()
    u = conn.execute('SELECT * FROM users WHERE username=? AND password=?', (data['username'], data['password'])).fetchone()
    conn.close()
    if u:
        session['user_id'] = u['id']
        session['username'] = u['username']
        return jsonify({'success': True, 'username': u['username']})
    return jsonify({'success': False, 'message': 'Erreur identifiants'})

@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    conn = get_db_connection()
    try:
        conn.execute('INSERT INTO users (username, password) VALUES (?, ?)', (data['username'], data['password']))
        conn.commit()
        u = conn.execute('SELECT * FROM users WHERE username=?', (data['username'],)).fetchone()
        session['user_id'] = u['id']
        session['username'] = u['username']
        conn.close()
        return jsonify({'success': True, 'username': u['username']})
    except:
        conn.close()
        return jsonify({'success': False, 'message': 'Pseudo pris'})

@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'success': True})

if __name__ == '__main__':
    app.run(debug=True, port=5000)