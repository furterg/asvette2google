"""
Ce script va rechercher la liste des sorties pour chaque activité sur ASVETTE.
I lva ensuite récupérer la liste des sorties présentes dans le calendrier Google correspondant.
En fonction des résultats:
- On ajoute les sorties de l'activité ASVETTE qui n'existent pas sur Google Calendar.
- On met à jour les sorties de l'activité ASVETTE qui ont changé.
"""
import os
import sys
import time

import requests
import pandas as pd
import datetime
import httplib2
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


ESC: str = 'l5t9lmq3d84uam9rvuvkfum4q4@group.calendar.google.com'  # Escalade
SDF: str = 'n49a0esd948cfcdjdmli4d271o@group.calendar.google.com'  # Ski de fond
# List des activités et id ASVETTE correspondant. Le Ski Alpin est exclu.
ACTIVITIES: dict[str, dict] = {
    'Ski de Rando': {'asvette_id': 1,
                     'google_id': '9676k6ja62o3karrf1qal43vg8@group.calendar.google.com'},
    'Ski de Fond': {'asvette_id': 2, 'google_id': SDF},
    'Alpinisme': {'asvette_id': 4,
                  'google_id': 'd1q94ivu5pm8mmui4pn9mjcbmc@group.calendar.google.com'},
    'Randonnée': {'asvette_id': 5,
                  'google_id': 'lk29f8nbu3i0hhn70i7b8oetho@group.calendar.google.com'},
    'Rando Raquettes': {'asvette_id': 6, 'google_id': SDF},
    'Via Ferrata': {'asvette_id': 7, 'google_id': ESC},
    'Canyoning': {'asvette_id': 8, 'google_id': ESC},
    'Escalade': {'asvette_id': 9, 'google_id': ESC},
    'Ski de randonnée nordique': {'asvette_id': 10, 'google_id': SDF},
}
ED_str: str = 'End Date'
SD_str: str = 'Start Date'
ST_str: str = 'Start Time'
ET_str: str = 'End Time'
ADE_str: str = 'All Day Event'


def timer(func):
    def wrapper(*args, **kwargs):
        """
        Decorator to measure the execution time of a function.

        Prints the execution time of the wrapped function using icecream.

        Example:
            @timer
            def my_function():
                ...

            my_function()  # prints "Execution time: 0.00 seconds"
        """
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
    url: str = (f"https://asvel.limoog.net/public/pages/liste-sortie.php?"
                f"Pass%C3%A9es=F&Activite={activity_id}")
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
        row_data: list = [cell.text.strip() for cell in row.find_all("td")]
        if row_data:
            rows.append(row_data)
            # print(f"ASVETTE: {row_data[1]}, date: {row_data[3]}")
    # On transforme le tableau en DataFrame
    df: pd.DataFrame = pd.DataFrame(rows, columns=headers)
    if df.empty:
        return df

    # On transforme la colonne 'Date' en datetime
    df['Date'] = pd.to_datetime(df['Date'])
    # On transforme la colonne 'Départ' en datetime
    df['Heure'] = pd.to_datetime(df['Heure'], format='%H:%M:%S', errors='coerce').dt.time

    first_char: str = 'Durée_first_char'
    # On extrait le nombre de jours de la colonne 'Durée'
    df[first_char] = df['Durée'].apply(lambda x: int(x.split(' ')[0]) - 1)
    # On ajoute le nombre de jours pour créer la colonne 'End Date'
    df[ED_str] = df.apply(lambda ligne: ligne['Date'] + pd.DateOffset(days=ligne[first_char]),
                          axis=1)
    # On supprime la colonne 'Durée_first_char', plus besoin.
    df = df.drop(first_char, axis=1)
    df['Date'] = df['Date'].dt.strftime('%Y-%m-%d')
    df[ED_str] = df[ED_str].dt.strftime('%Y-%m-%d')

    # On ajoute une colonne 'Description' qui correspond à Difficulté + Encadrant
    df['Description'] = df['Difficulté'] + ' | ' + df['Encadrant']

    # On ajoute deux colonnes pour le bon format du CSV
    df[ET_str] = ''
    df['Private'] = ''
    # Ajoute TROIS heures à l'heure de début pour déterminer la fin si pas une sortie journée.
    df[ET_str] = df.apply(
        lambda x: (datetime.datetime.combine(datetime.date.today(), x['Heure'])
                   + datetime.timedelta(hours=3)).time()
        if not pd.isnull(x['Heure']) else '', axis=1)

    # On considère qu'une sortie dure la journée s'il n'y a pas d'heure de départ ou si le départ
    # est avant 10h00.
    df[ADE_str] = df['Heure'].apply(
        lambda x: 'TRUE' if pd.isnull(x) or x < pd.to_datetime('10:00:00').time() else 'FALSE')
    df['Heure'] = df['Heure'].apply(lambda x: x.strftime('%H:%M:%S') if not pd.isnull(x) else '')
    df[ET_str] = df[ET_str].apply(lambda x: x.strftime('%H:%M:%S') if x else '')
    # On renomme les colonnes pour correspondre au format du fichier csv
    df = df.rename(columns={'Nom': 'Subject', 'Date': SD_str, 'Heure': ST_str,
                            'Lieu': 'Location'})
    df = df[['Id', 'Subject', SD_str, ST_str, ED_str, ET_str, ADE_str,
             'Description', 'Location', 'Private']]
    df['Id'] = df['Id'].apply(lambda x: 'asvette' + 'act' + str(activity_id) + 'id' + str(x))
    return df


