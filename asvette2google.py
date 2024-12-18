#!/usr/bin/env python3
"""
Ce script va rechercher la liste des sorties pour chaque activité sur ASVETTE.
I lva ensuite récupérer la liste des sorties présentes dans le calendrier Google correspondant.
En fonction des résultats :
- On ajoute les sorties de l'activité ASVETTE qui n'existent pas sur Google Calendar.
- On met à jour les sorties de l'activité ASVETTE qui ont changé.
"""
import argparse
import os
import sys
import time

import requests
import pandas as pd
import datetime
import httplib2
import urllib.parse
from ast import literal_eval
from bs4 import BeautifulSoup
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from icecream import ic
import logging

ic.configureOutput(includeContext=True)

SCRIPT_PATH = os.path.dirname(os.path.abspath(__file__))

SCOPES: list[str] = ["https://www.googleapis.com/auth/calendar"]
TOKEN: str = os.path.join(SCRIPT_PATH, "token.json")

URL: str = "https://asvel.limoog.net/public/pages/liste-sortie.php?Pass%C3%A9es=F&Activite="
URL_SORTIE_BASE: str = "https://asvette.limoog.net/public/pages/info-sortie.php?id="

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


def start_logging(log_file_path: str):
    # Set up logging
    logging.basicConfig(filename=log_file_path, level=logging.INFO,
                        format='%(asctime)s - %(levelname)s - %(message)s')


class Zap:

    def __init__(self, webhook: str | None):
        self.webhook: str | None = webhook
        self.start_time: str = datetime.datetime.now().strftime('%H:%M:%S')
        self.end_time: str = ''
        self.payload: dict = {
            'start': self.start_time,
            'end': '',
            'result': '',
        }

    def post(self) -> None:
        self.end_time = datetime.datetime.now().strftime('%H:%M:%S')
        self.payload['end'] = self.end_time
        try:
            r = requests.post(self.webhook, data=self.payload)
            logging.info(f"Zapier action finished with status: {r.status_code}")
        except HttpError as e:
            logging.error(e)
        except TimeoutError as e:
            logging.error(e)

    def add(self, result: str) -> None:
        self.payload['result'] += result


class CommandLineArguments:

    def __init__(self):
        parser = argparse.ArgumentParser(description="Run the script with an optional log file path.")
        parser.add_argument('--log', type=str, default='asvette.log',
                            help="Chemin absolu vers le fichier de logs (défaut : asvette.log)")
        parser.add_argument('--hook', type=str, default=None,
                            help="URL d'un webhook Zapier qui capturera le résultat de l'automatisation.")
        self.arguments = parser.parse_args()
        self.log_file: str = os.path.abspath(self.arguments.log)
        self.webhook: str | None = None if self.arguments.hook is None else self._get_zapier_hook()

    def _get_zapier_hook(self) -> str | None:
        try:
            parsed_url = urllib.parse.urlparse(self.arguments.hook)

            if parsed_url.scheme == 'https' and parsed_url.netloc == 'hooks.zapier.com':
                return "https://hooks.zapier.com" + parsed_url.path
        except ValueError:
            return None


