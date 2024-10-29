"""
Ce script va rechercher la liste des sorties pour chaque activité sur ASVETTE et créé un fichier csv
à importer dans les calendriers Google correspondant.
Le fichier CSV est créé uniquement si un ou plusieurs sorties sont prévues pour l'activité en question.
"""
import os
import sys
import time
from idlelib.debugger_r import start_debugger

import requests
import pandas as pd
import datetime
from bs4 import BeautifulSoup
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from icecream import ic

ic.configureOutput(includeContext=True)

# If modifying these scopes, delete the file token.json.
SCOPES: list[str] = ["https://www.googleapis.com/auth/calendar"]
TOKEN: str = "token.json"

# TODO: Rétablir la liste des activités aprés les tests
activities: dict[str, dict] = {
    'Rando Raquettes': {'asvette_id': 6, 'google_id': 'tot2sof5fb0ddj9uqkve8u8d04@group.calendar.google.com'}
}

# List des activités et id ASVETTE correspondant. Le Ski Alpin est exclu.
# activities: dict[str, dict] = {
#     'Ski de Rando': {'asvette_id': 1, 'google_id': '9676k6ja62o3karrf1qal43vg8@group.calendar.google.com'},
#     'Ski de Fond': {'asvette_id': 2, 'google_id': 'n49a0esd948cfcdjdmli4d271o@group.calendar.google.com'},
#     'Alpinisme': {'asvette_id': 4, 'google_id': 'd1q94ivu5pm8mmui4pn9mjcbmc@group.calendar.google.com'},
#     'Randonnée': {'asvette_id': 5, 'google_id': 'lk29f8nbu3i0hhn70i7b8oetho@group.calendar.google.com'},
#     'Rando Raquettes': {'asvette_id': 6, 'google_id': 'n49a0esd948cfcdjdmli4d271o@group.calendar.google.com'},
#     'Via Ferrata': {'asvette_id': 7, 'google_id': 'l5t9lmq3d84uam9rvuvkfum4q4@group.calendar.google.com'},
#     'Canyoning': {'asvette_id': 8, 'google_id': 'l5t9lmq3d84uam9rvuvkfum4q4@group.calendar.google.com'},
#     'Escalade': {'asvette_id': 9, 'google_id': 'l5t9lmq3d84uam9rvuvkfum4q4@group.calendar.google.com'},
#     'Ski de randonnée nordique': {'asvette_id': 10, 'google_id': 'n49a0esd948cfcdjdmli4d271o@group.calendar.google.com'},
# }


def timer(func):
    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        end = time.time()
        ic(f"Execution time: {end - start:.2f} seconds")
        return result

    return wrapper


def get_credentials():
    """
    Retourne les credentials pour accéder aux APIs Google.

    Les credentials sont stockés dans un fichier token.json. Si le fichier n'existe pas,
    le programme lance le flux d'authentification et stocke les credentials dans le fichier
    token.json.
    """
    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists(TOKEN):
        creds = Credentials.from_authorized_user_file(TOKEN, SCOPES)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                "credentials.json", SCOPES
            )
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open(TOKEN, "w") as token:
            token.write(creds.to_json())
    return creds


def get_service(creds: Credentials):
    """
    Retourne le service de Google Calendar.

    :param creds: Credentials pour accéder aux APIs Google
    :type creds: Credentials
    :return: Service de Google Calendar
    :rtype: Service
    """
    try:
        service = build("calendar", "v3", credentials=creds)
    except HttpError as error:
        print(f"Une erreur s'est produite: {error}")
        sys.exit(1)
    return service


