import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402

import validate  # noqa: E402  (path set up by _paths)


class TestValidateFunction(unittest.TestCase):
    def test_type_string(self):
        errors = validate.validate("hello", {"type": "string"})
        self.assertEqual(errors, [])

    def test_type_mismatch(self):
        errors = validate.validate(5, {"type": "string"})
        self.assertEqual(len(errors), 1)
        self.assertIn("expected type", errors[0])

    def test_type_list(self):
        schema = {"type": ["string", "null"]}
        self.assertEqual(validate.validate("x", schema), [])
        self.assertEqual(validate.validate(None, schema), [])
        self.assertEqual(len(validate.validate(5, schema)), 1)

    def test_integer_excludes_bool(self):
        # bool is a subclass of int in Python; schema type "integer" must
        # not accept True/False.
        errors = validate.validate(True, {"type": "integer"})
        self.assertEqual(len(errors), 1)

    def test_properties_and_required(self):
        schema = {
            "type": "object",
            "required": ["a"],
            "properties": {"a": {"type": "string"}, "b": {"type": "integer"}},
        }
        self.assertEqual(validate.validate({"a": "x"}, schema), [])
        errors = validate.validate({"b": 1}, schema)
        self.assertEqual(len(errors), 1)
        self.assertIn("missing required property 'a'", errors[0])

    def test_additional_properties_false(self):
        schema = {
            "type": "object",
            "properties": {"a": {"type": "string"}},
            "additionalProperties": False,
        }
        self.assertEqual(validate.validate({"a": "x"}, schema), [])
        errors = validate.validate({"a": "x", "z": 1}, schema)
        self.assertEqual(len(errors), 1)
        self.assertIn("additional property 'z' is not allowed", errors[0])

    def test_additional_properties_schema(self):
        schema = {
            "type": "object",
            "additionalProperties": {"type": "integer"},
        }
        self.assertEqual(validate.validate({"x": 1, "y": 2}, schema), [])
        errors = validate.validate({"x": "nope"}, schema)
        self.assertEqual(len(errors), 1)

    def test_items(self):
        schema = {"type": "array", "items": {"type": "integer", "minimum": 1}}
        self.assertEqual(validate.validate([1, 2, 3], schema), [])
        errors = validate.validate([1, 0, 3], schema)
        self.assertEqual(len(errors), 1)
        self.assertIn("[1]", errors[0])

    def test_enum(self):
        schema = {"type": "string", "enum": ["a", "b"]}
        self.assertEqual(validate.validate("a", schema), [])
        errors = validate.validate("c", schema)
        self.assertEqual(len(errors), 1)
        self.assertIn("expected one of", errors[0])

    def test_minimum_maximum(self):
        schema = {"type": "integer", "minimum": 1, "maximum": 3}
        self.assertEqual(validate.validate(2, schema), [])
        self.assertEqual(len(validate.validate(0, schema)), 1)
        self.assertEqual(len(validate.validate(4, schema)), 1)

    def test_min_length(self):
        schema = {"type": "string", "minLength": 3}
        self.assertEqual(validate.validate("abc", schema), [])
        self.assertEqual(len(validate.validate("ab", schema)), 1)

    def test_min_items_max_items(self):
        schema = {"type": "array", "minItems": 1, "maxItems": 2, "items": {"type": "string"}}
        self.assertEqual(validate.validate(["a"], schema), [])
        self.assertEqual(len(validate.validate([], schema)), 1)
        self.assertEqual(len(validate.validate(["a", "b", "c"], schema)), 1)

    def test_ref_and_definitions(self):
        schema = {
            "type": "object",
            "definitions": {"pos_int": {"type": "integer", "minimum": 1}},
            "properties": {"n": {"$ref": "#/definitions/pos_int"}},
        }
        self.assertEqual(validate.validate({"n": 5}, schema), [])
        errors = validate.validate({"n": 0}, schema)
        self.assertEqual(len(errors), 1)
        self.assertTrue(errors[0].startswith("n:"))

    def test_any_of(self):
        schema = {"anyOf": [{"type": "string"}, {"type": "null"}]}
        self.assertEqual(validate.validate("x", schema), [])
        self.assertEqual(validate.validate(None, schema), [])
        errors = validate.validate(5, schema)
        self.assertEqual(len(errors), 1)
        self.assertIn("anyOf", errors[0])

    def test_nested_path_reporting(self):
        schema = {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["status"],
                        "properties": {"status": {"type": "string", "enum": ["to_do", "done"]}},
                    },
                }
            },
        }
        instance = {"items": [{"status": "pending"}]}
        errors = validate.validate(instance, schema)
        self.assertEqual(len(errors), 1)
        self.assertIn("items[0].status", errors[0])


class TestLoadSchema(unittest.TestCase):
    def test_load_schema_bare_name(self):
        schema = validate.load_schema("care_plan")
        self.assertEqual(schema.get("title"), "care_plan")

    def test_load_schema_path(self):
        path = os.path.join(_paths.SCHEMA_DIR, "run.schema.json")
        schema = validate.load_schema(path)
        self.assertEqual(schema.get("title"), "run")


class TestValidateCLI(unittest.TestCase):
    def _run(self, args):
        return subprocess.run(
            [sys.executable, os.path.join(_paths.SCRIPTS_DIR, "validate.py")] + args,
            capture_output=True,
            text=True,
        )

    def test_cli_valid_ok(self):
        with tempfile.TemporaryDirectory() as d:
            instance_path = os.path.join(d, "instance.json")
            with open(instance_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "schema_version": "1.0",
                        "plugin_version": "0.1.0",
                        "run_id": "r1",
                        "coverage": [],
                        "missing": [],
                    },
                    f,
                )
            result = self._run(["--schema", "coverage", "--file", instance_path])
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout.strip(), "OK")

    def test_cli_invalid_exit_1(self):
        with tempfile.TemporaryDirectory() as d:
            instance_path = os.path.join(d, "instance.json")
            with open(instance_path, "w", encoding="utf-8") as f:
                json.dump({"schema_version": "1.0"}, f)
            result = self._run(["--schema", "coverage", "--file", instance_path])
            self.assertEqual(result.returncode, 1)
            self.assertNotIn("Traceback", result.stdout)
            self.assertNotIn("Traceback", result.stderr)

    def test_cli_invalid_json_exit_1(self):
        with tempfile.TemporaryDirectory() as d:
            instance_path = os.path.join(d, "instance.json")
            with open(instance_path, "w", encoding="utf-8") as f:
                f.write("{not valid json")
            result = self._run(["--schema", "coverage", "--file", instance_path])
            self.assertEqual(result.returncode, 1)
            self.assertNotIn("Traceback", result.stdout)
            self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
