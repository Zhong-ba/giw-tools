const { ArgumentParser } = require("argparse");
const { SingleBar } = require("cli-progress");
const { existsSync, writeFileSync, readdirSync, rmdirSync, mkdirSync } = require("fs");
const { join } = require("path");
const stringify = require("json-stringify-pretty-compact");

const LANGUAGES = ["EN"];
const TEXTMAPS = {};

/**
 * Options set by command line arguments and defaults.
 */
const OPTIONS = {
  output_dir: require("D:/WikiGenshin/0 - Data/tools/scriptconfig.json").RepoPath + "/MappedExcelBinOutput_EN",
  mapped_dir: require("D:/WikiGenshin/0 - Data/tools/scriptconfig.json").RepoPath + "/MappedToID",
  textMap_dir: require("D:/WikiGenshin/0 - Data/tools/scriptconfig.json").RepoPath + "/TextMap",
  textmapprefix: "TextMap",
  excel_dir: require("D:/WikiGenshin/0 - Data/tools/scriptconfig.json").RepoPath + "/ExcelBinOutput",
  files: [],
  idOnly: false,
  clean: false,
  remove: false,
  addIcon: false,
  keepHash: false,
  keepId: false,
  debug: false,
};

/**
 * Excel with id's as key to value pairs for quick lookup.
 */
const EXCEL = {
  NPC: {},
  MATERIAL: {},
  REWARD: {},
  AVATAR: {},
  WEAPON: {},
  FURNITURE: {},
  ARTIFACT: {},
  MONSTER: {},
  MONSTER_DESCRIBE: {},
  MONSTER_AFFIX: {},
  CARD_CHAR: {},
  CARD: {}
};

/**
 * Main Function
 */
function main() {

  // Parse the Arguments.
  const parser = new ArgumentParser({
    description: "Genshin Data Excel Mapping."
  });

  parser.add_argument("-o", "--output", { help: "output directory." });
  parser.add_argument("-m", "--mapped", { help: "mapped excel directory." });
  parser.add_argument("-t", "--textmapdir", { help: "input TextMap directory." });
  parser.add_argument("-tp", "--textmapprefix", { help: "TextMap file name prefix." });
  parser.add_argument("-e", "--exceldir", { help: "input excel JSON directory." });
  parser.add_argument("-l", "--languages", { help: "TextMap language (comma separated). [default: EN]" });
  parser.add_argument("-f", "--files", { help: "The files to map (comma separated). [default: ALL]" });
  parser.add_argument("-c", "--clean", { action: "store_const", const: true, help: "cleans output directories." });
  parser.add_argument("-r", "--remove", { action: "store_const", const: true, help: "removes empty values (String, Arrays, Objects)." });
  parser.add_argument("-i", "--addIcon", { action: "store_const", const: true, help: "adds icon to rewards." });
  parser.add_argument("-k", "--keepHash", { action: "store_const", const: true, help: "keeps the hash keys." });
  parser.add_argument("-ki", "--keepId", { action: "store_const", const: true, help: "keeps the ids of Avatars, NPCs, Rewards." });
  parser.add_argument("-d", "--debug", { action: "store_const", const: true, help: "print debug statements." });
  parser.add_argument("-id", "--idOnly", { action: "store_const", const: true, help: "only map the Excel ids." });

  // Assign the Arguments.
  let parsed_args = parser.parse_args();
  if (parsed_args.output) OPTIONS.output_dir = parsed_args.output;
  if (parsed_args.mapped) OPTIONS.mapped_dir = parsed_args.mapped;
  if (parsed_args.textmapdir) OPTIONS.textMap_dir = parsed_args.textmapdir;
  if (parsed_args.textmapprefix) OPTIONS.textmapprefix = parsed_args.textmapprefix;
  if (parsed_args.exceldir) OPTIONS.excel_dir = parsed_args.exceldir;
  if (parsed_args.languages) {
    if (parsed_args.languages == "ALL") {
      LANGUAGES.forEach(language => {
        if (existsSync(join(OPTIONS.textMap_dir, `${OPTIONS.textmapprefix}${language}.json`))) {
          TEXTMAPS[language] = require(join(OPTIONS.textMap_dir, `Text${language}.json`))
        }
      });
    } else {
      let languages = parsed_args.languages.split(",");
      if (languages.length > 0) {
        languages.forEach(language => {
          if (!LANGUAGES.includes(language)) return console.log(`${language} is not a valid language.`);
          TEXTMAPS[language] = require(join(OPTIONS.textMap_dir, `${OPTIONS.textmapprefix}${language}.json`))
        });
      }
    }
  } else {
    TEXTMAPS["EN"] = require(join(OPTIONS.textMap_dir, `${OPTIONS.textmapprefix}EN.json`))
  }
  if (parsed_args.files) {
    let file_names = parsed_args.files.split(",");
    OPTIONS.files = file_names.map(file => {
      let path = join(OPTIONS.excel_dir, file + ".json");
      if (!existsSync(path)) return console.log(`${path} is not a valid excel file path.`);
      else return file + ".json";
    });
    if (OPTIONS.files.includes(undefined)) return;
  }
  if (parsed_args.idOnly) OPTIONS.idOnly = parsed_args.idOnly
  if (parsed_args.remove) OPTIONS.remove = parsed_args.remove;
  if (parsed_args.clean) OPTIONS.clean = parsed_args.clean;
  if (parsed_args.addIcon) OPTIONS.addIcon = parsed_args.addIcon;
  if (parsed_args.keepHash) OPTIONS.keepHash = parsed_args.keepHash;
  if (parsed_args.keepId) OPTIONS.keepId = parsed_args.keepId;
  if (parsed_args.debug) OPTIONS.debug = parsed_args.debug;

  // Debug statements
  if (OPTIONS.debug) console.log({ TEXTMAPS: Object.keys(TEXTMAPS), OPTIONS });

  // Clean directories
  if (OPTIONS.clean) {
    rmdirSync(OPTIONS.output_dir, { recursive: true });
    rmdirSync(OPTIONS.mapped_dir, { recursive: true });
    process.exit(0)
  }

  // Parse
  excelMap();
}