def get_asvette_events(activity_id: int) -> pd.DataFrame:
    """
    Cette fonction va rechercher la liste des sorties pour chaque activité sur ASVETTE et mettre
    les informations dans un DataFrame.
    Si le dataframe est vide, on le retourne directement.
    S'il y a des sorties, on met en forme le Dataframe et on le retourne.
    :param activity_id: Id de l'activité
    :type activity_id: integer
    :return: dataframe des sorties
    :rtype: pandas dataframe
    """
    # URL pour ASVETTE
    url: str = f"https://asvel.limoog.net/public/pages/liste-sortie.php?Pass%C3%A9es=F&Activite={activity_id}"

    # Send a GET request to the webpage
    response: requests.Response = requests.get(url)

    # Create a BeautifulSoup object from the response content
    soup: BeautifulSoup = BeautifulSoup(response.content, "html.parser")

    # On récupère le tableau des sorties
    table = soup.find("table", {"id": "table_sortie"})
    # On récupère les en-têtes du tableau
    headers: list = [header.text.strip() for header in table.find_all("th")]

    # On récupère les données du tableau
    rows: list = []
    for row in table.find_all("tr"):
        row_data = [cell.text.strip() for cell in row.find_all("td")]
        if row_data:
            rows.append(row_data)
    # On transforme le tableau en DataFrame
    df: pd.DataFrame = pd.DataFrame(rows, columns=headers)
    if df.empty:
        return df

    # On transforme la colonne 'Date' en datetime
    df['Date'] = pd.to_datetime(df['Date'])
    # On transforme la colonne 'Départ' en datetime
    df['Heure'] = pd.to_datetime(df['Heure'], format='%H:%M', errors='coerce').dt.time

    first_char: str = 'Durée_first_char'
    # On extrait le nombre de jours de la colonne 'Durée'
    df[first_char] = df['Durée'].apply(lambda x: int(x.split(' ')[0]) - 1)
    # On ajoute le nombre de jours pour créer la colonne 'End Date'
    df['End Date'] = df.apply(lambda ligne: ligne['Date'] + pd.DateOffset(days=ligne[first_char]),
                              axis=1)
    # On supprime la colonne 'Durée_first_char', plus besoin.
    df = df.drop(first_char, axis=1)
    df['Date'] = df['Date'].dt.strftime('%Y-%m-%d')
    df['End Date'] = df['End Date'].dt.strftime('%Y-%m-%d')

    # On ajoute une colonne 'Description' qui correspond à Difficulté + Encadrant
    df['Description'] = df['Difficulté'] + ' | ' + df['Encadrant']

    # On ajoute deux colonnes pour le bon format du CSV
    df['End Time'] = ''
    df['Private'] = ''
    # Ajoute 3 heure à l'heure de début pour déterminer la fin si pas une sortie journée.
    df['End Time'] = df.apply(lambda x: (datetime.datetime.combine(datetime.date.today(), x['Heure'])
                                         + datetime.timedelta(hours=3)).time()
    if not pd.isnull(x['Heure']) else '', axis=1)

    # On considère qu'une sortie dure la journée s'il n'y a pas d'heure de départ ou si le départ
    # est avant 10h00
    df['All Day Event'] = df['Heure'].apply(
        lambda x: 'TRUE' if pd.isnull(x) or x < pd.to_datetime('10:00').time() else 'FALSE')
    df['Heure'] = df['Heure'].apply(lambda x: x.strftime('%H:%M') if not pd.isnull(x) else '')
    df['End Time'] = df['End Time'].apply(lambda x: x.strftime('%H:%M') if x else '')
    # On transforme la colonne 'Date' en datetime

    ic(df.columns)
    # On renomme les colonnes pour correspondre au format du fichier csv
    df = df.rename(columns={'Nom': 'Subject', 'Date': 'Start Date', 'Heure': 'Start Time',
                            'Lieu': 'Location'})
    df = df[['Id', 'Subject', 'Start Date', 'Start Time', 'End Date', 'End Time', 'All Day Event',
             'Description', 'Location', 'Private']]
    df['Id'] = df['Id'].apply(lambda x: 'asvette' + 'test' + 'act' + str(activity_id) + 'id' + str(x))  # TODO: Remove 'test' from string
    ic(df.columns)
    ic(df.head(5))
    df = df.iloc[:3, :]  # TODO: Supprimer cette ligne si on veut afficher toutes les sorties
    ic(df.iloc[0].to_dict())
    return df


