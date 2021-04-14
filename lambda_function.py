#!/usr/bin/python3

import sys
import pytz
import datetime
import os.path
from googleapiclient.discovery import build

#from google_auth_oauthlib.flow import InstalledAppFlow

from google.oauth2 import service_account
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
import requests
import dateutil.parser

SLACK_URL="https://slack.com/api/chat.postMessage"
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']
CHANNEL_TAGS = {"test" : "#bottest"}

def lambda_handler(event, context):
    """Shows basic usage of the Google Calendar API.
    Prints the start and name of the next 10 events on the user's calendar.
    """

    print("event:", event)
    print("context:", context)

    creds = None
    creds = service_account.Credentials.from_service_account_file('credentials.json', scopes=SCOPES)

    service = build('calendar', 'v3', credentials=creds)

    # Call the Calendar API
    now = datetime.datetime.utcnow().isoformat() + 'Z' # 'Z' indicates UTC time
    print('Getting the upcoming 10 events')
    events_result = service.events().list(calendarId=config.CALENDAR_ID, timeMin=now,
                                        maxResults=10, singleEvents=True,
                                        orderBy='startTime').execute()
    events = events_result.get('items', [])

    now = datetime.datetime.now(datetime.timezone.utc)

    if not events:
        print('No upcoming events found.')
    for event in events:
        start = event['start'].get('dateTime', event['start'].get('date'))
        start = dateutil.parser.isoparse(start)
        delta = start - now
        if  delta <= datetime.timedelta(minutes=15) and delta >= (datetime.timedelta(minutes=0)):
            start = start.astimezone(pytz.timezone("US/Central"))
            headers = {"Authorization": f"Bearer {config.BOT_OAUTH}", 'Content-Type': 'application/json'}

            # figure out if event text needs to have tag removed
            text_content = event["summary"]
            for key in CHANNEL_TAGS.keys():
                if f"[{key}]" in text_content:
                    payload['channel'] = CHANNEL_TAGS[key]
                    text_content = text_content.replace(f"[{key}]", '').strip()
                    break  
            else:
                print("no event tag found:", text_context) 

            # setup payload
            payload = {'text': f'Upcoming Event: "{text_content}" at {start.strftime("%X")} CST'}

            print(payload)
            print()

            r = requests.post(SLACK_URL, json=payload, headers=headers)
            print(r)



if __name__== "__main__":
  lambda_handler(None, None)

