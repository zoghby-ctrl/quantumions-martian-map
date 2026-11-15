const fs = require("node:fs");
const source = fs.readFileSync("static/app.js", "utf8");
function arrayConstant(name) {
  const prefix = `const ${name} = `;
  const start = source.indexOf(prefix);
  if (start < 0) throw new Error(`Missing ${name}`);
  const valueStart = start + prefix.length;
  const end = source.indexOf(";", valueStart);
  return JSON.parse(source.slice(valueStart, end));
}
const routes = source.match(/const OFFLINE_PATHS = \{\s*classical: (\[[^\n]+\]),\s*quantum: (\[[^\n]+\]),/);
if (!routes) throw new Error("Missing offline route fixtures");
const paths = { classical: JSON.parse(routes[1]), quantum: JSON.parse(routes[2]) };
const obstacles = new Set(arrayConstant("OFFLINE_OBSTACLES").map(([r, c]) => `${r},${c}`));
for (const [name, path] of Object.entries(paths)) {
  if (path.some(([r, c]) => obstacles.has(`${r},${c}`))) throw new Error(`${name} enters crater cells`);
  for (let i = 1; i < path.length; i++) {
    const [r0, c0] = path[i - 1];
    const [r1, c1] = path[i];
    const dr = Math.abs(r1 - r0), dc = Math.abs(c1 - c0);
    if (dr > 1 || dc > 1 || dr + dc === 0) throw new Error(`${name} contains a non-adjacent move`);
    if (dr && dc && (obstacles.has(`${r0},${c1}`) || obstacles.has(`${r1},${c0}`))) {
      throw new Error(`${name} cuts an impassable crater corner`);
    }
  }
}
console.log("offline preview routes avoid obstacles and use legal adjacent moves");