class GoogleCalendar:

    def __init__(self, service, name: str, calendar_id: str):
        self.service = service
        self.name: str = name
        self.id: str = calendar_id
        self.events: pd.DataFrame = self._get_events()
        self.is_events_empty: bool = self.events.empty
        self.nb_events: int = self.events.shape[0]

    def _get_events(self):
        """
            Cette fonction va chercher les sorties de l'activité sur Google Calendar
            et les mettre en forme dans un DataFrame.
            """
        # Call the Calendar API
        now: str = datetime.datetime.now().isoformat() + "Z"  # 'Z' indicates UTC time
        try:
            events_result = (
                self.service.events()
                .list(
                    calendarId=self.id,
                    timeMin=now,
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )
            events: list = events_result.get("items", [])
        except HttpError as error:
            logging.error(f"Une erreur s'est produite: {error}")
            sys.exit(1)
        except httplib2.error.ServerNotFoundError as error:
            logging.error(f"Une erreur s'est produite: {error}")
            sys.exit(1)
        event_list: list[list[str]] = [['Id', 'Subject', SD_str, ST_str,
                                        ED_str, ET_str, ADE_str,
                                        'Description', 'Location', 'Private']]
        for event in events:
            row = self._get_event_row(event)
            event_list.append(row)
        df: pd.DataFrame = pd.DataFrame(event_list[1:], columns=event_list[0])
        return df

    def add_event(self, event: dict) -> None:
        """
        Ajoute un nouvel événement dans le calendrier Google en utilisant l'API Google Calendar.
        :param: event (dict) : Événement à ajouter. Dictionnaire tel que décrit ici :
        https://developers.google.com/calendar/api/v3/reference/events/insert

        :return: Message indiquant le résultat de l'opération.
        :rtype: Str
        """
        try:
            added_event: dict = self.service.events().insert(calendarId=self.id,
                                                             body=event).execute()
            logging.info(f'Événement créé: {added_event.get("summary")}')
        except HttpError as error:
            # Si l'événement a été supprimé du calendrier. L'id existe et cela génère une erreur.
            if error.resp.status == 409:
                self.update_event(event)
            else:
                logging.error(f"Une erreur s'est produite: {error}\n"
                              f"{event.get('summary')} n'a pas pu être ajouté.\n{event}")

    def update_event(self, event: dict) -> None:
        """
        This function updates an event in a Google Calendar using the Google Calendar API.

        Parameters:
        service (googleapiclient.discovery.Resource): The Google Calendar API service.
        google_id (str): The ID of the Google Calendar.
        event (dict): The event to be updated in the Google Calendar.

        Returns:
        None
        """
        try:
            updated_event: dict = self.service.events().update(calendarId=self.id,
                                                               eventId=event['id'],
                                                               body=event).execute()
            logging.info(f'Événement mis à jour: {updated_event.get("summary")}')
        except HttpError as error:
            logging.error(f"Une erreur s'est produite: {error}\n{event.get('summary')} n'a \
            pas pu être mis à jour.\n{event}")

    @staticmethod
    def _get_event_row(event: dict) -> list:
        """
        Cette fonction prend un événement Google Calendar en entrée et renvoie
        la ligne correspondante au format ASVETTE.

        :param event: Un événement Google Calendar
        :type event: dict
        :return: la ligne correspondante au format CSV/ASVETTE
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


class Activity:
    def __init__(self, name: str, asvette_id: int, calendar_id: str):
        self.name: str = name
        self.id: int = asvette_id
        self.cal_id: str = calendar_id
        self.url: str = URL + str(self.id)  # URL pour ASVETTE
        self.table = self._get_html_table()
        self.events: pd.DataFrame = self._get_events()
        self.nb_events: int = self.events.shape[0]
        self.is_events_empty: bool = self.events.empty

    def get_row_dict(self, row_id: int) -> dict:
        """
        Cette fonction transforme un dictionnaire représentant une sortie ASVETTE
        en un dictionnaire correspondant à l'API Google Calendar.
        :param row_id: Index dans le Dataframe des sorties
        :return: dictionnaire représentant la sortie ASVETTE en format Google Calendar
        :rtype: dict
        """
        row: pd.Series = self.events.iloc[row_id]
        s_date: str = row[SD_str]
        e_date: str = row[ED_str]
        s_time: str = row[ST_str]
        e_time: str = row[ET_str]
        if row[ADE_str] == 'TRUE':
            start: str = r"{" + f"'date': '{s_date}', 'timeZone': 'Europe/Paris'" + r"}"
            end: str = r"{" + f"'date': '{e_date}', 'timeZone': 'Europe/Paris'" + r"}"
        else:
            start = r"{" + f"'dateTime': '{s_date}T{s_time}', 'timeZone': 'Europe/Paris'" + r"}"
            end = r"{" + f"'dateTime': '{e_date}T{e_time}', 'timeZone': 'Europe/Paris'" + r"}"
        asvette_id: int = int(row['Id'].split('id')[-1])
        url: str = URL_SORTIE_BASE + str(asvette_id)
        source: str = r"{" + f"'title': 'ASVETTE', 'url': '{url}'" + r"}"
        description: str = row['Description']
        return_dict = {
            'id': row['Id'],
            'summary': row['Subject'],
            'location': row['Location'],
            'description': description,
            'start': literal_eval(start),
            'end': literal_eval(end),
            'source': literal_eval(source),
        }
        return return_dict

    @staticmethod
    def _get_rows(table) -> pd.DataFrame | None:
        # On récupère les en-têtes du tableau
        headers: list = [header.text.strip() for header in table.find_all("th")]
        rows: list = []
        for row in table.find_all("tr"):
            row_data: list = [cell.text.strip() for cell in row.find_all("td")]
            if row_data:
                rows.append(row_data)
                # print(f"ASVETTE: {row_data[1]}, date: {row_data[3]}")
        # On transforme le tableau en DataFrame
        df: pd.DataFrame = pd.DataFrame(rows, columns=headers)
        return df

    @staticmethod
    def _parse_time(x):
        if x == '':
            return pd.NaT
        else:
            return pd.to_datetime(x, format='%H:%M')

    def _get_html_table(self):
        # Send a GET request to the webpage
        response: requests.Response = requests.get(self.url)
        # Create a BeautifulSoup object from the response content
        soup: BeautifulSoup = BeautifulSoup(response.content, "html.parser")

        # On récupère le tableau des sorties
        return soup.find("table", {"id": "table_sortie"})

    def _get_events(self) -> pd.DataFrame:
        """
        Cette fonction va rechercher la liste des sorties pour chaque activité sur ASVETTE et mettre
        les informations dans un DataFrame.
        Si le dataframe est vide, on le retourne directement.
        S'il y a des sorties, on met en forme le Dataframe et on le retourne.
        """
        # On récupère les données du tableau
        df: pd.DataFrame = self._get_rows(self.table)
        if df.empty:
            return df
        # On transforme la colonne 'Date' en datetime
        df['Date'] = pd.to_datetime(df['Date'])
        # On transforme la colonne 'Départ' en datetime
        df['Heure'] = df['Heure'].apply(self._parse_time)
        df['Heure'] = pd.to_datetime(df['Heure'], format='%H:%M:%S', errors='coerce').dt.time

        first_char: str = 'Durée_first_char'
        # On extrait le nombre de jours de la colonne 'Durée'
        df[first_char] = df['Durée'].apply(lambda x: int(x.split(' ')[0]) - 1)
        # On ajoute une colonne 'Description' == à Difficulté + Encadrant + URL d'inscription
        df['Description'] = (df['Difficulté'] + ' | ' + df['Encadrant'] + '<BR><a href="' +
                             URL_SORTIE_BASE + df['Id'] + '">Inscription</a>')

        # On ajoute deux colonnes pour le bon format du CSV
        df[ET_str] = ''
        df['Private'] = ''
        # Ajoute TROIS heures à l'heure de début pour déterminer la fin si pas une sortie journée.
        df[ET_str] = df.apply(
            lambda x: (datetime.datetime.combine(datetime.date.today(), x['Heure'])
                       + datetime.timedelta(hours=3)).time()
            if not pd.isnull(x['Heure']) else '', axis=1)

        # On considère qu'une sortie dure la journée si pas d'heure de départ ou si le départ
        # est avant 10h00.
        df[ADE_str] = df['Heure'].apply(
            lambda x: 'TRUE' if pd.isnull(x) or x < pd.to_datetime('10:00:00').time() else 'FALSE')

        # On ajoute le nombre de jours pour créer la colonne 'End Date'
        df[ED_str] = df.apply(lambda ligne: ligne['Date'] +
                                            pd.DateOffset(
                                                days=ligne[first_char] + 1 if ligne[ADE_str] == 'TRUE' else ligne[
                                                    first_char]), axis=1)
        # On supprime la colonne 'Durée_first_char', plus besoin.
        df = df.drop(first_char, axis=1)
        df['Date'] = df['Date'].dt.strftime('%Y-%m-%d')
        df[ED_str] = df[ED_str].dt.strftime('%Y-%m-%d')

        df['Heure'] = df['Heure'].apply(
            lambda x: x.strftime('%H:%M:%S') if not pd.isnull(x) else '')
        df[ET_str] = df[ET_str].apply(lambda x: x.strftime('%H:%M:%S') if x else '')
        # On renomme les colonnes pour correspondre au format du fichier csv
        df = df.rename(columns={'Nom': 'Subject', 'Date': SD_str, 'Heure': ST_str,
                                'Lieu': 'Location'})
        df = df[['Id', 'Subject', SD_str, ST_str, ED_str, ET_str, ADE_str,
                 'Description', 'Location', 'Private']]
        df['Id'] = df['Id'].apply(lambda x: 'asvette' + 'act' + str(self.id) + 'id' + str(x))
        return df


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
        logging.info(f"Execution time: {end - start:.2f} seconds")
        return result

    return wrapper


def get_credentials(zap: Zap):
    """
    Retourne les credentials pour accéder aux APIs Google.

    Les credentials sont stockés dans un fichier token.json. Si le fichier n'existe pas,
    le programme lance le flux d'authentification et stocke les credentials dans le fichier
    token.json.
    """
    creds = None
    cred_file: str = os.path.join(SCRIPT_PATH, 'credentials.json')
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists(TOKEN):
        try:
            creds = Credentials.from_authorized_user_file(TOKEN, SCOPES)
        except RefreshError:
            msg: str = "Le token est invalide. Il faudra se reconnecter."
            logging.warning(msg)
            if zap.webhook is not None:
                zap.add(msg)
                zap.post()

            creds = None
            sys.exit(2)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                cred_file, SCOPES
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
        logging.error(f"Une erreur s'est produite: {error}")
        sys.exit(1)
    return service


def diff_asvette_google(asv_dict: dict, google_dict: dict) -> bool:
    """
    Check if an ASVETTE event is different from a Google Calendar event.

    Parameters:
    asv_dict (dict): The dictionary representing the ASVETTE event
    google_dict (dict): The dictionary representing the Google Calendar event

    Returns:
    bool: True if there is a difference between the two events, False otherwise
    """
    log_line: str = asv_dict['Subject']
    nb_diff: int = 0
    for key, valeur in asv_dict.items():
        # Si la valeur ASVETTE est différente de la valeur dans le calendrier
        if valeur != google_dict[key]:
            log_line += f' | {key}: {valeur} != {google_dict[key]}'
            nb_diff += 1
    logging.info(log_line)
    return True if nb_diff > 0 else False


def check_events(act: Activity, cal: GoogleCalendar) -> str:
    """
    Vérifie si les événements d'une activité ASVETTE sont présents sur un calendrier Google.
    Si un événement n'est pas présent, il est ajouté.
    Si un événement est présent, mais différent, il est mis à jour.
    Retourne un tuple contenant :
    - Le nombre d'événements identiques.
    - Le nombre d'événements différents.
    - Le nombre d'événements absents du calendrier Google.

    Parameters :
    act (Activity) : Une activité ASVETTE avec ses sorties.
    cal (GoogleCalendar) : Les événements Google Calendar correspondants é l'activité.

    Returns :
    str : Le résultat de l'opération avec le nombre de sorties inchangées, ajoutées et mises à jour.
    """
    nb_identical: int = 0
    nb_different: int = 0
    nb_absentes: int = 0
    for index, row in act.events.iterrows():
        event: dict = act.get_row_dict(int(str(index)))
        # Si la sortie (id) n'est pas dans le calendrier, on l'ajoute
        if cal.events is None or row['Id'] not in cal.events['Id'].values:
            nb_absentes += 1
            cal.add_event(event)  # ajoute 1 événement et imprime le résultat de l'opération.
        # Si la sortie (id) est dans le calendrier, on compare les champs.
        else:
            # On stocke l'index de la sortie dans le dataframe Google
            google_index: int = (cal.events[cal.events['Id'] == row['Id']].index.item())
            # Si les champs sont different, on met à jour le calendrier.
            if diff_asvette_google(row.to_dict(), cal.events.iloc[google_index].to_dict()):
                nb_different += 1
                cal.update_event(event)
            else:
                nb_identical += 1
    return (f"{act.name}: {nb_identical} identiques | "
            f"{nb_different} mises à jour | {nb_absentes} créées")


@timer
def main() -> None:
    args: CommandLineArguments = CommandLineArguments()
    start_logging(args.log_file)
    logging.info("starting...")
    zap: Zap = Zap(args.webhook)
    credentials = get_credentials(zap)
    service = get_service(credentials)
    # On passe en revue les activités
    for activity, value in ACTIVITIES.items():
        # 1. Recherche des sorties pour l'activité sur le site ASVETTE
        act = Activity(activity, value['asvette_id'], value['google_id'])
        # Si aucune sortie ASVETTE, Alors on passe à l'activité suivante
        if act.is_events_empty:
            logging.info(f"Aucune sortie {act.name} trouvée")
            continue
        # 2. Recherche des sorties pour l'activité sur Google Calendar
        cal: GoogleCalendar = GoogleCalendar(service, act.name, act.cal_id)
        # On passe en revue la liste des sorties pour ajout ou mise à jour du calendrier :
        check: str = check_events(act, cal)
        zap.add(check + '\n')
        logging.info(check)
    if zap.webhook is not None:
        zap.post()
    logging.info("Calendar update finished normally")


if __name__ == '__main__':
    ic.enable()
    main()
