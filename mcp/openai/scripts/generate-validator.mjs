import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import Ajv from "ajv";
import standaloneCode from "ajv/dist/standalone/index.js";

const schemaPath = fileURLToPath(
  new URL("../../../skills/simplify/schema/care_plan.schema.json", import.meta.url),
);
const outputPath = fileURLToPath(new URL("../ui/generated/validate-report.js", import.meta.url));
const schema = JSON.parse(readFileSync(schemaPath, "utf8"));
const ajv = new Ajv({ allErrors: true, code: { source: true, esm: true }, strict: true });
const validate = ajv.compile(schema);
mkdirSync(fileURLToPath(new URL("../ui/generated/", import.meta.url)), { recursive: true });
writeFileSync(outputPath, `${standaloneCode(ajv, validate)}\n`, "utf8");
