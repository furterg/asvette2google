# asvette2google.py

Ce script va rechercher la liste des sorties pour chaque activité sur ASVETTE et créer un fichier CSV à importer dans le calendrier Google correspondant. Le fichier CSV est créé uniquement s'il y a un ou plusieurs sorties prévues pour l'activité en question.

## Prérequis

- Python 3.x
- Les packages requis sont répertoriés dans le fichier `requirements.txt`.
- être dans la liste des utilisateurs approuvés sur Google API.
- Avoir le fichier 'credentials.json' qui permet de générer le token.

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
python3 asvette2google.py [--log <log_file>] [--hook <webhook_url>]
```

* --log : spécifie le chemin absolu vers le fichier de logs (défaut : asvette.log dans le dossier du script)
* --hook : spécifie l'URL d'un webhook Zapier qui capturera le résultat de l'automatisation (facultatif)

Exemple :

```shell
python asvette2google.py --log /var/log/asvette.log --hook https://zapier.com/hooks/1234567890
```

Le script fait les choses suivantes pour chaque activité :

1. Récupère la liste de sorties sur ASVETTE.
2. Récupère la liste des sorties sur le calendrier Google correspondant.
3. Si une sortie existe dans ASVETTE mais pas dans Google, elle est ajoutée au calendrier
avec un ID qui est basé sur l'ID ASVETTE.
   * S'il n'y a pas d'heure de début ou si elle débute avant 10h00 → Sortie journée entière
   * Si l'heure de début est après 10h00 → j'attribue arbitrairement une heure de fin 3h après.
4. Si une sortie existe aux deux endroits (même ID) mais avec des informations différentes, elle est mise à jour sur le calendrier à partir des infos ASVETTE.
5Les sorties identiques des deux cotés ne sont pas modifiées.

## Remarques

* Le Ski Alpin est exclu de la recherche.
* Les sorties sont filtrées uniquement pour les activités répertoriées dans le dictionnaire ACTIVITIES.

Ce projet a été développé par Gregory Furter pour l'[ASVEL Ski Montagne](https://www.asvelskimontagne.fr/).