def get_google_event_row(event):
    """
    Cette fonction prend un événement Google Calendar en entrée et renvoie
    la ligne correspondante au format CSV attendu par le fichier de sortie.

    :param event: Un événement Google Calendar
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
        start_date_str: str = start.split('T')[0]
        row.append(start_date_str)
        start_time_str: str = start.split('T')[1].split('+')[0]
        row.append(start_time_str)
        start_time = datetime.datetime.strptime(start_time_str, '%H:%M:%S')
        all_day: str = 'TRUE' if start_time.hour < 10 else 'FALSE'
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
    row.append(event['location'] if 'location' in event.keys() else '')
    row.append('')  # Private
    return row


def get_google_events(service, google_id: str) -> pd.DataFrame | None:
    """
    Cette fonction va chercher les sorties de l'activité sur Google Calendar
    et les mettre en forme dans un DataFrame.
    :param service: Service Google Calendar
    :type service: object
    :param google_id: Id du calendrier sur Google Calendar
    :type google_id: string
    :return: dataframe des sorties
    :rtype: pandas dataframe
    """
    # Call the Calendar API
    now: str = datetime.datetime.now().isoformat() + "Z"  # 'Z' indicates UTC time
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
        print(f"Une erreur s'est produite: {error}")
        sys.exit(1)
    except httplib2.error.ServerNotFoundError as error:
        print(f"Une erreur s'est produite: {error}")
        sys.exit(1)

    if not events:
        print("Aucune sortie trouvée.")
        return

    event_list: list[list[str]] = [['Id', 'Subject', SD_str, ST_str,
                                    ED_str, ET_str, ADE_str,
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
    :param asvette: Dictionnaire représentant une sortie ASVETTE
    :type asvette: dict
    :return: dictionnaire représentant la sortie ASVETTE en format Google Calendar
    :rtype: dict
    """
    s_date: str = asvette[SD_str]
    e_date: str = asvette[ED_str]
    s_time: str = asvette[ST_str]
    e_time: str = asvette[ET_str]
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


def diff_asvette_google(asv_dict: dict, google_dict: dict) -> bool:
    """
    Check if an ASVETTE event is different from a Google Calendar event.

    Parameters:
    asv_dict (dict): The dictionary representing the ASVETTE event
    google_dict (dict): The dictionary representing the Google Calendar event

    Returns:
    bool: True if there is a difference between the two events, False otherwise
    """
    nb_diff: int = 0
    for key, valeur in asv_dict.items():
        # Si la valeur ASVETTE est différente de la valeur dans le calendrier
        if valeur != google_dict[key]:
            print('ASVETTE {key}: {valeur}\n'
                  'GOOGLE {key}: {google_dict[key]}\n')
            nb_diff += 1
    return True if nb_diff > 0 else False


def add_google_event(service, google_id: str, event: dict) -> None:
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
        # Si l'événement a été supprimé du calendrier. L'id existe et cela génère une erreur.
        if error.resp.status == 409:
            update_google_event(service, google_id, event)
        else:
            print(f"Une erreur s'est produite: {error}")
            sys.exit(1)


