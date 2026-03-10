import json
import logging
import os
import re
import subprocess
import shutil
import tempfile
from pathlib import Path
from typing import Dict, Any

# ================= [Global Configuration] =================
DEFAULT_ROOT_DIR = r"D:\Desktop\重新导入几个可能需要mapping的domain_01031831\重新导入几个可能需要mapping the domain_01031831\Social_Network_Twitter\Cypher\TuGraph-DB_Instance"
INPUT_FILENAME = "import_config.json"

TARGET_SUBDIR_NAME = "GQL2"
TARGET_INSTANCE_NAME = "Spanner_Instance"
IMPORT_CONFIG_OUTPUT = "spanner_import_config.json"

INSTANCE_ID = "test-instance"
PROJECT_ID = "test-project"
EMULATOR_HOST = "localhost:9020"

ENABLE_DEPLOY = False  # Set to True to enable deployment to Spanner Emulator
ENABLE_COPY_CSVS = True
ENABLE_DDL_GEN = True
ENABLE_IMPORT_GEN = True
# ==========================================================

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("MigrationToolV8_Fixed")


class NameSanitizer:
    """
    Handles naming conventions:
    - SRC_ID / DST_ID must remain uppercase to match DDL column names.
    - vid is preserved as 'vid' (not mapped to 'vid_val').
    """
    @staticmethod
    def clean(name: str) -> str:
        if name is None:
            return ""

        raw = str(name).strip()

        # Preserve edge table ID columns (unified to uppercase)
        up = raw.upper()
        if up in ("SRC_ID", "DST_ID"):
            return up

        low = raw.lower()

        # Preserve original vid name
        if low == "vid":
            return "vid"

        # Mapping for Spanner Graph reserved words
        mapping = {
            "timestamp": "ts",
            "date": "dt",
            "limit": "limit_val",
            "key": "key_val",
            "order": "order_val",
            "group": "group_val",
            "source": "source_val",
            "target": "target_val",
            "user": "user_val",
            "vid": "vid_val",  # Won't trigger due to the early return above
        }
        return mapping.get(low, low)


class TypeMapper:
    @staticmethod
    def get_spanner_type(original_type: str, for_ddl: bool = False) -> str:
        original_type = (original_type or "STRING").upper()
        mapping = {
            "INT8": "INT64",
            "INT16": "INT64",
            "INT32": "INT64",
            "INT64": "INT64",
            "LONG": "INT64",
            "FLOAT": "FLOAT64",
            "DOUBLE": "FLOAT64",
            "BOOL": "BOOL",
            "BOOLEAN": "BOOL",
            "STRING": "STRING",
            "TEXT": "STRING",
            "DATE": "STRING",
            "DATETIME": "STRING",
            "TIMESTAMP": "STRING",
        }
        base_type = mapping.get(original_type, "STRING")
        if for_ddl and base_type == "STRING":
            return "STRING(MAX)"
        return base_type


class ImportConfigGenerator:
    """
    Generates spanner_import_config.json.
    - Forces SRC_ID/DST_ID to STRING in edge tables.
    - Ensures SRC_ID/DST_ID are uppercase.
    """
    def generate(self, config_data: Dict[str, Any]) -> str:
        schema_map = {}
        if "schema" in config_data:
            for item in config_data["schema"]:
                props = {p["name"]: p["type"] for p in item.get("properties", [])}
                schema_map[item["label"]] = props

        node_files, edge_files = [], []
        if "files" in config_data:
            for file_item in config_data["files"]:
                original_label = file_item["label"]
                is_edge = "SRC_ID" in file_item 

                # Determine Table Name
                if is_edge:
                    target_table_name = f"{file_item['SRC_ID']}{original_label}{file_item['DST_ID']}"
                else:
                    target_table_name = NameSanitizer.clean(original_label)

                new_file_item = {
                    "path": file_item["path"],
                    "label": target_table_name,
                    "format": "CSV",
                    "header": file_item.get("header", 0),
                    "columns": {}
                }

                label_props = schema_map.get(original_label, {})

                if "columns" in file_item:
                    for col_name in file_item["columns"]:
                        clean_col = NameSanitizer.clean(col_name)

                        # vid column
                        if clean_col == "vid":
                            new_file_item["columns"]["vid"] = "STRING"
                            continue

                        # edge ID columns
                        if clean_col in ("SRC_ID", "DST_ID"):
                            new_file_item["columns"][clean_col] = "STRING"
                            continue

                        # normal properties
                        original_type = label_props.get(col_name, "STRING")
                        new_file_item["columns"][clean_col] = TypeMapper.get_spanner_type(original_type)

                # Ensure edge table has vid column
                if is_edge and "vid" not in new_file_item["columns"]:
                    new_file_item["columns"]["vid"] = "STRING"

                if is_edge:
                    edge_files.append(new_file_item)
                else:
                    node_files.append(new_file_item)

        return json.dumps({"files": node_files + edge_files}, indent=2, ensure_ascii=False)


