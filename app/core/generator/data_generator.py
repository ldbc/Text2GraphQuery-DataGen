import copy
from datetime import datetime
import json
from pathlib import Path
import re
import subprocess
import time
from typing import List, Tuple

from app.core.llm.llm_client import LlmClient
from app.core.prompt import data


class DataGenerator:
    """High-quality data generator based on Schema"""

    def __init__(self, llm_client: LlmClient):
        self.llm_client = llm_client

    def _extract_python_code(self, response: str) -> str:
        """Robustly extract Python code from LLM response using regex."""
        # Match ```python ... ``` or ``` ... ``` blocks
        code_block_match = re.search(r"```(?:python)?\s*\n(.*?)\n```", response, re.DOTALL)
        if code_block_match:
            return code_block_match.group(1).strip()
        # If no code block found, return entire response as fallback (assuming it's all code)
        return response.strip()

    def generate_data_script(self, schema_sql) -> str:
        """Call LLM to generate data generation Python script."""

        data.INSTRUCTION_TEMPLATE = data.INSTRUCTION_TEMPLATE.format(schema_sql=schema_sql)
        message = [
            {"role": "system", "content": data.PROMPT},
            {"role": "user", "content": data.INSTRUCTION_TEMPLATE},
        ]

        response = self.llm_client.call_with_messages(message)

        # Robust code extraction
        code = self._extract_python_code(response)

        if not code:
            raise ValueError("LLM did not return any code.")

        # Optional core checks: e.g., check for if __name__ == "__main__":
        if 'if __name__ == "__main__":' not in code:
            print("Warning: Generated code is missing the main execution block.")

        return code

    def _sanitize_code(self, code: str) -> str:
        """
        Apply fixes for known high-frequency errors in generated code.
        This is a more reliable safety measure than relying solely on prompts.
        """
        # 1. Fix Faker import issues
        if "from faker import Faker" not in code:
            if "import faker" in code:
                code = code.replace("import faker", "from faker import Faker", 1)
            else:
                code = "from faker import Faker\n" + code

        # 2. Ensure Faker instance is created
        if not re.search(r"fake\s*=\s*Faker\(.*\)", code):
            last_import_pos = -1
            for match in re.finditer(r"^import .*", code, re.MULTILINE):
                last_import_pos = match.end()
            for match in re.finditer(r"^from .*", code, re.MULTILINE):
                last_import_pos = max(last_import_pos, match.end())

            if last_import_pos != -1:
                code = (
                    code[:last_import_pos]
                    + "\n\n# Initialize Faker\nfake = Faker('en_US')\n"
                    + code[last_import_pos:]
                )
            else:
                code = "# Initialize Faker\nfake = Faker('en_US')\n" + code

        return code

    def generate_data(
        self, schema_file, output_base: str = "examples/generated_data", max_retries: int = 2
    ) -> Tuple[str, List[Path]]:
        """Generate, save, and execute data generation script with automatic retry/fix logic."""
        with open(schema_file, encoding="utf-8") as f:
            schema_sql = f.read()
            print(f"Schema SQL: {schema_sql}")
            # schema_json = json.dumps(json.load(f), ensure_ascii=False)

        output_base = Path(output_base)

        # Script will create ./csv_files/ subdir, but ensure root exists
        script_dir = output_base / "scripts"
        script_dir.mkdir(parents=True, exist_ok=True)

        last_error = ""  # Error Traceback info
        original_code = ""

        for attempt in range(max_retries + 1):
            if attempt > 0:
                print(
                    f"--- Attempt {attempt + 1}/{max_retries + 1}: "
                    "Asking LLM to fix the previous error ---"
                )
                FIX_INSTRUCTION = data.FIX_INSTRUCTION.format(
                    last_error=last_error, original_code=original_code
                )
                FIX_SYSTEM_PROMPT = data.FIX_SYSTEM_PROMPT
                message = [
                    {"role": "system", "content": FIX_SYSTEM_PROMPT},
                    {"role": "user", "content": FIX_INSTRUCTION},
                ]
                response = self.llm_client.call_with_messages(message)
                code = self._extract_python_code(response)
            else:
                print("--- Attempt 1: Generating initial script ---")
                code = self.generate_data_script(schema_sql)

            if not code:
                last_error = "LLM returned empty code."
                continue

            original_code = code

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            script_name = f"data_generator_{timestamp}_attempt{attempt + 1}.py"
            script_path = script_dir / script_name

            with open(script_path, "w", encoding="utf-8") as f:
                f.write(code)

            try:
                result = subprocess.run(
                    ["python", str(script_path.name)],
                    cwd=str(script_dir),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    timeout=600,
                )

                if result.returncode == 0:
                    print(f"--- Script executed successfully on attempt {attempt + 1}! ---")
                    csv_files = list((script_dir / "csv_files").glob("*.csv"))
                    if not csv_files:
                        raise FileNotFoundError(
                            "Script ran but produced no CSV files. Output:"
                            f"\n{result.stdout}\n{result.stderr}"
                        )
                    return str(script_path), csv_files
                else:
                    last_error = f"STDOUT:\n{result.stdout}\n\nSTDERR:\n{result.stderr}"
                    print(f"Script failed on attempt {attempt + 1}. Error:\n{last_error}")
                    # Remove failed Python code file after each attempt,
                    # only reserve the successful one
                    try:
                        if script_path.exists():
                            script_path.unlink()
                    except Exception as del_err:
                        print(f"Failed to delete failed script {script_path}: {del_err}")

            except subprocess.TimeoutExpired as e:
                last_error = f"Script execution timed out: {e}"
                print(last_error)
            except Exception as e:
                last_error = f"An unexpected error occurred: {e}"
                print(last_error)

            time.sleep(2)  # Avoid excessive API calls

        raise RuntimeError(
            f"Failed to generate a working script after {max_retries + 1} attempts. "
            f"Last error:\n{last_error}"
        )

    def clean_json_schema(self, input_data):
        """Clean JSON schema: set 'optional' to True \
           and 'unique' to False for non-_id properties."""
        if isinstance(input_data, str):
            try:
                data = json.loads(input_data)
            except json.JSONDecodeError:
                # Failed to parse, return original input
                return input_data
        else:
            data = copy.deepcopy(input_data)

        if not isinstance(data, list):
            if isinstance(data, dict) and "schema" in data:
                data = data["schema"]
            else:
                # Cannot process, return original data
                return data

        for item in data:
            # Only process VERTEX type
            if isinstance(item, dict) and item.get("type") == "VERTEX":
                properties = item.get("properties", [])
                # Iterate all properties
                for prop in properties:
                    if not isinstance(prop, dict):
                        continue
                    prop_name = prop.get("name", "")
                    if prop_name and not prop_name.endswith("_id"):
                        # set 'optional' to True and 'unique' to False for non-_id properties
                        prop["optional"] = True
                        prop["unique"] = False

        return json.dumps(data, indent=2)

    def generate_import_config(self, schema_file, csv_file_info: str, output_path):
        with open(schema_file, encoding="utf-8") as f:
            schema_json = json.dumps(json.load(f), ensure_ascii=False)

        IMPORT_SYSTEM_PROMPT = data.IMPORT_SYSTEM_PROMPT
        IMPORT_INSTRUCTION = data.IMPORT_INSTRUCTION.format(
            schema_json=self.clean_json_schema(schema_json), csv_files_info=csv_file_info
        )

        message = [
            {"role": "system", "content": IMPORT_SYSTEM_PROMPT},
            {"role": "user", "content": IMPORT_INSTRUCTION},
        ]

        response = self.llm_client.call_with_messages(message)
        # Parse response as JSON
        try:
            start_idx = response.find("{")
            end_idx = response.rfind("}") + 1
            json_str = response[start_idx:end_idx]
            import_config = json.loads(json_str)
        except Exception as err:
            raise ValueError("LLM did not return valid JSON for import config.") from err

        # Parse cleaned schema
        try:
            cleaned_schema = json.loads(self.clean_json_schema(schema_json))
        except Exception as err:
            raise ValueError("Failed to parse cleaned schema JSON.") from err

        # Synthesize: replace schema array in import_config with cleaned_schema
        import_config["schema"] = cleaned_schema

        # Return synthesized config as JSON string
        # Write import_config JSON to /example/generated_data/scripts/csv_files/import_config.json
        output_path = Path(output_path) / "import_config.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(import_config, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"Failed to write import config: {e}")
            return False
