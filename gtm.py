#################
### IMPORTS
#################

import argparse
import httplib2
import gspread
import re
import datetime
from oauth2client.service_account import ServiceAccountCredentials
from apiclient.discovery import build
from oauth2client import client
from oauth2client import file
from oauth2client import tools

#################
### CREATE LIBRARIES
#################




#################
### GET DATA
#################

### GTM ACCOUNTS CONTAINERS TAGS
#################

# function to connect the GTM api
def GetService(api_name, api_version, scope, client_secrets_path):
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        parents=[tools.argparser])
    flags = parser.parse_args([])
    flow = client.flow_from_clientsecrets(
        client_secrets_path, scope=scope,
        message=tools.message_if_missing(client_secrets_path))
    storage = file.Storage(api_name + '.dat')
    credentials = storage.get()
    if credentials is None or credentials.invalid:
        credentials = tools.run_flow(flow, storage, flags)
    http = credentials.authorize(http=httplib2.Http())
    service = build(api_name, api_version, http=http)
    return service

# set the context
scope = ['https://www.googleapis.com/auth/tagmanager.readonly']
service = GetService('tagmanager', 'v2', scope, 'secrets/gtm_secret.json')

# get GTM accounts
gtm_accounts = service.accounts().list().execute()['account']

# create the gtm_table : final JSON
gtm_table = {}

# create an array with accounts we want to get
interesting_accounts = ['FixeAds', 'OLX_PL', 'OLX_UA', 'OLX_KZ', 'Autovit ATLAS', 'Otomoto', 'otoDOM atlas', 'OLX.ro', 'Olx.bg', 'olx.BG', 'OLX_UZ', 'Imovirtual', 'Storia.ro', 'Otodom.ua']
interesting_containers_fixeads = ['GTM-KDMWP7', 'GTM-W9NK32']

# variable to only filter on the Default Workspace
workspace_filter = 'Default Workspace'

# loop
for acc in gtm_accounts:

    # i run the script for interesting gtm accounts
    if acc['name'] in interesting_accounts:

        # get the path and name to add the gtm name as a key
        account_path = acc['path']
        account_name = acc['name']
        gtm_table[account_name] = {
            'account_id': int(acc['accountId']),
            'containers': [],
            'triggers': []
        }

        # get the array of JSONs from containers then based on the path from accounts
        containers = service.accounts().containers().list(parent=account_path).execute()['container']

        # then i check each workspace from each container
        for con in containers:
            if acc['name'] == 'FixeAds' and con['publicId'] not in interesting_containers_fixeads:
                continue
            else:
                container_path = con['path']

                # and i build a JSON with info i want
                containers_json = {
                    'name': con['name'],
                    'tracking_id': con['publicId'],
                    'container_id': int(con['containerId']),
                    'platform': None,
                    'tags': [],
                    'triggers': []
                }

                # condition to know if there's info about usage (apps or html)
                if 'usageContext' in con:
                    containers_json['platform'] = con['usageContext'][0]
                else:
                    containers_json['platform'] = 'unknown'

                # get the array of JSONs from workspaces
                workspaces = service.accounts().containers().workspaces().list(parent=container_path).execute()['workspace']

                # check for tags inside Default workspaces
                for wor in workspaces:
                    if wor['name'] == workspace_filter:
                        tags = service.accounts().containers().workspaces().tags().list(parent=wor['path']).execute()
                        triggers = service.accounts().containers().workspaces().triggers().list(parent=wor['path']).execute()

                        # if there is a configured tag
                        if 'tag' in tags:
                            tags = tags['tag']
                            for tag in tags:
                                tags_json = {
                                    'name': tag['name'],
                                    'tag_id': int(tag['tagId']),
                                    'type': tag['type'],
                                    'triggers': None,
                                    'url': tag['tagManagerUrl'],
                                    'params': tag['parameter'],
                                    'timestamp': int(tag['fingerprint'][:-3])
                                }

                                # if there is a trigger in the tag
                                if 'firingTriggerId' in tag:
                                    tags_json['triggers'] = tag['firingTriggerId']

                                # add the JSONs in the containers_json JSON
                                containers_json['tags'].append(tags_json)

                        # if there is a trigger in the container
                        if 'trigger' in triggers:
                            triggers = triggers['trigger']
                            for tri in triggers:
                                triggers_json = {
                                    'name': tri['name'],
                                    'trigger_id': int(tri['triggerId']),
                                    'type': tri['type'],
                                    'url': tri['tagManagerUrl'],
                                    'timestamp': int(tri['fingerprint'][:-3]),
                                    'custom_event_present': False,
                                    'custom_event_name': None,
                                    'custom_event_type': None,
                                    'custom_event_filters': False
                                }

                                # if the trigger is a custom event
                                if tri['type'] == 'customEvent':
                                    triggers_json['custom_event_present'] = True
                                    triggers_json['custom_event_name'] = tri['customEventFilter'][0]['parameter'][1]['value']
                                    triggers_json['custom_event_type'] = tri['customEventFilter'][0]['type']

                                    # if there's a specific filter
                                    if 'filter' in tri:
                                        triggers_json['custom_event_filters'] = True

                                # add the JSONs in the containers_json JSON
                                containers_json['triggers'].append(triggers_json)

                # add the containers_json in the gtm_table
                gtm_table[account_name]['containers'].append(containers_json)

