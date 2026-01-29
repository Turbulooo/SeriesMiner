PROJET SAE S5.C.01 - APPLICATION SERIESMINER

--- BINÔME ---
Étudiant 1 : MONTOUT Ewen (Non-alternant)
Étudiant 2 : BRACH Manolo (Non-alternant)

Groupe : 8

--- DESCRIPTION ---
Ce projet contient le code source de l'application "SeriesMiner", un simulateur de plateforme de streaming vidéo avec moteur de recommandation basé sur le contenu (TF-IDF).

--- STRUCTURE DE L'ARCHIVE ---
/SeriesMiner
|-- app.py              # Le serveur Flask et le moteur IA
|-- setup_etl.py        # Le script d'initialisation et de nettoyage des données (ETL)
|-- run_tests.py        # Le script de tests automatisés (Unitaires & Intégration)
|-- requirements.txt    # La liste des dépendances Python
|-- /database           # Dossier pour la base de données SQLite (générée par le script ETL)
|-- /data               # Dossier contenant les fichiers sources (SRT, TXT, ZIP)
|-- /Interface          # Dossier contenant les assets Web (CSS, Images)
|-- /Css
|-- /Html_Js        # Contient les templates HTML (index.html)

--- INSTALLATION & LANCEMENT ---

Pré-requis :

Python 3.8 ou supérieur

pip (gestionnaire de paquets)

Installation des dépendances :
Ouvrez un terminal dans le dossier du projet et exécutez :
pip install -r requirements.txt


Initialisation des données (ETL) :
Avant de lancer le serveur, il faut construire la base de données :
python setup_etl.py
(Cela va créer le fichier database/series.db à partir des fichiers du dossier /data)

Lancement de l'application :
python app.py

--- LANCEMENT DES TESTS ---
Pour exécuter la suite de tests automatisés :
python run_tests.py

--- NOTES ---
Le fichier 'requirements.txt' contient les librairies nécessaires :

flask

pandas

scikit-learn

numpy
