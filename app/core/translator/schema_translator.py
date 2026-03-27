import json
import logging
import os
import shutil
from typing import Dict, Any, List

# ================= [配置区域] =================
DEFAULT_ROOT_DIR = r"examples\generated_schemas"
OUTPUT_DIR = r"examples\Spanner_Instance"
# ============================================

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("CleanerToolV2")

class NameSanitizer:
    @staticmethod
    def clean(name: str) -> str:
        return name.strip()

class TypeMapper:
    @staticmethod
    def get_spanner_type(original_type: str, for_ddl: bool = False) -> str:
        original_type = original_type.upper()
        mapping = {
            "INT8": "INT64", "INT16": "INT64", "INT32": "INT64", "INT64": "INT64", "LONG": "INT64",
            "FLOAT": "FLOAT64", "DOUBLE": "FLOAT64", 
            "BOOL": "BOOL", "BOOLEAN": "BOOL",
            "STRING": "STRING", "TEXT": "STRING", 
            "DATE": "DATE", 
            "DATETIME": "STRING", "TIMESTAMP": "STRING"
        }
        
        base_type = mapping.get(original_type, "STRING")
        
        if for_ddl and base_type == "STRING": 
            return "STRING(MAX)"
        return base_type

class ImportConfigGenerator:
    def generate(self, config_data: Dict[str, Any]) -> str:
        schema_map = {}
        if "schema" in config_data:
            for item in config_data["schema"]:
                props = {p["name"]: p["type"] for p in item["properties"]}
                schema_map[item["label"]] = props

        node_files, edge_files = [], []
        if "files" in config_data:
            for file_item in config_data["files"]:
                original_label = file_item["label"]
                is_edge = "SRC_ID" in file_item

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
                        original_type = label_props.get(col_name, "STRING")
                        if col_name in ["SRC_ID", "DST_ID"]: 
                            original_type = "STRING"
                        
                        new_file_item["columns"][clean_col] = TypeMapper.get_spanner_type(original_type)

                if is_edge: 
                    edge_files.append(new_file_item)
                else: 
                    node_files.append(new_file_item)

        return json.dumps({"files": node_files + edge_files}, indent=2, ensure_ascii=False)

