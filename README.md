# asvette2google.py

Ce script va rechercher la liste des sorties pour chaque activité sur ASVETTE et créer un fichier CSV à importer dans le calendrier Google correspondant. Le fichier CSV est créé uniquement s'il y a un ou plusieurs sorties prévues pour l'activité en question.

## Prérequis

- Python 3.x
- Les packages requis sont répertoriés dans le fichier `requirements.txt`.

## Installation

1. Clonez le référentiel GitHub :
    
    ```shell
    git clone https://github.com/furterg/asvette2google.git asvette2google
    cd asvette2google
    ```

2. Créer un environment virtuel Python :

    ```shell
    python3 -m venv venv
    source venv/bin/activate
    ```

3. Installez les dépendances à l'aide de pip :
    ```shell
    pip install -r requirements.txt
    ```

## Utilisation
Exécutez le script en exécutant la commande suivante :

```shell
python3 asvette2google.py
```

Le script passera en revue les différentes activités et recherchera les sorties correspondantes sur ASVETTE. Si des sorties sont trouvées, un fichier CSV sera créé pour chaque activité, prêt à être importé dans le calendrier Google.

## Remarques

* Le Ski Alpin est exclu de la recherche.
* Les sorties sont filtrées uniquement pour les activités répertoriées dans le dictionnaire activites.
* Les fichiers CSV seront créés avec le nom de chaque activité.

Ce projet a été développé par Gregory Furter pour l'[ASVEL Ski Montagne](https://www.asvelskimontagne.fr/).