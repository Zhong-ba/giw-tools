import json

from getConfig import CONFIG


def ls_blessing_scan_targets(type_id):
    valid_list = []

    with open(f'{CONFIG.EXCEL_PATH}/BlessingScanExcelConfigData.json', 'r', encoding = 'utf-8') as file:
        blessingscanexcel = json.load(file)

    with open(f'{CONFIG.EXCEL_PATH}/MonsterExcelConfigData.json', 'r', encoding = 'utf-8') as file:
        monsterexcel = json.load(file)

    with open(f'{CONFIG.EXCEL_PATH}/GadgetExcelConfigData.json', 'r', encoding = 'utf-8') as file:
        gadgetexcel = json.load(file)

    with open(f'{CONFIG.EXCEL_PATH}/AnimalDescribeExcelConfigData.json', 'r', encoding = 'utf-8') as file:
        animaldescribeexcel = json.load(file)

    for item in blessingscanexcel:
        if item['TypeId'] != type_id:
            continue

        ref_id = item['RefId']

        if item['ScanType'] == 'BLESSING_SCAN_TYPE_MONSTER':
            for monster in monsterexcel:
                try:
                    if monster['DescribeId'] == ref_id:
                        try:
                            valid_list.append(monster['DescribeName'])
                        except KeyError:
                            try:
                                for animal in animaldescribeexcel:
                                    if animal['Id'] == ref_id:
                                        valid_list.append(animal['NameTextMapHash'])
                            except KeyError:
                                if isinstance(monster['NameTextMapHash'], str):
                                    valid_list.append(monster['NameTextMapHash'])
                                else:
                                    valid_list.append(monster['MonsterName'])
                except KeyError:
                    continue

        elif item['ScanType'] == 'BLESSING_SCAN_TYPE_GATHER':
            for gadget in gadgetexcel:
                if gadget['Id'] == ref_id:
                    valid_list.append(gadget['InteractNameTextMapHash'])

    return valid_list


def parse_blessing_scan():
    with open(f'{CONFIG.EXCEL_PATH}/BlessingScanTypeExcelConfigData.json', 'r', encoding = 'utf-8') as file:
        blessingscantypeexcel = json.load(file)

    output = ""

    for item in blessingscantypeexcel:
        name = item['TypeNameTextMapHash']
        type_id = item['TypeId']
        valid_list = list(set(ls_blessing_scan_targets(type_id)))

        list_text = ''
        for list_item in valid_list:
            list_text = list_text + f'{list_item}\n'

        output = output + f'=={name}==\n{list_text}\n'

    print(output)