class DDLGenerator:
    def __init__(self):
        self.ignored_fields = {"SRC_ID", "DST_ID"}

    def _escape(self, name: str) -> str: 
        return f"`{name}`"
        
    def _get_pk(self, schema_item: Dict) -> str: 
        return NameSanitizer.clean(schema_item.get("primary", "id"))

    def _infer_constraints(self, json_config: Dict) -> Dict:
        inferred = {}
        if isinstance(json_config, dict) and "files" in json_config:
            for f in json_config["files"]:
                if "SRC_ID" in f:
                    label = f.get("label")
                    pair = [f.get("SRC_ID"), f.get("DST_ID")]
                    if label not in inferred: inferred[label] = []
                    if pair not in inferred[label]: inferred[label].append(pair)
        return inferred

    def generate_stages(self, json_config: Dict, graph_name: str) -> Dict[str, str]:
        # Handle both formats: {"schema": [...]} and [...]
        if isinstance(json_config, list):
            schema_list = json_config
        else:
            schema_list = json_config.get("schema", [])
        node_ddls, edge_ddls = [], []
        node_meta_map = {}
        edge_graph_meta = {}
        inferred_constraints = self._infer_constraints(json_config)
        seen_nodes = set()

        # 1. Process Nodes
        for item in schema_list:
            if item["type"] == "VERTEX":
                label = item["label"]
                clean_label = NameSanitizer.clean(label)
                if clean_label in seen_nodes: continue
                seen_nodes.add(clean_label)

                pk = self._get_pk(item)
                columns = []
                pk_type = "STRING(MAX)"

                for prop in item["properties"]:
                    p_name = NameSanitizer.clean(prop["name"])
                    p_type = TypeMapper.get_spanner_type(prop["type"], True)
                    nullable = " NOT NULL" if p_name == pk else ""
                    if p_name == pk: pk_type = p_type
                    columns.append(f"  {self._escape(p_name):<20} {p_type}{nullable}")

                node_meta_map[label] = {"pk": pk, "type": pk_type, "clean_label": clean_label}
                node_ddls.append(f"CREATE TABLE {self._escape(clean_label)} (\n" + ",\n".join(columns) + f"\n) PRIMARY KEY ({self._escape(pk)});")

        # 2. Process Edges
        for item in schema_list:
            if item["type"] == "EDGE":
                label = item["label"]
                constraints = item.get("constraints", [])
                if not constraints: constraints = inferred_constraints.get(label, [])

                for src, dst in constraints:
                    src_info = node_meta_map.get(src, {"pk": "id", "type": "STRING(MAX)", "clean_label": NameSanitizer.clean(src)})
                    dst_info = node_meta_map.get(dst, {"pk": "id", "type": "STRING(MAX)", "clean_label": NameSanitizer.clean(dst)})

                    table_name = f"{src}{label}{dst}"
                    
                    columns = [
                        f"  `SRC_ID`           {src_info['type']} NOT NULL", 
                        f"  `DST_ID`           {dst_info['type']} NOT NULL"
                    ]
                    
                    pk_columns = ["SRC_ID", "DST_ID"]
                    
                    for prop in item.get("properties", []):
                        p_name = NameSanitizer.clean(prop["name"])
                        p_type = TypeMapper.get_spanner_type(prop["type"], True)
                        columns.append(f"  {self._escape(p_name):<20} {p_type}")

                        base_type = TypeMapper.get_spanner_type(prop["type"], False)
                        if base_type not in ["FLOAT64", "BOOL"]:
                            pk_columns.append(p_name)

                    columns.append(f"  FOREIGN KEY (`SRC_ID`) REFERENCES {self._escape(src_info['clean_label'])} ({self._escape(src_info['pk'])})")
                    columns.append(f"  FOREIGN KEY (`DST_ID`) REFERENCES {self._escape(dst_info['clean_label'])} ({self._escape(dst_info['pk'])})")

                    pk_str = ", ".join([self._escape(c) for c in pk_columns])
                    edge_ddls.append(f"CREATE TABLE {self._escape(table_name)} (\n" + ",\n".join(columns) + f"\n) PRIMARY KEY ({pk_str});")

                    if label not in edge_graph_meta: edge_graph_meta[label] = []
                    edge_graph_meta[label].append({
                        "table": table_name, 
                        "src": src_info, 
                        "dst": dst_info, 
                        "label_raw": label,
                        "pk_columns": pk_columns 
                    })

        # 3. Process Graph
        node_tables = sorted(list(set([self._escape(i['clean_label']) for i in node_meta_map.values()])))
        if not node_tables: return {}

        graph_ddl = f"CREATE OR REPLACE PROPERTY GRAPH {self._escape(graph_name)}\n  NODE TABLES ({', '.join(node_tables)})\n"
        edge_defs = []
        
        for e_label, tabs in edge_graph_meta.items():
            for t in tabs:
                final_label = e_label
                clean_label_check = NameSanitizer.clean(e_label)
                if clean_label_check in seen_nodes:
                    final_label = f"{e_label}_edge"

                pk_keys_str = ", ".join([self._escape(k) for k in t['pk_columns']])
                
                edge_defs.append(
                    f"    {self._escape(t['table'])}\n      KEY ({pk_keys_str})\n"
                    f"      SOURCE KEY (`SRC_ID`) REFERENCES {self._escape(t['src']['clean_label'])} ({self._escape(t['src']['pk'])})\n"
                    f"      DESTINATION KEY (`DST_ID`) REFERENCES {self._escape(t['dst']['clean_label'])} ({self._escape(t['dst']['pk'])})\n"
                    f"      LABEL {self._escape(final_label)}"
                )
                
        if edge_defs: graph_ddl += "  EDGE TABLES (\n" + ",\n".join(edge_defs) + "\n  );"

        return {"01_nodes": "\n\n".join(node_ddls), "02_edges": "\n\n".join(edge_ddls), "03_graph": graph_ddl}