/**
 * maps the excel OPTIONS.files.
 */
function excelMap() {
  const bar = new SingleBar({ stopOnComplete: true });
  if (OPTIONS.idOnly) return mapToId();
  mapToId();
  let files = OPTIONS.files.length > 0 ? OPTIONS.files : readdirSync(OPTIONS.excel_dir);
  bar.start(files.length, 0);
  files.forEach(filename => {
    if (filename === "DialogExcelConfigData.json") {
      if (OPTIONS.debug) console.log(`Skipping ${filename}`);
      bar.increment();
      return;
    }
    if (OPTIONS.debug) console.log(`Mapping ${filename}`);
    let file = require(join(OPTIONS.excel_dir, filename));
    save(mapObject(file, filename.replace(".json", "")), OPTIONS.output_dir, filename.replace(".json", ""));
    bar.increment()
  })
}

/**
 * Saves the object to file.
 * @param {any} data The data to save.
 * @param {string} path The file directory to save in.
 * @param {string} name The file name.
 * @param {string} type the file extension. Default json.
 */
function save(data, path, name, type = "json") {
  if (!existsSync(path)) mkdirSync(path);
  writeFileSync(join(path, `${name}.${type}`), type == "json" ? stringify(data, { maxLength: 100 }) : data);
}

/**
 * Maps the items Array.
 * @param {any[]} items The Array to map.
 * @param {String} excel Name of Excel file.
 * @returns Mapped Array.
 */
function mapArray(items, excel) {
  if (OPTIONS.remove) items = items.filter(item => !isEmpty(item));
  return items.map((item) => {
    if (Array.isArray(item)) {
      return mapArray(item, excel);
    } else if (typeof item == "object") {
      return mapObject(item, excel);
    } else {
      return item;
    }
  })
}

/**
 * Maps the item Object.
 * @param {any} item The Object to map.
 * @param {String} excel Name of Excel file.
 * @returns Mapped Object.
 */