def update_google_event(service, google_id: str, event: dict) -> None:
    """
    This function updates an event in a Google Calendar using the Google Calendar API.

    Parameters:
    service (googleapiclient.discovery.Resource): The Google Calendar API service.
    google_id (str): The ID of the Google Calendar.
    event (dict): The event to be updated in the Google Calendar.

    Returns:
    None
    """
    updated_event: dict = service.events().update(calendarId=google_id,
                                                  eventId=event['id'],
                                                  body=event).execute()
    print(f'Événement mis à jour: {updated_event.get("summary")}')


def check_google_events(service, act: str, cal_id: str, liste_asvette: pd.DataFrame,
                        liste_google: pd.DataFrame) -> tuple[int, int, int]:
    """
    Vérifie si les événements d'une activité ASVETTE sont présents sur un calendrier Google.
    Si un événement n'est pas présent, il est ajouté.
    Si un événement est présent mais différent, il est mis à jour.
    Retourne un tuple contenant:
    - Le nombre d'événements identiques.
    - Le nombre d'événements différents.
    - Le nombre d'événements absents du calendrier Google.

    Parameters:
    service (googleapiclient.discovery.Resource): The Google Calendar API service.
    act (str): The name of the activity.
    cal_id (str): The ID of the Google Calendar.
    liste_asvette (pd.DataFrame): The list of events from ASVETTE.
    liste_google (pd.DataFrame): The list of events from Google Calendar.

    Returns:
    tuple[int, int, int]: A tuple containing the number of identical events, the number of
    different events and the number of absent events.
    """
    nb_identical: int = 0
    nb_different: int = 0
    nb_absentes: int = 0
    for index, row in liste_asvette.iterrows():
        event: dict = get_asvette_event_row_dict(row.to_dict())
        # Si la sortie (id) n'est pas dans le calendrier, on l'ajoute
        if liste_google is None or row['Id'] not in liste_google['Id'].values:
            print(f"La Sortie {row['Subject']} n'existe pas sur Google Calendar.")
            nb_absentes += 1
            add_google_event(service, cal_id, event)
        # Si la sortie (id) est dans le calendrier, on compare les champs
        else:
            # On stocke l'index de la sortie dans le dataframe Google
            google_index: int = (liste_google[liste_google['Id'] == row['Id']]
                                 .index.item())
            if diff_asvette_google(row.to_dict(),
                                   liste_google.iloc[google_index].to_dict()):
                print(
                    f"La sortie {row['Subject']} de l'activité {act} "
                    f"n'est pas la même que sur Google Calendar")
                nb_different += 1
                update_google_event(service, cal_id, event)
            else:
                nb_identical += 1
    return nb_identical, nb_different, nb_absentes


def main() -> None:
    credentials = get_credentials()
    service = get_service(credentials)
    # On passe en revue les activités
    for activity, value in ACTIVITIES.items():
        asvette_id: int = value['asvette_id']
        google_id: str = value['google_id']
        print(f"---------\n{activity}\n")
        # 1. Recherche des sorties pour l'activité sur le site ASVETTE
        print(f"Recherche des sorties {activity} sur le site ASVETTE...")
        liste_sorties: pd.DataFrame = get_asvette_events(asvette_id)
        # Si aucune sortie ASVETTE, Alors on passe à l'activité suivante
        if liste_sorties.shape[0] == 0:
            print(f"Aucune sortie {activity} trouvée")
            continue
        print(f"Nombre de sorties asvette pour l'activité {activity} : {len(liste_sorties)}")
        # 2. Recherche des sorties pour l'activité sur Google Calendar
        print(f"\nRecherche des sorties {activity} sur Google Calendar...")
        liste_google_events: pd.DataFrame | None = get_google_events(service, google_id)
        nb_google: int = 0 if liste_google_events is None else len(liste_google_events)
        print(f"Nombre de sorties Google pour l'activité {activity} : {nb_google}")
        print("")
        # Si des sorties existent dans le calendrier. On passe en revue la liste :
        ident, diff, absent = check_google_events(service, activity, google_id, liste_sorties,
                                                  liste_google_events)
        print(f"\nsorties {activity} identiques: {ident}\n"
              f"sorties {activity} différentes: {diff}\n"
              f"sorties {activity} absentes: {absent}́")


if __name__ == '__main__':
    ic.disable()
    main()