class DDLGenerator:
    """
    Generates DDL for Table Creation and Property Graph definition.
    - Unifies vid as STRING(MAX).
    - Edge PK: (vid, SRC_ID, DST_ID).
    - Foreign Keys reference Vertex PKs.
    """
    def __init__(self):
        self.ignored_fields = {"SRC_ID", "DST_ID"}

    def _escape(self, name: str) -> str:
        return f"`{name}`"

    def _get_pk(self, schema_item: Dict) -> str:
        return NameSanitizer.clean(schema_item.get("primary", "id"))

    def _infer_constraints(self, json_config: Dict) -> Dict:
        inferred = {}
        if "files" in json_config:
            for f in json_config["files"]:
                if "SRC_ID" in f:
                    label = f.get("label")
                    pair = [f.get("SRC_ID"), f.get("DST_ID")]
                    if label not in inferred:
                        inferred[label] = []
                    if pair not in inferred[label]:
                        inferred[label].append(pair)
        return inferred

    def generate_stages(self, json_config: Dict, graph_name: str) -> Dict[str, str]:
        schema_list = json_config.get("schema", [])
        node_ddls, edge_ddls = [], []
        node_meta_map = {}
        edge_graph_meta = {}
        inferred_constraints = self._infer_constraints(json_config)
        seen_nodes = set()

        # -------- Nodes --------
        for item in schema_list:
            if item.get("type") == "VERTEX":
                label = item["label"]
                clean_label = NameSanitizer.clean(label)
                if clean_label in seen_nodes:
                    continue
                seen_nodes.add(clean_label)

                pk = self._get_pk(item)
                columns = []
                pk_type = "STRING(MAX)"

                for prop in item.get("properties", []):
                    p_name = NameSanitizer.clean(prop["name"])

                    # Enforce unified vid type
                    if p_name == "vid":
                        p_type = "STRING(MAX)"
                    else:
                        p_type = TypeMapper.get_spanner_type(prop.get("type", "STRING"), True)

                    nullable = " NOT NULL" if p_name == pk else ""
                    if p_name == pk:
                        pk_type = p_type
                    columns.append(f"   {self._escape(p_name):<20} {p_type}{nullable}")

                node_meta_map[label] = {"pk": pk, "type": pk_type, "clean_label": clean_label}
                node_ddls.append(
                    f"CREATE TABLE {self._escape(clean_label)} (\n" +
                    ",\n".join(columns) +
                    f"\n) PRIMARY KEY ({self._escape(pk)});"
                )

        # -------- Edges --------
        for item in schema_list:
            if item.get("type") == "EDGE":
                label = item["label"]
                constraints = item.get("constraints", [])
                if not constraints:
                    constraints = inferred_constraints.get(label, [])

                for src, dst in constraints:
                    src_info = node_meta_map.get(
                        src,
                        {"pk": "id", "type": "STRING(MAX)", "clean_label": NameSanitizer.clean(src)}
                    )
                    dst_info = node_meta_map.get(
                        dst,
                        {"pk": "id", "type": "STRING(MAX)", "clean_label": NameSanitizer.clean(dst)}
                    )

                    table_name = f"{src}{label}{dst}"

                    columns = [
                        f"   `vid`               STRING(MAX) NOT NULL",
                        f"   `SRC_ID`            {src_info['type']} NOT NULL",
                        f"   `DST_ID`            {dst_info['type']} NOT NULL",
                    ]

                    pk_cols = ["`vid`", "`SRC_ID`", "`DST_ID`"]

                    for prop in item.get("properties", []):
                        p_name = NameSanitizer.clean(prop["name"])

                        # vid already injected above
                        if p_name == "vid":
                            continue

                        p_type = TypeMapper.get_spanner_type(prop.get("type", "STRING"), True)
                        columns.append(f"   {self._escape(p_name):<20} {p_type}")

                    columns.append(
                        f"   FOREIGN KEY (`SRC_ID`) REFERENCES {self._escape(src_info['clean_label'])} ({self._escape(src_info['pk'])})"
                    )
                    columns.append(
                        f"   FOREIGN KEY (`DST_ID`) REFERENCES {self._escape(dst_info['clean_label'])} ({self._escape(dst_info['pk'])})"
                    )

                    edge_ddls.append(
                        f"CREATE TABLE {self._escape(table_name)} (\n" +
                        ",\n".join(columns) +
                        f"\n) PRIMARY KEY ({', '.join(pk_cols)});"
                    )

                    edge_graph_meta.setdefault(label, []).append({
                        "table": table_name,
                        "src": src_info,
                        "dst": dst_info,
                        "pk_cols": pk_cols
                    })

        # -------- Property Graph --------
        node_tables = sorted(list(set([self._escape(i["clean_label"]) for i in node_meta_map.values()])))
        if not node_tables:
            return {}

        graph_ddl = (
            f"CREATE OR REPLACE PROPERTY GRAPH {self._escape(graph_name)}\n"
            f"  NODE TABLES ({', '.join(node_tables)})\n"
        )

        edge_defs = []
        for e_label, tabs in edge_graph_meta.items():
            for t in tabs:
                edge_defs.append(
                    f"     {self._escape(t['table'])}\n"
                    f"       KEY ({', '.join(t['pk_cols'])})\n"
                    f"       SOURCE KEY (`SRC_ID`) REFERENCES {self._escape(t['src']['clean_label'])} ({self._escape(t['src']['pk'])})\n"
                    f"       DESTINATION KEY (`DST_ID`) REFERENCES {self._escape(t['dst']['clean_label'])} ({self._escape(t['dst']['pk'])})\n"
                    f"       LABEL {self._escape(e_label)}"
                )

        if edge_defs:
            graph_ddl += "  EDGE TABLES (\n" + ",\n".join(edge_defs) + "\n  );"

        return {
            "01_nodes": "\n\n".join(node_ddls),
            "02_edges": "\n\n".join(edge_ddls),
            "03_graph": graph_ddl
        }