function mapObject(item, excel) {
  if (OPTIONS.remove) Object.entries(item).forEach(([key, value]) => {
    if (isEmpty(value)) delete item[key];
  });
  if (Array.isArray(item)) return mapArray(item, excel);
  let result = {};
  Object.entries(item).map(([prop, value]) => {
    prop = prop.charAt(0).toUpperCase() + prop.slice(1)
    if (prop.indexOf("Hash") != -1) {
      let text = getText(value);
      if (OPTIONS.keepHash) result[prop] = value;
      if (!(OPTIONS.remove && text == "")) {
        if (OPTIONS.keepHash) result[prop.replace("Hash", "Value")] = text;
        else result[prop] = text;
      }
    } else if (prop == "TalkRole") {
      if (OPTIONS.keepId) {
        result[prop] = {
          Type: value.Type,
          Id: value.Id,
          Name: EXCEL.NPC[value.Id]?.name
        }
      } else {
        result[prop] = {
          Type: value.Type,
          Id: EXCEL.NPC[value.Id]?.name || value.Id
        }
      }
    } else if ((prop == "RewardIdList") && Array.isArray(value)) {
      result[prop] = value.map(reward => {
        if (OPTIONS.keepId) return { Id: reward, Reward: EXCEL.REWARD[reward] };
        else return EXCEL.REWARD[reward] || reward;
      });
    } else if ((prop == "RewardId" || prop == "RewardID") && excel != "RewardExcelConfigData") {
      if (OPTIONS.keepId) result[prop] = { Id: value, Reward: EXCEL.REWARD[value] || value };
      else result[prop] = EXCEL.REWARD[value] || value;
    } else if (prop == "InputVec" || prop == "OutputVec" || prop == "QualityOutputVec" || prop == "CostItems" || prop == "MaterialItems" || prop == "PreviewItems") {
      if (OPTIONS.keepId) {
        result[prop] = value.reduce((acc, curr) => {
          if (!OPTIONS.remove || !isEmpty(curr)) acc.push({
            Id: curr.Id,
            Name: getItem(curr.Id).name,
            Count: curr.Count
          });
          return acc;
        }, []);
      } else {
        result[prop] = value.reduce((acc, curr) => {
          if (!OPTIONS.remove || !isEmpty(curr)) acc.push({
            Id: getItem(curr.Id).name,
            Count: curr.Count
          });
          return acc;
        }, []);
      }
    } else if (prop == "BasicRewardId" || prop == "BonusRewardId" || prop == "FinishRewardId" || prop == "FirstPassRewardId" || prop == "FirstPassReward" || prop == "SuccessRewardId" || prop == "FailureRewardId") {
      if (OPTIONS.keepId) result[prop] = { Id: value, Reward: EXCEL.REWARD[value] };
      else result[prop] = EXCEL.REWARD[value] || value;
    } else if (prop == "AvatarId" || prop.includes("CharacterId")) {
      if (OPTIONS.keepId) result[prop] = { Id: value, Name: EXCEL.AVATAR[value]?.name };
      else result[prop] = EXCEL.AVATAR[value] || value;
    } else if (prop == "FavoriteNpcExcelIdVec") {
      result[prop] = value.map(avatar => {
        if (OPTIONS.keepId) return { Id: avatar, Name: EXCEL.AVATAR[avatar]?.name };
        else return EXCEL.AVATAR[avatar] || avatar;
      });
    } else if (prop == "NpcId") {
      if (OPTIONS.keepId) {
        result[prop] = Array.isArray(value) ? value.map(npc => ({ Id: npc, Name: EXCEL.NPC[npc]?.name })) : ({ Id: value, Name: EXCEL.NPC[value]?.name });
      } else {
        result[prop] = Array.isArray(value) ? value.map(npc => EXCEL.NPC[npc]?.name || npc) : (EXCEL.NPC[value]?.name || value);
      }
    } else if (Array.isArray(value) && (prop.includes("Desc") || prop == "Tips")) {
      result[prop] = value.map(effect => getText(effect));
    } else if (prop == "ItemId" || prop == "CombineId" || prop == "ResultItemId" || prop == "FurnitureItemID" || prop == "WeaponId") {
      if (OPTIONS.keepId) {
        result[prop] = { Id: value, Name: getItem(value).name };
      } else {
        result[prop] = getItem(value).name;
      }
    } else if (prop == "TrialAvatarParamList") {
      result[prop] = [EXCEL.AVATAR[value[0]]?.name || value[0], value[1]]
    } else if (prop == "TrialWeaponParamList") {
      result[prop] = [EXCEL.WEAPON[value[0]]?.name || value[0], value[1]]
    } else if (prop == "AppendPropList" || prop == "FirstMonsterList" || prop == "SecondMonsterList" || prop == "PEBNHLAOCBO") {
      result[prop] = value.map(monster => EXCEL.MONSTER_DESCRIBE[monster]?.name)
    } else if (Array.isArray(value) && prop == "OKFHEMAKLNN") { // GCGTalkDetailExcelConfigData
      result[prop] = value.map(text => getText(text));
    } else if (prop == "CharacterList") {
      result[prop] = Array.isArray(value) ? value.map(item => EXCEL.CARD_CHAR[item] || getText(item)) : item;
    } else if (prop == "WaitingCharacterList") {
      result[prop] = Array.isArray(value) ? value.map(item => ({ Id: EXCEL.CARD_CHAR[item.Id || item.id], CondCount: item.CondCount || item.condCount }) || getText(item)) : item;
    } else if (prop == "CardList") {
      result[prop] = Array.isArray(value) ? value.map(item => EXCEL.CARD[item] || getText(item)) : item;
    } else if (prop == "Affix" && excel != "MonsterAffixExcelConfigData") {
      result[prop] = Array.isArray(value) ? value.map(item => EXCEL.MONSTER_AFFIX[item]?.name || getText(item)) : item;
    } else if (prop == "MonsterId") {
      result[prop] = value
      result["MonsterName"] = EXCEL.MONSTER[value]?.name;
    } else if (prop == "DescribeId") {
      result[prop] = value
      result["DescribeName"] = EXCEL.MONSTER_DESCRIBE[value]?.name;
    } else if (Array.isArray(value)) {
      result[prop] = mapArray(value, excel);
    } else if (typeof value == "object") {
      result[prop] = mapObject(value, excel);
    } else {
      result[prop] = getText(value);
    }
  });
  return result;
}

