/** Install/build the frontend even when CI initially installs only root packages. */
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const cwd = fileURLToPath(new URL("../commerce-testbed/frontend/", import.meta.url));
const env = { ...process.env };
delete env.npm_config_allow_scripts;
for (const args of [["ci", "--no-audit", "--no-fund"], ["run", "build:assets"]]) {
  const result = spawnSync("npm", args, { cwd, env, stdio: "inherit" });
  if (result.error) throw result.error;
  if (result.status !== 0) process.exit(result.status ?? 1);
}