### GTM NINJA MATRIX
#################

# define a scope to get the Ninja matrix
scope = ['https://spreadsheets.google.com/feeds',
         'https://www.googleapis.com/auth/drive']

# set credentials
credentials = ServiceAccountCredentials.from_json_keyfile_name('secrets/sheets_secret.json', scope)

# shortcut to the google sheet library
gc = gspread.authorize(credentials)

# get the Ninja matrix
ninja = gc.open("Ninja - test").sheet1

# get the location of the 'GTM' columns
cell_gtm = ninja.find('GTM')

# get the location of trackPage
cell_trackpage = ninja.find('trackPage')

# get the location of trackEvent
cell_trackevent = ninja.find('trackEvent')

# get the location of the next filled cell in column A
col_a = ninja.col_values(1)
starting_track_event = col_a[cell_trackevent.row:]
cell_trackevent_end = 0
i = 0
while cell_trackevent_end == 0:
    if starting_track_event[i] is not '':
        cell_trackevent_end = i + cell_trackevent.row
    else:
        i += 1

# now get the list of events from GTM columns
row_start = cell_trackpage.row +1
row_end = cell_trackevent_end
range_web = [x for x in ninja.col_values(cell_gtm.col +1)[row_start:row_end] if x != '']
range_android = [x for x in ninja.col_values(cell_gtm.col +3)[row_start:row_end] if x != '']
range_ios = [x for x in ninja.col_values(cell_gtm.col +5)[row_start:row_end] if x != '']


#################
### CREATE JSON
#################

# setup a library of known trackers
trackers = {
    'vendors': {
        'fbevents': 'facebook',
        'facebook': 'facebook',
        'optimizely': 'optimizely',
        'gtm-survey{': 'survey monkey',
        '.surveyMonkeyGTMPopup': 'survey monkey',
        'widget.surveymonkey.com': 'survey monkey',
        'creativecdn.com': 'rtb',
        'doubleclick.net': 'doubleclick',
        'cxense': 'cxense',
        'branch.io': 'branch',
        'egoicommerce': 'e-goi',
        'hotjar': 'hotjar',
        'navdmp': 'navegg',
        'mixpanel': 'mixpanel',
        'gemius.pl': 'gemius',
        'userzoom': 'user zoom',
        'plugins.soclminer': 'social miner',
        'soclTracking': 'social miner',
        'mail.ru': 'mail ru',
        'yandex.ru': 'yandex',
        'trovit.com': 'trovit',
        'criteo': 'criteo'
    },
    'tracks': {
        'cXenseParse': 'cxense',
        'fbq(': 'facebook',
        'mixpanel.track': 'mixpanel',
        'DFPAudiencePixel': 'doubleclick',
        'optimizely': 'optimizely',
        'creativecdn': 'rtb'
    },
    'type': {
        'html': 'custom html',
        'cegg': 'crazy egg',
        'awct': 'adwords',
        'sp': 'adwords',
        'gclidw': 'adwords',
        'ua': 'google analytics',
        'ga': 'google analytics',
        'asp': 'adroll',
        'fsl': 'form submit listener',
        'funct': 'call function'
    }
}