/**
 * Get the Text in the textmap(s).
 * @param {any} key potential textmap hash key.
 * @returns The text of the key from textmaps if it exists, otherwise empty string.
 */
function getText(key) {
  let result = {};
  Object.entries(TEXTMAPS).forEach(([code, map]) => {
    let value = map[String(key)];
    result[code] = value != undefined ? value : key;
  })
  let values = Object.values(result);
  if (values.every((value) => value == "")) result = "";
  else if (values.every((value) => value == values[0])) result = values[0];
  else if (Object.keys(result).length == 1) result = values[0];
  return result;
}

/**
 * Check if the value is empty. 
 * @param {any} value Value to check for.
 * @returns Returns if the value is empty.
 */
function isEmpty(value) {
  if (value == "") return true;
  else if (Array.isArray(value) && (value.length == 0 || value.every(isEmpty))) return true;
  else if (typeof value == "object" && (Object.keys(value).length == 0 || Object.values(value).every(isEmpty))) return true;
  else return false;
}

/**
 * Get the Item.
 * @param {any} id ID of the Item.
 * @returns The object with name of the item or the ID.
 */
function getItem(id) {
  let item = EXCEL.WEAPON[id] || EXCEL.ARTIFACT[id] || EXCEL.FURNITURE[id] || EXCEL.MATERIAL[id];
  if (item) return item;
  else return {
    name: id,
    icon: ""
  };
}

/**
 * Map frequently used Excels with id's as key to value.
 */
function mapToId() {
  materialsToId();
  npcsToId();
  avatarsToId();
  furnitureToId();
  weaponToId();
  artifactToId();
  monsterToId();
  monsterToDescribeId();
  affixToId();
  rewardsToId();
  cardCharToId();
  cardToId();
  save(EXCEL.MATERIAL, OPTIONS.mapped_dir, "MaterialsExcelConfigData");
  save(EXCEL.NPC, OPTIONS.mapped_dir, "NpcExcelConfigData");
  save(EXCEL.AVATAR, OPTIONS.mapped_dir, "AvatarExcelConfigData");
  save(EXCEL.FURNITURE, OPTIONS.mapped_dir, "HomeWorldFurnitureExcelConfigData");
  save(EXCEL.WEAPON, OPTIONS.mapped_dir, "WeaponExcelConfigData");
  save(EXCEL.ARTIFACT, OPTIONS.mapped_dir, "ReliquaryExcelConfigData");
  save(EXCEL.MONSTER, OPTIONS.mapped_dir, "MonsterExcelConfigData");
  save(EXCEL.MONSTER_DESCRIBE, OPTIONS.mapped_dir, "MonsterDescribeExcelConfigData");
  save(EXCEL.MONSTER_AFFIX, OPTIONS.mapped_dir, "MonsterAffixExcelConfigData");
  save(EXCEL.REWARD, OPTIONS.mapped_dir, "RewardExcelConfigData");
  save(EXCEL.CARD_CHAR, OPTIONS.mapped_dir, "GCGCharExcelConfigData");
  save(EXCEL.CARD, OPTIONS.mapped_dir, "GCGDeckCardExcelConfigData");
}

/**
 * Maps Materials to id.
 * @returns {[Object]} Materials Mapped to id.
 */
