const { readFileSync } = require("fs");
const { dirname, join, resolve } = require("path");

// Mirrors dataSource.py; keep the two resolvers in sync.
const SOURCES = { dimbreath: "AnimeGameData", gura: "YuanShenResources" };
const SETTINGS = { excel: ["ExcelSource", "dimbreath"], binoutput: ["BinOutputSource", "gura"] };
const REVISIONS = { excel: "ExcelRevision", binoutput: "BinOutputRevision" };

const configPath = resolve(process.env.GENSHIN_TOOLS_CONFIG || join(__dirname, "..", "scriptconfig.json"));
const config = JSON.parse(readFileSync(configPath, "utf8"));
const source = config.DataSource || "local";

if (!["local", "remote", "github"].includes(source)) {
  throw new Error('DataSource must be "local" or "remote" ("github" is accepted as "remote").');
}

if (source !== "local") {
  const root = join(dirname(configPath), ".data");
  const directories = {};
  try {
    const ready = JSON.parse(readFileSync(join(root, "ready.json"), "utf8"));
    for (const [role, [key, fallback]] of Object.entries(SETTINGS)) {
      const choice = config[key] || fallback;
      if (!(choice in SOURCES)) throw new Error(`${key} must be one of: ${Object.keys(SOURCES).join(", ")}.`);
      const revision = ready[role];
      if (!revision || !(revision.source in SOURCES)) throw Object.assign(new Error(role), { code: "ENOENT" });
      if (revision.source !== choice) {
        throw new Error(`The prepared ${role} data does not match ${key}. Run quickSetup.bat again.`);
      }
      const pinned = config[REVISIONS[role]] || "latest";
      if (pinned !== "latest" && pinned !== revision.commit) {
        throw new Error(`The prepared ${role} data does not match ${REVISIONS[role]}. Run quickSetup.bat again.`);
      }
      if (!/^[0-9a-f]{40}$/.test(revision.commit) || (role === "excel" && !/^[0-9a-f]{64}$/.test(revision.pipeline))) {
        throw new Error("Invalid dataset setup metadata.");
      }
      const cache = join(root, SOURCES[revision.source]);
      directories[role] = role === "excel"
        ? join(cache, "datasets", `${revision.commit}-${revision.pipeline.slice(0, 12)}`)
        : join(cache, "binoutput", revision.commit);
      const prepared = JSON.parse(readFileSync(join(directories[role], ".prepared.json"), "utf8"));
      if (JSON.stringify(Object.entries(prepared).sort()) !== JSON.stringify(Object.entries(revision).sort())) {
        throw new Error("Dataset setup metadata does not match. Run quickSetup.bat again.");
      }
    }
  } catch (error) {
    if (error.code !== "ENOENT") throw error;
    throw new Error("Remote data is not prepared. Run quickSetup.bat (or python setupData.py) first.");
  }
  config.RepoPath = directories.excel;
  config.BinPath = join(directories.binoutput, "BinOutput");
}

module.exports = config;