# create regex to understand what is in a custom html tag
rgx_script = re.compile("""^.*(script>|iframe>|<meta).*$""")
rgx_lib = re.compile("""^(?=.*src=|.*src =)(?=.*.js).*$""")

# make a list of our trackers
vendors_list = list(trackers['vendors'].keys())
type_list = list(trackers['type'].keys())
tracks_list = list(trackers['tracks'].keys())

# create the table
final_data = []


# loop
for k in gtm_table:
    for con in gtm_table[k]['containers']:
        for tag in con['tags']:

            # I create a JSONs which will be the final one per tag
            tag_json = {
                'account': k,
                'container': con['name'],
                'container_tag': con['tracking_id'],
                'platform': con['platform'],
                'tag_name': tag['name'],
                'last_update': datetime.datetime.fromtimestamp(tag['timestamp']).strftime('%Y-%m-%d %H:%M'),
                'url': tag['url'],
                'type': 'unknown',
                'script_added': 'no',
                'library_called': 'no',
                'pixel_called': 'no',
                'vendors': 'none',
                'triggered': 'no',
                'triggers': []
            }

            # if the tag type is a type I know, then run this
            if tag['type'] in type_list:
                tag_json['type'] = trackers['type'][tag['type']]

                # and if it's a custom html type, i want to know what is the custom html called
                if tag['type'] == 'html':
                    tag_script = tag['params'][0]['value'].replace('\n', '')
                    tag_json['vendors'] = []

                    # if a script is inserted
                    if re.match(rgx_script, tag_script):
                        tag_json['script_added'] = 'yes'

                        # if a javascript library is called
                        if re.match(rgx_lib, tag_script):
                            tag_json['library_called'] = 'yes'

                            # and if this library is in our known list, add the name into the array
                            if any(v in tag_script for v in vendors_list):
                                for ven in vendors_list:
                                    if ven in tag_script:
                                        tag_json['vendors'].append(trackers['vendors'][ven])

                            else:
                                tag_json['vendors'].append('unknown')

                            tag_json['vendors'] = tag_json['vendors'][0]

                        # if it's not a library, then is it a pixel ?
                        elif any(v in tag_script for v in tracks_list):
                            tag_json['pixel_called'] = 'yes'
                            for ven in tracks_list:
                                if ven in tag_script:
                                    tag_json['vendors'].append(trackers['tracks'][ven])

            # if the tag type is not in the list
            else:
                tag_json['type'] = 'unknown'

            # if the tag is triggered
            if 'triggers' in tag:
                if tag['triggers'] is not None:
                    tag_json['triggers'] = tag['triggers']
                    tag_json['triggered'] = 'yes'


            # then finally add the json to the array
            final_data.append(tag_json)

import json
with open('dashboard/src/amelie_gtmtags.js', 'w') as fp:
    fp.write('var gtmData = ')
    json.dump(final_data, fp)

#################
### MATCH TRIGGERS AND NINJA EVENTS
#################
# match triggers and ninja events
# get the number of tag type global

global_stats = {
    'triggered': {
        'data': ['yes', 'no'],
        'values': [0, 0]
    },
    'type': {
        'data': ['custom html', 'adwords', 'google analytics', 'others'],
        'colors': ['#1A659E','#45AC8B', '#FAAE3F', '#707575'],
        'values': [0, 0, 0, 0],
        'echart': []
    },
    'vendors': {
        'data': [],
        'values': [],
        'echart': []
    },
    'global': {
        'accounts': interesting_accounts,
        'triggered': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        'not_triggered': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        'custom_html': {
            'values': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            'library': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            'facebook': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            'surveymonkey': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            'rtb': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            'others': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            'unknown': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
        },
        'adwords': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        'ga': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        'others': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
    },
    'sunburst': []
}