class ToolProcessor:
    def __init__(self):
        self.import_gen = ImportConfigGenerator()
        self.ddl_gen = DDLGenerator()

    def run_command(self, cmd: list, ignore_error=False):
        if not ENABLE_DEPLOY:
            return
        if "gcloud" in cmd and "--quiet" not in cmd:
            cmd.append("--quiet")
        try:
            logger.info(f"Executing: {' '.join(cmd)}")
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            if not ignore_error:
                logger.error(f"Command failed: {e.stderr}")
            raise e

    def sanitize_db_name(self, name: str) -> str:
        clean = re.sub(r"[^a-zA-Z0-9]", "_", name).lower()
        if not clean[0].isalpha():
            clean = "db_" + clean
        return clean[:30]

    def _find_csv(self, domain_root: Path, filename: str) -> Path:
        direct_path = domain_root / filename
        if direct_path.exists():
            return direct_path

        ignore_dirs = {TARGET_SUBDIR_NAME, "GQL", "GQL2", "Spanner_Instance", "output", "__pycache__"}
        for root, dirs, files in os.walk(domain_root):
            dirs[:] = [d for d in dirs if d not in ignore_dirs]
            if filename in files:
                return Path(root) / filename

        return None

    def process_directory(self, json_path: Path):
        domain_root = json_path.parent
        folder_name = domain_root.name.replace("_tugraph", "")
        db_id = self.sanitize_db_name(folder_name)

        root_base = domain_root.parent
        target_dir = root_base / TARGET_SUBDIR_NAME / folder_name / TARGET_INSTANCE_NAME

        logger.info(f"Processing: {domain_root.name}")
        logger.info(f"  -> Graph Name: {db_id}")
        logger.info(f"  -> Target Dir: {target_dir}")

        target_dir.mkdir(parents=True, exist_ok=True)

        try:
            with open(json_path, "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception as e:
            logger.error(f"JSON Error: {e}")
            return

        # 1) Copy CSV files
        if ENABLE_COPY_CSVS and "files" in config:
            for f in config["files"]:
                src = self._find_csv(domain_root, f.get("path"))
                dst = target_dir / f.get("path")
                if src and src.exists():
                    try:
                        if src.resolve() != dst.resolve():
                            shutil.copy2(src, dst)
                    except shutil.SameFileError:
                        pass
                else:
                    logger.warning(f"CSV NOT FOUND: {f.get('path')}")

        # 2) Generate Import Config
        if ENABLE_IMPORT_GEN:
            with open(target_dir / IMPORT_CONFIG_OUTPUT, "w", encoding="utf-8") as f:
                f.write(self.import_gen.generate(config))

        # 3) Generate DDL
        stages = {}
        if ENABLE_DDL_GEN:
            stages = self.ddl_gen.generate_stages(config, db_id)
            with open(target_dir / f"Spanner_SchemaDDL_{db_id}.sql", "w", encoding="utf-8") as f:
                f.write(f"{stages.get('01_nodes','')}\n\n{stages.get('02_edges','')}\n\n{stages.get('03_graph','')}")

        # 4) Deploy to Emulator
        if ENABLE_DEPLOY and ENABLE_DDL_GEN:
            self.deploy(db_id, stages)

    def deploy(self, db_id, stages):
        logger.info(f"Deploying {db_id}...")
        try:
            self.run_command(["gcloud", "config", "set", "api_endpoint_overrides/spanner", f"http://{EMULATOR_HOST}"], True)
            self.run_command(["gcloud", "config", "set", "auth/disable_credentials", "true"], True)
            self.run_command(["gcloud", "config", "set", "project", PROJECT_ID], True)

            self.run_command(["gcloud", "spanner", "instances", "create", INSTANCE_ID,
                              "--config=emulator-config", "--description=Test", "--nodes=1"], True)

            self.run_command(["gcloud", "spanner", "databases", "delete", db_id, "--instance", INSTANCE_ID], True)
            self.run_command(["gcloud", "spanner", "databases", "create", db_id, "--instance", INSTANCE_ID], True)

            self._apply_ddl(db_id, stages.get("01_nodes", "") + "\n\n" + stages.get("02_edges", ""))
            self._apply_ddl(db_id, stages.get("03_graph", ""))
            logger.info(f"Successfully Deployed {db_id}!")
        except Exception as e:
            logger.error(f"Deployment failed: {e}")

    def _apply_ddl(self, db_id, ddl):
        if not ddl.strip():
            return
        with tempfile.NamedTemporaryFile(mode="w+", suffix=".sql", delete=False, encoding="utf-8") as tmp:
            tmp.write(ddl)
            tmp_path = tmp.name
        try:
            self.run_command(["gcloud", "spanner", "databases", "ddl", "update",
                              db_id, "--instance", INSTANCE_ID, f"--ddl-file={tmp_path}"])
        finally:
            os.remove(tmp_path)


if __name__ == "__main__":
    p = ToolProcessor()
    print("Migration Tool V8 - With VID Support (Fixed SRC_ID/DST_ID)")
    for f in sorted(list(Path(DEFAULT_ROOT_DIR).rglob(INPUT_FILENAME))):
        if TARGET_SUBDIR_NAME in f.parts:
            continue
        p.process_directory(f)