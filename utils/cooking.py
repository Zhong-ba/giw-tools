import os
import json
import urllib.parse
import urllib.request
from PIL import Image, ImageDraw

from getConfig import CONFIG
import toolLog as report
from utils.files import write_file, write_file_pages
from utils.misc import dict_to_table

COOKING_FILE_PAGE = '''==Summary==
{{File
|categories = Manual Cooking Images
}}

==Licensing==
{{Fairuse}}'''


def clamp(n, min_value, max_value):
    return max(min(n, max_value), min_value)


BG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Cook.webp')


def cooking_qte_data():
    '''Recipe name -> {'center', 'width'} of its manual cooking dial.'''
    with open(f'{CONFIG.EXCEL_PATH}/CookRecipeExcelConfigData.json', 'r', encoding = 'utf-8') as file:
        recipeexcel = {item['Id']: item for item in json.load(file)}
    
    out = {}
    
    for recipe in recipeexcel.values():
        name = recipe.get('NameTextMapHash')
        qteparams = recipe.get('QteParam').split(',')
        out[name] = {
            'center': float(qteparams[0]),
            'width': float(qteparams[1]),
        }
    return out


def qte_file_name(center, length):
    # round() avoids float truncation such as int(0.29 * 100) == 28.
    return f'Manual Cooking C-{round(center * 100)} W-{round(length * 100)}.png'


def missing_wiki_files(names, api = 'https://genshin-impact.fandom.com/api.php', timeout = 30):
    '''The file names among names that have no File: page on the wiki.'''
    names, missing = list(names), set()
    for start in report.track(list(range(0, len(names), 50)), 'Checking wiki images in batches'):
        query = urllib.parse.urlencode({'action': 'query', 'format': 'json',
                                        'titles': '|'.join(f'File:{name}' for name in names[start:start + 50])})
        # Fandom rejects requests without a browser-like User-Agent.
        request = urllib.request.Request(f'{api}?{query}', headers = {'User-Agent': 'Mozilla/5.0 PainmeloTools'})
        with urllib.request.urlopen(request, timeout = timeout) as response:
            pages = json.load(response).get('query', {}).get('pages', {})
        missing.update(page['title'].removeprefix('File:') for page in pages.values() if 'missing' in page)
    return [name for name in names if name in missing]


def parse_cooking_qte():
    report.stage('Building Manual Cooking data')
    out = cooking_qte_data()
    file_write_path = f'{CONFIG.OUTPUT_PATH}/Manual_Cooking_data.lua'
    
    write_file(file_write_path, f'''--[=[<%-- [PAGE_INFO]
    pageTitle = #Module:Manual Cooking/data#
[END_PAGE_INFO] --%>--]=]

return {dict_to_table(out)}''')


def cooking_qte_image_gen(center, length):
    SIZE = 1240
    SCALE = 8  # Scale factor for anti-aliasing
    SCALED_SIZE = SIZE * SCALE
    INNER_THICKNESS = int((1 - 0.04066555965) * SCALED_SIZE * 0.5)
    
    Q1 = clamp(78 * (center - length / 2), 0, 78)
    Q2 = clamp(78 * (center - length / 8), 0, 78)
    Q3 = clamp(78 * (center + length / 8), 0, 78)
    Q4 = clamp(78 * (center + length / 2), 0, 78)
    
    TRANSPARENT = (0, 0, 0, 0)
    COLOR1 = (236, 233, 179, 255)  # #ECE9B3
    COLOR2 = (255, 192, 64, 255)   # #FFC040
    
    base_image = Image.new('RGBA', (SCALED_SIZE, SCALED_SIZE))
    draw = ImageDraw.Draw(base_image)
    
    # Draw pie chart sections
    draw.pieslice([0, 0, SCALED_SIZE, SCALED_SIZE], 231, 231 + Q1, fill=TRANSPARENT)
    draw.pieslice([0, 0, SCALED_SIZE, SCALED_SIZE], 231 + Q1, 231 + Q2, fill=COLOR1)
    draw.pieslice([0, 0, SCALED_SIZE, SCALED_SIZE], 231 + Q2, 231 + Q3, fill=COLOR2)
    draw.pieslice([0, 0, SCALED_SIZE, SCALED_SIZE], 231 + Q3, 231 + Q4, fill=COLOR1)
    draw.pieslice([0, 0, SCALED_SIZE, SCALED_SIZE], 231 + Q4, 309, fill=TRANSPARENT)
    
    # Mask to yellow section only
    mask2 = Image.new('L', (SCALED_SIZE, SCALED_SIZE), 0)
    mask2_draw = ImageDraw.Draw(mask2)
    mask2_draw.pieslice([0, 0, SCALED_SIZE, SCALED_SIZE], 231 + Q1, 231 + Q4, fill=255)
    mask2_draw.ellipse([SCALED_SIZE//2 - INNER_THICKNESS, SCALED_SIZE//2 - INNER_THICKNESS, SCALED_SIZE//2 + INNER_THICKNESS, SCALED_SIZE//2 + INNER_THICKNESS], fill=0)
    base_image.putalpha(mask2)
    
    # Crop
    black_mask = Image.new('L', (SCALED_SIZE, SCALED_SIZE), 0)
    black_mask_draw = ImageDraw.Draw(black_mask)
    black_mask_draw.pieslice([0, 0, SCALED_SIZE, SCALED_SIZE], 231, 309, fill=255)
    black_mask_draw.ellipse([SCALED_SIZE//2 - INNER_THICKNESS, SCALED_SIZE//2 - INNER_THICKNESS, SCALED_SIZE//2 + INNER_THICKNESS, SCALED_SIZE//2 + INNER_THICKNESS], fill=0)
    
    bbox = black_mask.getbbox()

    bar_final = base_image.crop(bbox)
    
    # Downscale (antialiasing)
    cropped_size = [int(size / SCALE) for size in bar_final.size]
    bar_final = bar_final.resize(cropped_size, Image.LANCZOS)
    
    # Add background
    background = Image.open(BG_PATH).convert("RGBA")
    
    canvas = Image.new('RGBA', background.size, (0, 0, 0, 0))
    bar_x = (canvas.width - bar_final.width) // 2
    canvas.paste(bar_final, (bar_x, 43), bar_final)
    
    final_image = Image.alpha_composite(background, canvas)
    
    # Save
    filename = qte_file_name(center, length)
    try:
        final_image.save(f'{CONFIG.OUTPUT_PATH}/Cooking_QTE/{filename}')
        report.info(f'Saved {filename}')
    except Exception as e:
        report.warning(f'Could not save {filename}: {e}')


def cooking_qte_2(only_missing = False):
    '''Draws a dial image for every center/width combination used by a recipe; returns the file names drawn.'''
    os.makedirs(f'{CONFIG.OUTPUT_PATH}/Cooking_QTE', exist_ok = True)
    combos = sorted({(value['center'], value['width']) for value in cooking_qte_data().values()})
    if only_missing:
        absent = set(missing_wiki_files(qte_file_name(*combo) for combo in combos))
        combos = [combo for combo in combos if qte_file_name(*combo) in absent]
    for center, length in report.track(combos, 'Drawing cooking dial images'):
        cooking_qte_image_gen(center, length)
    names = [qte_file_name(*combo) for combo in combos]
    write_file_pages(f'{CONFIG.OUTPUT_PATH}/Cooking_QTE', dict.fromkeys(names, COOKING_FILE_PAGE))
    return names