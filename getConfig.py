from dataSource import load_config

CONFIG = None


class Config:
    def __init__(self, file):
        # Local asset folders and the previous dataset are optional (the hosted profile has none of them).
        self.IMAGE_PATH = file.get("ImgPath")
        self.TALENT_BG_PATH = file.get("TalentBGPath")
        self.EXCEL_PATH = f'{file["RepoPath"]}/MappedExcelBinOutput_EN'
        self.EXCEL_PATH_OLD = f'{file["RepoPathOld"]}/MappedExcelBinOutput_EN' if file.get("RepoPathOld") else None
        self.BIN_PATH = file.get('BinPath') or f'{file["RepoPath"]}/BinOutput'
        self.OUTPUT_PATH = file["OutputPath"]
    
    
CONFIG_FILE = load_config()
CONFIG = Config(CONFIG_FILE)