'''THIS IS UNFINISHED AND IM TOO LAZY TO FINISH IT'''

import json

from getConfig import CONFIG


def parse_fishing_points():
    '''<%-- [PAGE_INFO]
    comment = #Please do not remove this struct. It's record contains some important information of edit. This struct will be removed automatically after you push edits.#
    pageTitle = #Fishing Point/Mont Esus East#
    pageID = #261067#
    revisionID = #1458412#
    contentModel = #wikitext#
    contentFormat = #text/x-wiki#
[END_PAGE_INFO] --%>

{{Fishing Point
|title         = Mont Esus East
|id            = 5010
|subarea       = Mont Esus East
|area          = Liffey Region
|region        = Fontaine
|description   = One of the fishing points registered with the Fontaine Fishing Association. Located on the shoals near Mont Esus, it has a rich variety of fish. Looking east from here, one can see the ruins of the Fontaine Research Institute's Central Laboratory...
|day           = Streaming Axe Marlin; Blazing Heartfeather Bass; Maintenance Mek: Initial Configuration; Ornamental Streaming Axe Marlin; Ornamental Blazing Heartfeather Bass; Ornamental Maintenance Mek: Initial Configuration
|night         = Streaming Axe Marlin; Maintenance Mek: Initial Configuration; Maintenance Mek: Situation Controller; Ornamental Streaming Axe Marlin; Ornamental Maintenance Mek: Initial Configuration; Ornamental Maintenance Mek: Situation Controller
|display limit = 5
|total         = 13
}}'''
    
    with open(f'{CONFIG.EXCEL_PATH}/FishPoolExcelConfigData.json', 'r', encoding = 'utf-8') as file:
        poolexcel = {item['Id']: item for item in json.load(file)}
        
    with open(f'{CONFIG.EXCEL_PATH_OLD}/FishPoolExcelConfigData.json', 'r', encoding = 'utf-8') as file:
        poolexcel_old = {item['Id']: item for item in json.load(file)}
        
    with open(f'{CONFIG.EXCEL_PATH_OLD}/../Testing/fishstock.json', 'r', encoding = 'utf-8') as file:
        fishstock = {item['Id']: item for item in json.load(file)}
    
    for id, item in poolexcel.items():
        if id in list(poolexcel_old.keys()):
            print(f'Skipping {id}.')
            continue
        
        title = item.get('PoolNameTextMapHash')