function materialsToId() {
  if (!existsSync(join(OPTIONS.excel_dir, "MaterialExcelConfigData.json"))) {
    console.error(`${join(OPTIONS.excel_dir, "MaterialExcelConfigData.json")} does not exist.`);
    return process.exit();
  }
  let data = require(join(OPTIONS.excel_dir, "MaterialExcelConfigData.json"));
  Object.values(data).forEach(material => {
    EXCEL.MATERIAL[material.Id || material.id] = {
      name: getText(material.NameTextMapHash || material.nameTextMapHash),
      icon: material.Icon || material.icon
    };
  });
}

/**
 * Maps Rewards to id.
 * @returns {[Object]} Rewards Mapped to id.
 */
function rewardsToId() {
  if (!existsSync(join(OPTIONS.excel_dir, "RewardExcelConfigData.json"))) {
    console.error(`${join(OPTIONS.excel_dir, "RewardExcelConfigData.json")} does not exist.`);
    return process.exit();
  }
  let rewards = require(join(OPTIONS.excel_dir, "RewardExcelConfigData.json"));
  rewards.forEach(reward => {
    let result = [];
    (reward.RewardItemList || reward.rewardItemList)?.forEach(item => {
      if (item.ItemId || item.itemId) {
        let res = {
          ItemId: getItem(item.ItemId || item.itemId).name || (item.ItemId || item.itemId),
          ItemCount: item.ItemCount || item.itemCount
        }
        if (OPTIONS.addIcon && getItem(item.ItemId || item.itemId).icon) res["ItemIcon"] = getItem(item.ItemId || item.itemId).icon;
        result.push(res)
      }
    })
    EXCEL.REWARD[reward.RewardId || reward.rewardId] = result;
  });
}

/**
 * Maps NPC name to id.
 * @returns {Object} Names Mapped to id.
 */
function npcsToId() {
  if (!existsSync(join(OPTIONS.excel_dir, "NpcExcelConfigData.json"))) {
    console.error(`${join(OPTIONS.excel_dir, "NpcExcelConfigData.json")} does not exist.`);
    return process.exit();
  }
  let data = require(join(OPTIONS.excel_dir, "NpcExcelConfigData.json"));
  Object.values(data).forEach(npc => {
    EXCEL.NPC[npc.Id] = {
      name: getText(npc.NameTextMapHash || npc.nameTextMapHash)
    }
  });
}

/**
 * Maps Avatars to id.
 * @returns {Object} Avatars to id.
 */
function avatarsToId() {
  if (!existsSync(join(OPTIONS.excel_dir, "AvatarExcelConfigData.json"))) {
    console.error(`${join(OPTIONS.excel_dir, "AvatarExcelConfigData.json")} does not exist.`);
    return process.exit();
  }
  let data = require(join(OPTIONS.excel_dir, "AvatarExcelConfigData.json"));
  Object.values(data).forEach(avatar => {
    EXCEL.AVATAR[avatar.Id || avatar.id] = {
      name: getText(avatar.NameTextMapHash || avatar.nameTextMapHash),
      icon: avatar.IconName || avatar.iconName
    };
  });
}

/**
 * Maps Furniture to id.
 * @returns {Object} Furniture to id.
 */
function furnitureToId() {
  if (!existsSync(join(OPTIONS.excel_dir, "HomeWorldFurnitureExcelConfigData.json"))) {
    console.error(`${join(OPTIONS.excel_dir, "HomeWorldFurnitureExcelConfigData.json")} does not exist.`);
    return process.exit();
  }
  let data = require(join(OPTIONS.excel_dir, "HomeWorldFurnitureExcelConfigData.json"));
  Object.values(data).forEach(furniture => {
    EXCEL.FURNITURE[furniture.Id || furniture.id] = {
      name: getText(furniture.NameTextMapHash || furniture.nameTextMapHash),
      icon: furniture.Icon || furniture.icon
    };
  });
}

/**
 * Maps Weapons to id.
 * @returns {Object} Weapon to id.
 */
function weaponToId() {
  if (!existsSync(join(OPTIONS.excel_dir, "WeaponExcelConfigData.json"))) {
    console.error(`${join(OPTIONS.excel_dir, "WeaponExcelConfigData.json")} does not exist.`);
    return process.exit();
  }
  let data = require(join(OPTIONS.excel_dir, "WeaponExcelConfigData.json"));
  Object.values(data).forEach(weapon => {
    EXCEL.WEAPON[weapon.Id || weapon.id] = {
      name: getText(weapon.NameTextMapHash || weapon.nameTextMapHash),
      icon: weapon.Icon || weapon.Icon
    };
  });
}

