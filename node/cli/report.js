import fs from "node:fs";
import path from "node:path";

function fmt(value) {
  return value === null || value === undefined ? "-" : String(value);
}

function printProduct(product) {
  console.log(`\nProduct: ${product.product_id} (${product.url})`);
  console.log(`  Overall Score : ${fmt(product.overall_score)}${product.blocked ? " [BLOCKED]" : ""}`);
  console.log(`  Confidence    : ${fmt(product.confidence)}`);
  console.log("  Category Scores:");
  for (const [name, score] of Object.entries(product.category_scores)) {
    console.log(`    - ${name}: ${score}`);
  }

  console.log("  Issues:");
  for (const severity of ["high", "medium", "low"]) {
    const entries = product.issues[severity] || [];
    console.log(`    - ${severity.toUpperCase()}: ${entries.length}`);
    for (const issue of entries.slice(0, 3)) {
      console.log(`      * ${issue.rule_id} | p=${issue.priority_score} | ${issue.message}`);
    }
  }

  if (product.regression?.has_previous) {
    console.log("  Regression:");
    console.log(`    - previous: ${fmt(product.regression.previous_overall_score)}`);
    console.log(`    - delta   : ${fmt(product.regression.overall_delta)}`);
  }

  if ((product.recommendations || []).length > 0) {
    console.log("  Recommendations:");
    for (const rec of product.recommendations.slice(0, 5)) {
      console.log(`    - [${rec.rule_id}] ${rec.action} (${rec.estimated_lift})`);
    }
  }
}

function main() {
  const target = process.argv[2];
  if (!target) {
    console.error("Usage: node cli/report.js <report.json>");
    process.exit(1);
  }

  const absolute = path.resolve(process.cwd(), target);
  const report = JSON.parse(fs.readFileSync(absolute, "utf-8"));

  console.log("Agentic Readiness Assessment Report");
  console.log("=".repeat(36));
  console.log(`Ruleset        : ${report.scoring_meta.ruleset_version}`);
  console.log(`Rubric source  : ${report.scoring_meta.rubric_source}`);
  console.log(`Generated (UTC): ${report.scoring_meta.generated_at_utc}`);

  const s = report.summary;
  console.log("\nSummary:");
  console.log(`  Products      : ${s.product_count}`);
  console.log(`  Scored        : ${s.scored_count}`);
  console.log(`  Blocked       : ${s.blocked_count}`);
  console.log(`  Average Score : ${fmt(s.average_score)}`);

  for (const product of report.products) {
    printProduct(product);
  }
}

main();