def process_all_domains():
    root_path = os.path.abspath(DEFAULT_ROOT_DIR)
    if not os.path.exists(root_path):
        logger.error(f"Root path does not exist: {root_path}")
        return

    # Check for example_schema.json in the input directory
    example_schema_path = os.path.join(root_path, "example_schema.json")
    if os.path.exists(example_schema_path):
        logger.info("Found example_schema.json, processing it...")
        spanner_instance_dir = OUTPUT_DIR
        
        if not os.path.exists(spanner_instance_dir):
            os.makedirs(spanner_instance_dir)
        
        try:
            with open(example_schema_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            
            # Generate Config
            config_gen = ImportConfigGenerator()
            new_import_config_str = config_gen.generate(config_data)
            target_config_path = os.path.join(spanner_instance_dir, "spanner_import_config.json")
            with open(target_config_path, 'w', encoding='utf-8') as f:
                f.write(new_import_config_str)
            logger.info(f"  -> Generated {target_config_path}")
            
            # Generate DDL
            ddl_gen = DDLGenerator()
            stages = ddl_gen.generate_stages(config_data, "generated_schemas")
            target_ddl_path = os.path.join(spanner_instance_dir, "Spanner_SchemaDDL_generated_schemas.sql")
            final_ddl = f"{stages['01_nodes']}\n\n{stages['02_edges']}\n\n{stages['03_graph']}"
            with open(target_ddl_path, 'w', encoding='utf-8') as f:
                f.write(final_ddl)
            logger.info(f"  -> Generated {target_ddl_path}")
        except Exception as e:
            logger.error(f"Error processing example_schema.json: {str(e)}")
        
        return

    # Original multi-domain processing
    for domain in os.listdir(root_path):
        domain_path = os.path.join(root_path, domain)
        if not os.path.isdir(domain_path) or domain.startswith("."):
            continue

        # Define key paths
        tugraph_instance_dir = os.path.join(domain_path, "Cypher", "TuGraph-DB_Instance")
        source_config_path = os.path.join(tugraph_instance_dir, "import_config.json")
        
        spanner_instance_dir = os.path.join(domain_path, "GQL", "Spanner_Instance")
        target_config_path = os.path.join(spanner_instance_dir, "spanner_import_config.json")
        
        ddl_filename = f"Spanner_SchemaDDL_{domain.lower()}.sql"
        target_ddl_path = os.path.join(spanner_instance_dir, ddl_filename)

        if not os.path.exists(source_config_path):
            logger.warning(f"Skipping {domain}: Source config not found at {source_config_path}")
            continue

        if not os.path.exists(spanner_instance_dir):
            os.makedirs(spanner_instance_dir)

        logger.info(f"Processing Domain: {domain}...")

        try:
            with open(source_config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)

            # Generate Config
            config_gen = ImportConfigGenerator()
            new_import_config_str = config_gen.generate(config_data)
            with open(target_config_path, 'w', encoding='utf-8') as f:
                f.write(new_import_config_str)
            logger.info(f"  -> Regenerated {target_config_path}")

            # Generate DDL
            ddl_gen = DDLGenerator()
            stages = ddl_gen.generate_stages(config_data, domain.lower())
            final_ddl = f"{stages['01_nodes']}\n\n{stages['02_edges']}\n\n{stages['03_graph']}"
            with open(target_ddl_path, 'w', encoding='utf-8') as f:
                f.write(final_ddl)
            logger.info(f"  -> Regenerated {target_ddl_path}")

            # Sync CSV files
            logger.info(f"  -> Syncing raw CSV files...")
            for f_name in os.listdir(tugraph_instance_dir):
                if f_name.lower().endswith(".csv"):
                    src_csv = os.path.join(tugraph_instance_dir, f_name)
                    dst_csv = os.path.join(spanner_instance_dir, f_name)
                    shutil.copy2(src_csv, dst_csv)
            logger.info(f"  -> CSVs synced.")

        except Exception as e:
            logger.error(f"Error processing {domain}: {str(e)}")

if __name__ == "__main__":
    process_all_domains()