/**
 * Maps Artifacts to id.
 * @returns {Object} Artifact to id.
 */
function artifactToId() {
  if (!existsSync(join(OPTIONS.excel_dir, "ReliquaryExcelConfigData.json"))) {
    console.error(`${join(OPTIONS.excel_dir, "ReliquaryExcelConfigData.json")} does not exist.`);
    return process.exit();
  }
  let data = require(join(OPTIONS.excel_dir, "ReliquaryExcelConfigData.json"));
  Object.values(data).forEach(artifact => {
    EXCEL.ARTIFACT[artifact.Id || artifact.id] = {
      name: getText(artifact.NameTextMapHash || artifact.nameTextMapHash),
      icon: artifact.Icon || artifact.icon
    };
  });
}

/**
 * Maps Monsters to id.
 * @returns {Object} Monster to id.
 */
function monsterToId() {
  if (!existsSync(join(OPTIONS.excel_dir, "MonsterExcelConfigData.json"))) {
    console.error(`${join(OPTIONS.excel_dir, "MonsterExcelConfigData.json")} does not exist.`);
    return process.exit();
  }
  let data = require(join(OPTIONS.excel_dir, "MonsterExcelConfigData.json"));
  Object.values(data).forEach(monster => {
    EXCEL.MONSTER[monster.Id || monster.id] = EXCEL.MONSTER[monster.DescribeId || monster.describeId] = {
      name: getText(monster.NameTextMapHash || monster.nameTextMapHash)
    };
  });
}

/**
 * Maps Monsters to describe id.
 * @returns {Object} Monster to id.
 */
function monsterToDescribeId() {
  if (!existsSync(join(OPTIONS.excel_dir, "MonsterDescribeExcelConfigData.json"))) {
    console.error(`${join(OPTIONS.excel_dir, "MonsterDescribeExcelConfigData.json")} does not exist.`);
    return process.exit();
  }
  let data = require(join(OPTIONS.excel_dir, "MonsterDescribeExcelConfigData.json"));
  Object.values(data).forEach(monster => {
    EXCEL.MONSTER_DESCRIBE[monster.Id || monster.id] = EXCEL.MONSTER_DESCRIBE[monster.DescribeId || monster.describeId] = {
      name: getText(monster.NameTextMapHash || monster.nameTextMapHash)
    };
  });
}

/**
 * Maps monster affix to affix name.
 * @returns {Object} Monster affix to id.
 */
function affixToId() {
  if (!existsSync(join(OPTIONS.excel_dir, "MonsterAffixExcelConfigData.json"))) {
    console.error(`${join(OPTIONS.excel_dir, "MonsterAffixExcelConfigData.json")} does not exist.`);
    return process.exit();
  }
  let data = require(join(OPTIONS.excel_dir, "MonsterAffixExcelConfigData.json"));
  Object.values(data).forEach(affix => {
    EXCEL.MONSTER_AFFIX[affix.Id || affix.id] = EXCEL.MONSTER_AFFIX[affix.DescribeId || affix.describeId] = {
      name: getText(affix.Affix || affix.affix)
    };
  });
}

/**
 * Maps Character Cards to id.
 * @returns {Object} Character Card to id.
 */
function cardCharToId() {
  if (!existsSync(join(OPTIONS.excel_dir, "GCGCharExcelConfigData.json"))) {
    console.error(`${join(OPTIONS.excel_dir, "GCGCharExcelConfigData.json")} does not exist.`);
    return process.exit();
  }
  let data = require(join(OPTIONS.excel_dir, "GCGCharExcelConfigData.json"));
  Object.values(data).forEach(card => {
    EXCEL.CARD_CHAR[card.Id || card.id] = getText(card.NameTextMapHash || card.nameTextMapHash)
  });
}

/**
 * Maps Action Cards to id.
 * @returns {Object} Action Card to id.
 */
function cardToId() {
  if (!existsSync(join(OPTIONS.excel_dir, "GCGDeckCardExcelConfigData.json"))) {
    console.error(`${join(OPTIONS.excel_dir, "GCGDeckCardExcelConfigData.json")} does not exist.`);
    return process.exit();
  }
  let data = require(join(OPTIONS.excel_dir, "GCGDeckCardExcelConfigData.json"));
  Object.values(data).forEach(card => {
    EXCEL.CARD[card.Id || card.id] = EXCEL.MATERIAL[card.ItemId || card.itemId]?.name
  });
}

main();