for row in final_data:

    # get triggers
    if row['triggered'] == 'yes':
        global_stats['triggered']['values'][0] += 1
        global_stats['global']['triggered'][global_stats['global']['accounts'].index(row['account'])] += 1

        # get types
        if row['type'] not in global_stats['type']['data']:
            global_stats['type']['values'][global_stats['type']['data'].index('others')] += 1
        else:
            global_stats['type']['values'][global_stats['type']['data'].index(row['type'])] += 1

        # get vendors
        if row['vendors'] is not 'none':
            if isinstance(row['vendors'], list):
                if len(row['vendors']) > 0:
                    row['vendors'] = row['vendors'][0]
                else:
                    row['vendors'] = 'unknown'

            if row['vendors'] not in global_stats['vendors']['data']:
                global_stats['vendors']['data'].append(row['vendors'])
                global_stats['vendors']['values'].append(1)

            else:
                global_stats['vendors']['values'][global_stats['vendors']['data'].index(row['vendors'])] += 1

        # get global stats
        if row['type'] == 'adwords':
            global_stats['global']['adwords'][global_stats['global']['accounts'].index(row['account'])] += 1
        elif row['type'] == 'google analytics':
            global_stats['global']['ga'][global_stats['global']['accounts'].index(row['account'])] += 1
        elif row['type'] == 'custom html':
            global_stats['global']['custom_html']['values'][global_stats['global']['accounts'].index(row['account'])] += 1
            if row['library_called'] == 'yes' and row['vendors'] != 'survey monkey':
                global_stats['global']['custom_html']['library'][global_stats['global']['accounts'].index(row['account'])] += 1
            if row['vendors'] == 'survey monkey':
                global_stats['global']['custom_html']['surveymonkey'][global_stats['global']['accounts'].index(row['account'])] += 1
            elif row['vendors'] == 'facebook':
                global_stats['global']['custom_html']['facebook'][global_stats['global']['accounts'].index(row['account'])] += 1
            elif row['vendors'] == 'rtb':
                global_stats['global']['custom_html']['rtb'][global_stats['global']['accounts'].index(row['account'])] += 1
            elif row['vendors'] == 'unknown':
                global_stats['global']['custom_html']['unknown'][global_stats['global']['accounts'].index(row['account'])] += 1
            else:
                global_stats['global']['custom_html']['others'][global_stats['global']['accounts'].index(row['account'])] += 1
        else:
            global_stats['global']['others'][global_stats['global']['accounts'].index(row['account'])] += 1

    else:
        global_stats['triggered']['values'][1] += 1
        global_stats['global']['not_triggered'][global_stats['global']['accounts'].index(row['account'])] += 1

for ty in global_stats['type']['data']:
    json = {'name': None,'value': None}
    json['name'] = ty
    json['value'] = global_stats['type']['values'][global_stats['type']['data'].index(ty)]
    global_stats['type']['echart'].append(json)

for ve in global_stats['vendors']['data']:
    json = {'name': None, 'value': None}
    json['name'] = ve
    json['value'] = global_stats['vendors']['values'][global_stats['vendors']['data'].index(ve)]
    global_stats['vendors']['echart'].append(json)



# create sunburst
for acc in global_stats['global']['accounts']:

    json = {
        'name': acc,
        'children': []
    }

    for tag in list(global_stats['global'].keys()):
        if tag not in ['accounts', 'triggered', 'not_triggered']:
            tagjson = {
                'name': tag
            }
            if tag == 'custom_html':
                tagjson['value'] = global_stats['global']['custom_html']['values'][global_stats['global']['accounts'].index(acc)]
                tagjson['children'] = []
                for chl in list(global_stats['global']['custom_html'].keys()):
                    if chl not in ['values','library']:
                        vendorjson = {
                            'name': chl,
                            'value': global_stats['global']['custom_html'][chl][global_stats['global']['accounts'].index(acc)]
                        }
                        tagjson['children'].append(vendorjson)
            else:
                tagjson['value'] = global_stats['global'][tag][global_stats['global']['accounts'].index(acc)]
            json['children'].append(tagjson)

    global_stats['sunburst'].append(json)

import json
with open('dashboard/src/amelie_gtmstats.js', 'w') as fp:
    fp.write('var gtmStats = ')
    json.dump(global_stats, fp)


