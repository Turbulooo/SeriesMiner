import unittest
import json
import sqlite3
import os
import sys

# Ajout du dossier courant au path
sys.path.append(os.getcwd())

from setup_etl import remove_accents as remove_accents_etl, clean_text_content
from app import app, get_db_connection, init_app 

class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

class TestSeriesMiner(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """Initialisation unique pour la vitesse"""
        # On ne veut pas les logs de Flask qui polluent l'affichage
        import logging
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.ERROR)

        app.config['TESTING'] = True
        cls.client = app.test_client()
        cls.test_user = "test_user_qa"
        cls.test_pass = "password123"
        
        # Injection de données de test
        conn = get_db_connection()
        conn.execute("DELETE FROM users WHERE username = ?", (cls.test_user,))
        conn.execute("INSERT OR REPLACE INTO series (id, title, cleaned_text) VALUES (1, 'Serie Test Integration', 'banana avion aircraft crash test')")
        conn.commit()
        conn.close()
        
        # Rechargement IA silencieux
        init_app()

    # --- Outils d'affichage ---
    def print_section(self, title, route=None):
        print("\n" + "="*60)
        if route:
            print(f"{Colors.BOLD}TEST INTEGRATION : {title}{Colors.ENDC}")
            print(f"{Colors.BLUE}Route testée : {route}{Colors.ENDC}")
        else:
            print(f"{Colors.BOLD}TEST UNITAIRE : {title}{Colors.ENDC}")
            print(f"{Colors.BLUE}Fonction interne{Colors.ENDC}")
        print("-" * 60)

    def log_step(self, msg):
        print(f"[*] {msg}")

    def log_success(self, msg):
        print(f"{Colors.GREEN}[SUCCESS] {msg}{Colors.ENDC}")

    def log_fail(self, msg):
        print(f"{Colors.FAIL}[FAILURE] {msg}{Colors.ENDC}")

    # --- TESTS UNITAIRES ---

    def test_01_unit_functions(self):
        # 1. Test remove_accents
        self.print_section("Nettoyage d'Accents (ETL)")
        entree = "Hôpital, Été"
        attendu = "Hopital, Ete"
        self.log_step(f"Entrée : '{entree}'")
        res = remove_accents_etl(entree)
        if res == attendu:
            self.log_success(f"Transformation correcte : '{res}'")
        else:
            self.log_fail(f"Attendu '{attendu}', reçu '{res}'")
            self.fail()

        # 2. Test clean_text_content
        print("") # Petit saut de ligne
        self.print_section("Nettoyage Complet du Texte (ETL)")
        entree = "<i>00:20</i> L'été à Paris !"
        self.log_step(f"Entrée brute : \"{entree}\"")
        res = clean_text_content(entree)
        # On s'attend à ce que 'été' devienne 'ete', 'paris' reste, et le reste saute
        if "ete" in res and "paris" in res and "<" not in res:
             self.log_success(f"Sortie nettoyée : \"{res}\"")
        else:
             self.log_fail(f"Nettoyage incorrect : \"{res}\"")
             self.fail()

    # --- TESTS INTEGRATION ---

    def test_02_catalogue(self):
        self.print_section("Récupération du Catalogue", "GET /api/series")
        self.log_step("Envoi de la requête GET...")
        response = self.client.get('/api/series')
        data = json.loads(response.data)
        
        self.log_step(f"Code HTTP reçu : {response.status_code}")
        if response.status_code == 200:
            self.log_success(f"Catalogue récupéré avec succès. {len(data)} séries trouvées.")
        else:
            self.log_fail("Erreur serveur")

    def test_03_register(self):
        self.print_section("Gestion de l'inscription", "POST /api/register")
        payload = {'username': self.test_user, 'password': self.test_pass}
        self.log_step(f"La requête POST effectuée avec : {payload}")
        
        response = self.client.post('/api/register', json=payload)
        data = json.loads(response.data)
        
        if data.get('success'):
            self.log_success(f"Compte '{self.test_user}' créé avec succès.")
        else:
            self.log_fail(f"Erreur : {data}")

    def test_04_login(self):
        self.print_section("Gestion de la connexion", "POST /api/login")
        self.log_step("Tentative de connexion avec le nouveau compte...")
        
        response = self.client.post('/api/login', json={'username': self.test_user, 'password': self.test_pass})
        if json.loads(response.data).get('success'):
            self.log_success("Authentification réussie, session ouverte.")
        else:
            self.log_fail("Échec connexion")

    def test_05_search(self):
        self.print_section("Moteur de Recherche", "GET /api/search")
        terme = "avion"
        self.log_step(f"Recherche du terme : '{terme}'")
        
        response = self.client.get(f'/api/search?q={terme}')
        data = json.loads(response.data)
        
        self.log_step(f"Nombre de résultats : {len(data)}")
        # On vérifie si notre série injectée (qui contient 'avion') remonte
        found = next((d for d in data if d['id'] == 1), None)
        
        if found:
            self.log_success(f"Recherche pertinente. Top résultat : {found['title']} (Score: {found['score']})")
        else:
            self.log_fail("La série test n'a pas été trouvée.")

    def test_06_rate(self):
        self.print_section("Notation d'une série", "POST /api/rate")
        # On renforce la session
        self.client.post('/api/login', json={'username': self.test_user, 'password': self.test_pass})
        
        self.log_step("Ajout d'une note de 5/5 pour la série ID 1")
        response = self.client.post('/api/rate', json={'serie_id': 1, 'rating': 5})
        
        if json.loads(response.data).get('success'):
            self.log_success("Note enregistrée en base de données.")
        else:
            self.log_fail("Erreur notation")

    def test_07_my_ratings(self):
        self.print_section("Récupération 'Mes Notes'", "GET /api/my_ratings")
        self.log_step("Vérification que la note est bien sauvegardée...")
        
        response = self.client.get('/api/my_ratings')
        data = json.loads(response.data)
        
        found = next((d for d in data if d['id'] == 1 and d['rating'] == 5), None)
        
        if found:
            self.log_success(f"Série retrouvée dans l'historique : {found['title']} - Note : {found['rating']}/5")
        else:
            self.log_fail("Note introuvable dans l'historique.")

    def test_08_recommend(self):
        self.print_section("Système de Recommandation", "GET /api/recommend")
        self.log_step("Demande de recommandation (Content-Based car connecté)...")
        
        response = self.client.get('/api/recommend')
        data = json.loads(response.data)
        
        if len(data) > 0:
            self.log_success(f"L'IA a généré {len(data)} recommandations.")
        else:
            self.log_fail("Aucune recommandation générée.")

if __name__ == '__main__':
    # Verbosity 0 pour cacher les "..." de unittest et ne voir que nos prints
    runner = unittest.TextTestRunner(verbosity=0)
    unittest.main(testRunner=runner)