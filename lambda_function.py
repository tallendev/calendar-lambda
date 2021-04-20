#!/usr/bin/python3

import config
import datetime
import json
import pytz
import requests
import sys

import dateutil.parser
import os.path

from google.auth.transport.requests import Request
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


SLACK_URL="https://slack.com/api/chat.postMessage"
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']

# time in minutes
ONE_WEEK = 10080
ONE_MONTH = 43200
# auto check time limit
AUTO_TIME = 15

# relies on service token from google api dashboard; different than user token which we don't use anymore
def get_service():
    creds = None
    creds = service_account.Credentials.from_service_account_file('credentials.json', scopes=SCOPES)
    service = build('calendar', 'v3', credentials=creds)

    return service

# grabs all events between now and now+minutes from API, then trims events that have already started
def get_events_in_range(minutes):
    service = get_service()
    dt_now = datetime.datetime.utcnow()
    now = dt_now.isoformat() + 'Z' # 'Z' indicates UTC time
    time_limit = ((dt_now + datetime.timedelta(minutes=minutes)).isoformat()) + 'Z'
    events_result = service.events().list(calendarId=config.CALENDAR_ID, timeMin=now, timeMax=time_limit,
                                           singleEvents=True, orderBy='startTime').execute()

    # we replace now and dt_now here because of timezone weirdness
    now = datetime.datetime.now(datetime.timezone.utc)
    dt_now = None

    events = events_result.get('items', [])
    ret_events = []
    for event in events:
        start = event['start'].get('dateTime', event['start'].get('date'))
        start = dateutil.parser.isoparse(start)
        delta = start - now
        # should have already filtered events between now and max time; just want to make sure we do not report
        # events that have already started
        if (delta > datetime.timedelta(minutes=0)):
            ret_events.append(event) 

    return ret_events

# For each channel, grabs events within time delta and removes channel tag from event subject, also 
#   verifies timezone which is hardcoded as CST for SC21
# minutes: how far in the future to look for events
# channels: which channels to search for events for; channels are searched and posted independently
def calendar_request_events(minutes, channels):
    ret = {}
    events = get_events_in_range(minutes)
    print("events:", events)

    for key in channels:
        ret[key] = []
    for event in events:
        text_content = event["summary"]
        fkey = None
        for key in channels:
            if f"[{key}]" in text_content:
                text_content = text_content.replace(f"[{key}]", '').strip()
                fkey = key
                break  
        else:
            continue
        start = event['start'].get('dateTime', event['start'].get('date'))
        start = dateutil.parser.isoparse(start)
        start = start.astimezone(pytz.timezone("US/Central"))
        ret[fkey].append((text_content, start))

    # return should be a dict (channel key) of lists (events) containing tuple of 
    # (event name, datetime with CST timezone)
    return ret