def get_google_event_row(event):
    """
    Cette fonction prend un événement Google Calendar en entrée et renvoie
    la ligne correspondante au format CSV attendu par le fichier de sortie.

    :param event: un événement Google Calendar
    :type event: dict
    :return: la ligne correspondante au format CSV
    :rtype: list
    """
    row: list = [event['id']]
    start: str = event['start'].get('dateTime', event['start'].get('date'))
    end: str = event['end'].get('dateTime', event['end'].get('date'))
    row.append(event['summary'])
    # get the start date in format 'YYY-MM-DD'
    if 'T' in start:
        start_date_str = start.split('T')[0]
        row.append(start_date_str)
        start_time_str = start.split('T')[1].split('+')[0]
        row.append(start_time_str)
        start_time = datetime.datetime.strptime(start_time_str, '%H:%M:%S')
        ic(start_time.hour)
        all_day = 'TRUE' if start_time.hour < 10 else 'FALSE'
    else:
        row.append(start)
        row.append('')
        all_day = 'TRUE'
    if 'T' in end:
        row.append(end.split('T')[0])
        row.append(end.split('T')[1].split('+')[0])
    else:
        row.append(end)
        row.append('')
    row.append(all_day)
    row.append(event['description'] if 'description' in event.keys() else '')
    ic('location' in event.keys())
    row.append(event['location'] if 'location' in event.keys() else '')
    row.append('')
    print(f"Event: {event['summary']}, Start: {start}")
    return row


