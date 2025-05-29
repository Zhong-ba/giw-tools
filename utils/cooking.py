import os
import json
from PIL import Image, ImageDraw

from getConfig import CONFIG
from utils.files import write_file
from utils.misc import dict_to_table


def clamp(n, min_value, max_value):
    return max(min(n, max_value), min_value)


def parse_cooking_qte():
    with open(f'{CONFIG.EXCEL_PATH}/CookRecipeExcelConfigData.json', 'r', encoding = 'utf-8') as file:
        recipeexcel = {item['Id']: item for item in json.load(file)}
    
    out = {}
    
    for key, recipe in recipeexcel.items():
        name = recipe.get('NameTextMapHash')
        qteparams = recipe.get('QteParam').split(',')
        out[name] = {}
        out[name]['center'] = float(qteparams[0])
        out[name]['width'] = float(qteparams[1])
        
    file_write_path = f'{CONFIG.OUTPUT_PATH}/Recipe_Output.lua'
    
    write_file(file_write_path, f'return {dict_to_table(out)}')


def cooking_qte_image_gen(center, length):
    BG_PATH = 'Cook.webp'
    
    SIZE = 1240
    SCALE = 8  # Scale factor for anti-aliasing
    SCALED_SIZE = SIZE * SCALE
    THICKNESS = int(1 * SCALED_SIZE * 0.5) 
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
    
    # Cut out center
    mask = Image.new('L', (SCALED_SIZE, SCALED_SIZE), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.ellipse([SCALED_SIZE//2 - THICKNESS, SCALED_SIZE//2 - THICKNESS, SCALED_SIZE//2 + THICKNESS, SCALED_SIZE//2 + THICKNESS], fill=255)
    mask_draw.ellipse([SCALED_SIZE//2 - INNER_THICKNESS, SCALED_SIZE//2 - INNER_THICKNESS, SCALED_SIZE//2 + INNER_THICKNESS, SCALED_SIZE//2 + INNER_THICKNESS], fill=0)
    base_image.putalpha(mask)
    
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
    filename = f'Manual Cooking C-{int(center * 100)} W-{int(length * 100)}.png'
    try:
        final_image.save(f'{CONFIG.OUTPUT_PATH}/Cooking_QTE/{filename}')
        print(f'Successfully saved {filename}')
    except Exception as e:
        print(f'Error saving {filename}: {e}')


def cooking_qte_2():
    if not os.path.exists(f'{CONFIG.OUTPUT_PATH}/Cooking_QTE'):
        os.makedirs(f'{CONFIG.OUTPUT_PATH}/Cooking_QTE')
    
    for center in [0.3, 0.38, 0.4, 0.45, 0.48, 0.5, 0.52, 0.55, 0.6, 0.63, 0.65, 0.7, 0.72, 0.77, 0.8, 0.85]:
        for length in [0.17, 0.22, 0.27, 0.35, 0.4]:
            cooking_qte_image_gen(center, length)