import os
import re

from getConfig import CONFIG
from utils.files import write_file
from utils.pageinfo import pageinfo


def file_redirect(source, target):
    if not os.path.exists(f'{CONFIG.OUTPUT_PATH}/Redirects'):
        os.makedirs(f'{CONFIG.OUTPUT_PATH}/Redirects')

    file_write_path = f'{CONFIG.OUTPUT_PATH}/Redirects/{source}.wikitext'
    file_write = f"{pageinfo('File:' + source)}\n#REDIRECT [[File:{target}]]\n[[Category:Redirect Pages]]"

    write_file(file_write_path, file_write)
    

def main_redirect(source, target):
    if not os.path.exists(f'{CONFIG.OUTPUT_PATH}/Redirects'):
        os.makedirs(f'{CONFIG.OUTPUT_PATH}/Redirects')
        
    filename = re.sub(r'[^\w\s]', '', source)

    file_write_path = f'{CONFIG.OUTPUT_PATH}/Redirects/{filename}.wikitext'
    file_write = f"{pageinfo(source)}\n#REDIRECT [[{target}]]\n[[Category:Redirect Pages]]"

    write_file(file_write_path, file_write)
    
    
def redirects_from_str(in_str):
    for line in in_str.split("\n"):
        pagename, target = line.split(r"%%%")
        
        main_redirect(pagename, target)