def get_google_events(service, google_id: str) -> pd.DataFrame | None:
    """
    Cette fonction va chercher les sorties de l'activité sur Google Calendar
    et les mettre en forme dans un DataFrame.
    :param google_id: Id du calendrier sur Google Calendar
    :type google_id: string
    :return: dataframe des sorties
    :rtype: pandas dataframe
    """
    # Call the Calendar API
    now = datetime.datetime.now().isoformat() + "Z"  # 'Z' indicates UTC time
    try:
        events_result = (
            service.events()
            .list(
                calendarId=google_id,
                timeMin=now,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        events = events_result.get("items", [])
    except HttpError as error:
        print(f"An error occurred: {error}")
        sys.exit(1)

    if not events:
        print("No upcoming events found.")
        return

    event_list: list[list[str]] = [['Id', 'Subject', 'Start Date', 'Start Time',
                                    'End Date', 'End Time', 'All Day Event',
                                    'Description', 'Location', 'Private']]
    for event in events:
        row = get_google_event_row(event)
        event_list.append(row)
    df: pd.DataFrame = pd.DataFrame(event_list[1:], columns=event_list[0])
    return df


def get_asvette_event_row_dict(asvette: dict) -> dict:
    """
    Cette fonction transforme un dictionnaire représentant une sortie ASVETTE
    en un dictionnaire correspondant à l'API Google Calendar.
    :param asvette: dictionnaire représentant une sortie ASVETTE
    :type asvette: dict
    :return: dictionnaire représentant la sortie ASVETTE en format Google Calendar
    :rtype: dict
    """
    ic(asvette)
    s_date: str = asvette['Start Date']
    e_date: str = asvette['End Date']
    s_time: str = asvette['Start Time']
    e_time: str = asvette['End Time']
    if asvette['All Day Event'] == 'TRUE':
        start: str = r"{" + f"'date': '{s_date}', 'timeZone': 'Europe/Paris'" + r"}"
        end: str = r"{" + f"'date': '{e_date}', 'timeZone': 'Europe/Paris'" + r"}"
    else:
        start = r"{" + f"'dateTime': '{s_date}T{s_time}:00', 'timeZone': 'Europe/Paris'" + r"}"
        end = r"{" + f"'dateTime': '{e_date}T{e_time}:00', 'timeZone': 'Europe/Paris'" + r"}"
    return {
        'id': asvette['Id'],
        'summary': asvette['Subject'],
        'location': asvette['Location'],
        'description': asvette['Description'],
        'start': eval(start),
        'end': eval(end),
    }


def add_google_event(service, google_id: str,event: dict) -> None:
    """
    This function adds a new event to a Google Calendar using the Google Calendar API.

    Parameters:
    service (googleapiclient.discovery.Resource): The Google Calendar API service.
    google_id (str): The ID of the Google Calendar.
    event (dict): The event to be added to the Google Calendar.

    Returns:
    None
    """
    try:
        event: dict = service.events().insert(calendarId=google_id, body=event).execute()
        print(f'Événement créé: {event.get("summary")}')
    except HttpError as error:
        print(f"Une erreur s'est produite: {error}")
        sys.exit(1)


def update_google_event(service, google_id: str, event: dict) -> None:
    updated_event: dict = service.events().update(calendarId=google_id,
                                                  eventId=event['id'],
                                                  body=event).execute()
    ic(updated_event)
    print(f'Événement mis à jour: {updated_event.get("summary")}')


def main() -> None:
    credentials = get_credentials()
    service = get_service(credentials)
    # On passe en revue les activités
    for activity, value in activities.items():
        asvette_id: int = value['asvette_id']
        google_id: str = value['google_id']
        print(f"---------\n{activity}")
        # 1. Recherche des sorties pour l'activité sur le site ASVETTE
        liste_sorties: pd.DataFrame = get_asvette_events(asvette_id)
        if liste_sorties.empty:
            print(f"Aucune sortie {activity} trouvée")
            continue
        print(f"Nombre de sorties pour l'activité {activity} : {liste_sorties.shape[0]}")
        # 2. Recherche des sorties pour l'activité sur Google Calendar
        liste_google_events: pd.DataFrame = get_google_events(service, google_id)
        ic(liste_google_events.iloc[0])
        # Si aucune sortie ASVETTE, Alors on passe à l'activité suivante
        if liste_sorties.shape[0] == 0:
            print(f"Aucune sortie {activity} de ASVETTE")
            continue
        # Si aucune sortie Google Calendar, Alors on ajoute les sorties de l'activité ASVETTe
        if liste_google_events is None:
            print(f"Aucune sortie {activity} sur Google Calendar")
            for index, row in liste_sorties.iterrows():
                ic(row)
                ic(row.to_dict())
                event = get_asvette_event_row_dict(row.to_dict())
                ic(event)
                add_google_event(service, google_id, event)
            continue
        else:
            # TODO : on compare les sorties de l'activité ASVETTE avec celles de Google Calendar
            # On ajoute les sorties de l'activité ASVETTE qui n'existent pas sur Google Calendar
            # create the code now
            for index, row in liste_sorties.iterrows():
                ic(row)
                ic(row.to_dict())
                if row['Id'] not in liste_google_events['Id'].values:
                    event = get_asvette_event_row_dict(row.to_dict())
                    ic(event)
                    add_google_event(service, google_id, event)
        # On passe en revue les sorties
        for index, row in liste_sorties.iterrows():
            ic(index)
            ic(row.to_dict())
            print(f"Id {row['Id']}")
            if row['Id'] in liste_google_events['Id'].values:
                index = liste_google_events[liste_google_events['Id'] == row['Id']].index.item()
                ic(liste_google_events.iloc[index].to_dict())
                if row.to_dict() == liste_google_events.iloc[index].to_dict():
                    print(f"Id {row['Id']} de la sortie {activity} de ASVETTE identique")
                else:
                    print(f"Id {row['Id']} de la sortie {activity} de ASVETTE non identique")
                    event = get_asvette_event_row_dict(row.to_dict())
                    ic(event)
                    update_google_event(service, google_id, event)

            print(f"Id {row['Id']} de la sortie {activity} de ASVETTE trouvé")


if __name__ == '__main__':
    main()