# Posts responses to requests to slack, depending on message content.
# text: raw text from slack message if here because of @ tag; should contain keyword
# uid: uid who sent raw text
# channelid: channel originating request
def keyword_response(text, uid, channelid):
    time_str = ""
    time_max = None
    channel_keys = []

    text = text.lower()
    
    print("processing keyword response, text:", text)
    # what kind of message are we responding to?
    if "who" in text:
        payload = {'channel': config.CHANNEL_TAGS[config.CHANNEL_ID_TAG[channelid]], 'text': f"hey <@{uid}>, my name is SVOLidarity, the volunteer who reminds you of all your upcoming events, but you can call me svollie."}
        headers = {"Authorization": f"Bearer {config.BOT_OAUTH}", 'Content-Type': 'application/json'}

        print("got a who request")
        print("headers:", headers)
        print("payload:", payload)
        r = requests.post(SLACK_URL, json=payload, headers=headers)
        return
    elif "week" in text:
        time_str = "7 days"
        time_max = ONE_WEEK 
        channel_keys = [config.CHANNEL_ID_TAG[channelid]]
    elif "month" in text:
        time_str = "30 days"
        time_max = ONE_MONTH
        channel_keys = [config.CHANNEL_ID_TAG[channelid]]
    elif "hey" in text or "hello" in text or "hi " in text:
        payload = {'channel': config.CHANNEL_TAGS[config.CHANNEL_ID_TAG[channelid]], 'text': f"Hi <@{uid}>!"}
        headers = {"Authorization": f"Bearer {config.BOT_OAUTH}", 'Content-Type': 'application/json'}

        print("got a hey request")
        print("headers:", headers)
        print("payload:", payload)
        r = requests.post(SLACK_URL, json=payload, headers=headers)
        return
        
    elif uid == None:
        time_str = f"{AUTO_TIME} minutes"
        time_max = AUTO_TIME
        channel_keys = config.CHANNEL_TAGS.keys()
    else:
        payload = {'channel': config.CHANNEL_TAGS[config.CHANNEL_ID_TAG[channelid]], 'text': f'<@{uid}> sorry, i dont know how to respond :( try one of these keywords: "week", "month", "who", "hello"'}
        headers = {"Authorization": f"Bearer {config.BOT_OAUTH}", 'Content-Type': 'application/json'}

        print("got a hey request")
        print("headers:", headers)
        print("payload:", payload)
        r = requests.post(SLACK_URL, json=payload, headers=headers)
        return

    print("minutes, channels:", time_max, ",", channel_keys)
    events_dicts = calendar_request_events(time_max, channel_keys)
    print("events dict:", events_dicts)

    # for all the channels, events returned, figure out a response
    for key, events in events_dicts.items():
        response = None
        if len(events) > 0:
            if uid != None:
                response = f'hey <@{uid}>, here are the event(s) coming up for {config.CHANNEL_STRINGS[key]} in the next {time_str}:\n'
            else: 
                #response = f'check out these upcoming events for {config.CHANNEL_STRINGS[key]} in the next {time_str}:\n'
                response = f'check out these events coming up in the next {time_str}:\n'
            for event in events:
                event_name = event[0]
                event_time = event[1]
                event_time = event_time.strftime('on %a %x at %X %Z')
                response += f"{event[0]} {event_time}\n"
        else:
            if uid != None:
                response = f"hey <@{uid}>, i didn't find any events for {config.CHANNEL_STRINGS[key]} in the next {time_str} : ("
            else:
                print (f"no upcoming events for autocheck in {key}")
                continue
            
        payload = {'channel': config.CHANNEL_TAGS[key], 'text':response}
        headers = {"Authorization": f"Bearer {config.BOT_OAUTH}", 'Content-Type': 'application/json'}
        r = requests.post(SLACK_URL, json=payload, headers=headers)
    return


# Filters out events that are just slack url verification; otherwise whould be user event
def process_user_event(event):
    mes_body = json.loads(event['body'])
    print("mes_body:", mes_body)
    print("mes_body[type]:", mes_body['type'])

    # there has to be a better way to unpack the JSON from slack
    # url verification is to ensure we actually own the endpoint
    if mes_body['type'] == "url_verification":
        print ("responding to challenge")
        challenge = mes_body['challenge']
        ret = {"content-type" : "text/plain", "challenge" : challenge}

    # should cover any slash commands or direct @bot tags that we implement
    elif mes_body['type'] == "event_callback":
        print("event callback caught")
        event = mes_body['event']
        if event['type'] == "app_mention":
            print("doing app mention")
            uid = event['user']
            text = event['text']
            channel = event['channel']
            ret = keyword_response(text, uid, channel)
        else:
            print("unhandled event_callback:", event['type'])
    else:
        print("unhandled event type:", mes_body['type'])

    return ret


# just determines if we have a default case of timer interrupt or if user requested info; default is fastpath.
def lambda_handler(event, context):

    print("event:", event)
    print("context:", context)

    ret = None
    # should be an auto-timer event
    if event == {} or event == None:
        # even though this isn't keyword it's simplest to lump this in as the null case
        ret = keyword_response("", None, "all")
    elif "body" in event:
        ret = process_user_event(event)
    else:
        print("no body in event?")

    print("done")
    return ret

if __name__== "__main__":
  lambda_handler(None, None)

