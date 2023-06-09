"""
Ce script va rechercher la liste des sorties pour chaque activité sur ASVETTE et créé un fichier csv
à importer dans les calendrier Google correspondant.
Le fichier CSV est créé uniquement si un ou plusieurs sorties sont prévues pour l'activité en question.
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd

# List des activités et id ASVETTE correspondant. Le Ski Alpin est exclu.
activites = {
    'Ski de Rando': 1,
    'Ski de Fond': 2,
    'Alpinisme': 4,
    'Randonnée': 5,
    'Rando Raquettes': 6,
    'Via Ferrata': 7,
    'Canyoning': 8,
    'Escalade': 9,
}


def get_events(id):
    """
    Cette fonction va rechercher la liste des sorties pour chaque activité sur ASVETTE et mettre
    les information dans un DataFrame.
    Si le dataframe est vide, on le retourne directement.
    S'il y a des sorties, on met en forme le Dataframe et on le retourne.
    :param id: id de l'activité
    :type id: integer
    :return: dataframe des sorties
    :rtype: pandas dataframe
    """
    # URL pour ASVETTE
    url = f"https://asvel.limoog.net/public/pages/liste-sortie.php?Pass%C3%A9es=F&Activite={id}"

    # Send a GET request to the webpage
    response = requests.get(url)

    # Create a BeautifulSoup object from the response content
    soup = BeautifulSoup(response.content, "html.parser")

    # On récupère le tableau des sorties
    table = soup.find("table", {"id": "table_sortie"})

    # On récupère les entetes du tableau
    headers = [header.text.strip() for header in table.find_all("th")]

    # On récupère les données du tableau
    rows = []
    for row in table.find_all("tr"):
        row_data = [cell.text.strip() for cell in row.find_all("td")]
        if row_data:
            rows.append(row_data)

    # On transforme le tableau en DataFrame
    df = pd.DataFrame(rows, columns=headers)
    if df.empty:
        return df

    # On transforme la colonne 'Date' en datetime
    df['Date'] = pd.to_datetime(df['Date'])
    # On transforme la colonne 'Départ' en datetime
    df['Départ'] = pd.to_datetime(df['Départ'], format='%H:%M', errors='ignore').dt.time

    # On estrait le premier caractère de la colonne 'Durée', qui représente le nombre de jours
    df['Durée_first_char'] = df['Durée'].str[0].astype(int)-1
    # On ajoute le nombre de jours pour créer la colonne 'End Date'
    df['End Date'] = df.apply(lambda row: row['Date'] + pd.DateOffset(days=row['Durée_first_char']),
                              axis=1)
    # On supprime la colonne 'Durée_first_char', plus besoin.
    df.drop('Durée_first_char', axis=1, inplace=True)

    # On ajoute une colonne 'Description' qui correspond à Difficulté + Encadrant
    df['Description'] = df['Difficulté'] + ' | ' + df['Encadrant']

    # On ajoute deux colonnes pour le bon format du CSV
    df['End Time'] = ''
    df['Private'] = ''

    # On considère qu'un dure ja journée s'il n'y a pas d'heure de départ ou si le départ
    # est avant 10h00
    df['All Day Event'] = df['Départ'].apply(
        lambda x: 'TRUE' if pd.isnull(x) or x < pd.to_datetime('10:00').time() else 'FALSE')

    # On renomme les colonnes pour correspondre au format du fichier csv
    df = df.rename(columns={'Nom': 'Subject', 'Date': 'Start Date', 'Départ': 'Start Time', 'Lieu': 'Location'})
    df = df[['Subject', 'Start Date', 'Start Time', 'End Date', 'End Time', 'All Day Event', 'Description', 'Location', 'Private']]
    return df


if __name__ == '__main__':

    # On passe en revue les activités
    for key, value in activites.items():
        print(f"---------\n{key}")
        liste_sorties = get_events(value)
        if liste_sorties.empty:
            print(f"Aucune sortie {key} trouvée")
            continue
        else:
            print(f"Nombre de sorties : {liste_sorties.shape[0]}")
            liste_sorties.to_csv(f"{key}.csv", index=False)
            print(f"Fichier {key}.csv créé")
