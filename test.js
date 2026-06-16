/* Node-test: henter CORE-blokken ut av index.html (én kilde) og verifiserer mot ekte filer.
   Kjør:  node test.js <fil.xlsx>     (krever ingen installasjon utover buntet vendor/xlsx)
   index.html er fortsatt 100% selvstendig i nettleser – denne testen bare gjenbruker logikken. */
"use strict";
const fs = require("fs");
const vm = require("vm");
global.XLSX = require("./vendor/xlsx.full.min.js");

// Hent CORE-blokken mellom markørene i index.html
const html = fs.readFileSync(__dirname + "/index.html", "utf8");
const m = html.match(/\/\* === CORE_START ===[\s\S]*?\/\* === CORE_END === \*\//);
if (!m) { console.error("Fant ikke CORE-blokk i index.html"); process.exit(1); }
const sandbox = { XLSX: global.XLSX, module: { exports: {} }, console };
vm.runInNewContext(m[0], sandbox);
const C = sandbox.module.exports;

const path = process.argv[2];
if (!path) { console.error("Bruk: node test.js <fil.xlsx>"); process.exit(1); }

const wb = XLSX.read(fs.readFileSync(path), { type: "buffer" });
const parsed = C.parseWorkbook(wb);

console.log("=".repeat(70));
console.log("FIL:", path);
console.log("Ark:", parsed.sheetsFound.join(", "));
console.log("Sesong (mars-apr):", parsed.seasonal
  ? `år ${parsed.seasonal.cols.join(",")}, juni→juli snitt ${C.fmtPct(parsed.seasonal.incByYear.snitt)}` : "ikke funnet");

parsed.weekly.forEach(s => {
  console.log(`\n- ${s.region} ${s.year} (ark «${s.sheetName}»): ${s.sites.length} lok, uker ${s.allWeeks.join(",")}, splitt=${[...s.splitWeeks].join(",") || "ingen"}`);
});

const current = parsed.weekly.filter(s => s.year !== 2024);
const hist = parsed.weekly.filter(s => s.year === 2024);
const find24 = r => hist.find(h => h.region === r) || null;

current.forEach(sheet => {
  const comp = C.computeRegion(sheet, find24(sheet.region), parsed.seasonal);
  console.log("\n" + "#".repeat(70));
  console.log(`REGION ${comp.region} ${comp.year}`);
  console.log(`  Analyseuker: faktisk=w${comp.aw.faktisk.join(",w")}  prognose=w${comp.aw.prognose.join(",w")}  (split=w${comp.aw.splitW})`);
  console.log(`  Region faktisk snitt/uke: ${C.fmtT(comp.regFa)}  prognose: ${C.fmtT(comp.regPr)}  endring: ${C.fmtPct(comp.regEndring)} -> ${comp.regStatus}`);
  console.log(`  Juni→juli: prognose ${C.fmtPct(comp.regInc)} (${C.fmtT(comp.regM06)}→${C.fmtT(comp.regM07)})` +
    (comp.has2024 ? `  | 2024 ${C.fmtPct(comp.reg24Inc)}` : "") +
    (comp.seasonalInc != null ? `  | hist.snitt ${C.fmtPct(comp.seasonalInc)}` : ""));
  console.log("  Ukentlige regiontotaler (tonn): " +
    sheet.allWeeks.map(w => `w${w}=${(comp.weekTotals[w] / 1000).toFixed(1)}`).join("  "));

  const counts = { Offensiv: 0, Realistisk: 0, Defensiv: 0, Ukjent: 0 };
  comp.rows.forEach(r => counts[r.status]++);
  console.log(`  Status-fordeling: ${JSON.stringify(counts)}  | slaktes ut: ${comp.rows.filter(r => r.slaughter).length}  | usikre: ${comp.rows.filter(r => r.uncertain).length}  | matchet 2024: ${comp.rows.filter(r => r.has2024).length}`);

  console.log("  Topp 5 avvik:");
  comp.rows.filter(r => r.endring !== null && !r.slaughter).sort((a, b) => Math.abs(b.endring) - Math.abs(a.endring)).slice(0, 5)
    .forEach(r => console.log(`    ${r.name.padEnd(22)} ${C.fmtPct(r.endring).padStart(8)}  ${r.status}${r.uncertain ? " [usikkert]" : ""}`));

  const sl = comp.rows.filter(r => r.slaughter);
  if (sl.length) console.log("  Slaktes ut: " + sl.map(r => r.name).join(", "));
});

/* ---- sanity-asserts ---- */
console.log("\n" + "=".repeat(70) + "\nSANITY-SJEKKER:");
let ok = true;
function check(name, cond) { console.log(`  [${cond ? "OK" : "FEIL"}] ${name}`); if (!cond) ok = false; }

const west = current.find(s => s.region === "Vest");
if (west) {
  check("Vest har splittet uke 27", west.splitWeeks.has(27));
  const beit = west.sites.find(s => /Beitveit/.test(s.name));
  check("Beitveit w27 hel = juni+juli (≈37242)", beit && Math.abs(beit.weekly[27] - 37242.365) < 1);
  check("Beitveit faktisk snitt ≈ 84208", beit && Math.abs(((beit.weekly[23] + beit.weekly[24]) / 2) - 84208.116) < 1);
}
const aw = west ? C.pickAnalysisWeeks(west) : null;
check("Faktisk=23,24 og prognose=25,26", aw && aw.faktisk.join() === "23,24" && aw.prognose.join() === "25,26");

// region-total skal matche Grand Total-raden (verifiserer kolonneparsing)
const midt = current.find(s => s.region === "Midt");
if (midt && midt.grandTotalRow) {
  const comp = C.computeRegion(midt, null, null);
  const w23gt = C.toNum(midt.grandTotalRow[midt.weekColMap[23][0]]);
  check("Midt w23 regiontotal == Grand Total-rad", Math.abs(comp.weekTotals[23] - w23gt) < 1);
}

process.exit(ok ? 0 : 1);
