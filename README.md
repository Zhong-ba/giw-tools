# Genshin Wiki Tools
Utilities for generating updates for the [Genshin Impact Wiki](https://genshin-impact.fandom.com) from game data.

## Setup
### 1. Install Requirements
```bash
pip install -r requirements.txt
```
### 2. Create scriptconfig.json
Create a ``scriptconfig.json`` file in the root directory with the following:
```json
{
    "RepoPath": "<path to the current version GenshinData>",
    "RepoPathOld": "<path to the previous version GenshinData>",
    "ImgPath": "<path to extracted Texture2D images>",
    "TalentBGPath": "<path to talent backgrounds>",
    "OutputPath": "<output location>"
}
```