import json

CONFIG = None


class Config:
    def __init__(self, file):
        self.IMAGE_PATH = file["ImgPath"]
        self.TALENT_BG_PATH = file["TalentBGPath"]
        self.EXCEL_PATH = f'{file["RepoPath"]}/MappedExcelBinOutput_EN'
        self.EXCEL_PATH_OLD = f'{file["RepoPathOld"]}/MappedExcelBinOutput_EN'
        self.BIN_PATH = f'{file["RepoPath"]}/BinOutput'
        self.OUTPUT_PATH = file["OutputPath"]
    
    
with open('scriptconfig.json', 'r', encoding = 'utf-8') as file:
    CONFIG_FILE = json.load(file)
    CONFIG = Config(CONFIG_FILE)