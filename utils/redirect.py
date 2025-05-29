import os
import re

from getConfig import CONFIG
from utils.files import write_file


def file_redirect(target, source):
    if not os.path.exists(f'{CONFIG.OUTPUT_PATH}/Redirects'):
        os.makedirs(f'{CONFIG.OUTPUT_PATH}/Redirects')

    file_write_path = f'{CONFIG.OUTPUT_PATH}/Redirects/{source}.wikitext'
    file_write = (f"<%-- [PAGE_INFO]\n    comment = #Please do not remove this struct. It's record contains some "
                  f"important information of edit. This struct will be removed automatically after you push edits.#\n "
                  f"   pageTitle = #File:{target}#\n    pageID = ##\n    revisionID = ##\n    contentModel = ##\n    "
                  f"contentFormat = ##\n[END_PAGE_INFO] --%>\n\n#REDIRECT [[File:{source}]]\n[[Category:Redirect "
                  f"Pages]]")

    write_file(file_write_path, file_write)
    

def main_redirect(target, source):
    if not os.path.exists(f'{CONFIG.OUTPUT_PATH}/Redirects'):
        os.makedirs(f'{CONFIG.OUTPUT_PATH}/Redirects')
        
    filename = re.sub(r'[^\w\s]', '', source)

    file_write_path = f'{CONFIG.OUTPUT_PATH}/Redirects/{filename}.wikitext'
    file_write = (f"<%-- [PAGE_INFO]\n    comment = #Please do not remove this struct. It's record contains some "
                  f"important information of edit. This struct will be removed automatically after you push edits.#\n "
                  f"   pageTitle = #{source}#\n    pageID = ##\n    revisionID = ##\n    contentModel = ##\n    "
                  f"contentFormat = ##\n[END_PAGE_INFO] --%>\n\n#REDIRECT [[{target}]]\n[[Category:Redirect "
                  f"Pages]]")

    write_file(file_write_path, file_write)