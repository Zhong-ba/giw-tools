import os
import json

from getConfig import CONFIG

def fix_str(str_input):
    return str_input.replace('"', r'\"')


def dict_to_table(python_dict, indent = 0):
    indent_str = '\t' * indent
    lua_table = "{\n"
    
    for key, value in python_dict.items():
        lua_key = f'{indent_str}\t["{fix_str(key)}"]'
        
        if isinstance(value, str):
            lua_value = f'"{fix_str(value)}"'
        elif isinstance(value, dict):
            lua_value = dict_to_table(value, indent + 1)
        elif isinstance(value, list):
            list_values = ", ".join([f'"{fix_str(item)}"' if isinstance(item, str) else str(item) for item in value])
            lua_value = "{" + list_values + "}"
        else:
            lua_value = str(value)
            
        lua_table += f"{lua_key} = {lua_value},\n"
        
    lua_table += f"{indent_str}}}"

    return lua_table


def capkeys():
    for root, dirs, files in os.walk(CONFIG.EXCEL_PATH):
        for file in files:
            if file.endswith('.json'):
                file_path = os.path.join(root, file)
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                def capitalize_keys(obj):
                    if isinstance(obj, dict):
                        new_obj = {}
                        for k, v in obj.items():
                            new_key = k.capitalize() if k and k[0].islower() else k
                            new_obj[new_key] = capitalize_keys(v)
                        return new_obj
                    elif isinstance(obj, list):
                        return [capitalize_keys(item) for item in obj]
                    else:
                        return obj
                
                new_data = capitalize_keys(data)
                
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(new_data, f, indent=2, ensure_ascii=False)