from pathlib import Path
from typing import Dict, List

from app.core.schema.schema_graph import SchemaGraph
from app.core.schema.schema_parser import SchemaParser

VERTEX_TABLE_SUFFIX = "VTX"
EDGE_TABLE_SUFFIX = "EDG"
# TODO: Use this constant when possible
VARCHAR2_TYPE = "VARCHAR2(4000)"

# Type mappings: JSON schema -> Oracle SQL
# TODO: define all supported types and specify allowed formats
TYPE_MAP = {
    "INT64": "NUMBER(19)",
    "INT32": "NUMBER(10)",
    "FLOAT": "FLOAT",
    "STRING": VARCHAR2_TYPE,
    "DATETIME": "TIMESTAMP",
    "BOOL": "BOOLEAN",
}

SQLLDR_TYPE_MAP = {
    "INT64": "INTEGER EXTERNAL",
    "INT32": "INTEGER EXTERNAL",
    "FLOAT": "DECIMAL EXTERNAL",
    "STRING": "CHAR",
    "DATETIME": 'TIMESTAMP "YYYY-MM-DD"',
    "BOOL": "CHAR",
}


class OracleSchemaParser(SchemaParser):
    def __init__(self, db_id, instance_path):
        self.db_id = db_id
        self.instance_path = instance_path

    def get_schema_graph(self):
        # Adding dummy implementation for now
        schema_graph = SchemaGraph(self.db_id)
        return schema_graph

    def _enquote_identifier(self, identifier: str):
        # TODO should we throw error here for invalid identifier
        return '"' + identifier + '"'

    def _build_column_attrs(self, label, prop, pk, pk_map):
        type = TYPE_MAP.get(prop["type"], "VARCHAR2(4000)")
        nullable = " NOT NULL" if not prop.get("optional") else ""
        unique = " UNIQUE" if prop.get("unique") and (not pk or prop.get("name") != pk) else ""
        if not pk_map.get(f"{label}"):
            pk_map[f"{label}"] = [pk, type]
        return type + nullable + unique

    def _add_table_columns(self, label, props, pk, pk_map):
        cols = []
        for prop in props:
            attributes = self._build_column_attrs(label, prop, pk, pk_map)
            col_def = f"{self._enquote_identifier(prop['name'])} {attributes}"
            if pk and prop["name"] == pk:
                col_def += " PRIMARY KEY"
            cols.append(col_def)
        return cols

    def _create_vertex_table(self, label, props, pk, pk_map):
        table_name = self._enquote_identifier(f"{label}_{VERTEX_TABLE_SUFFIX}")
        cols = self._add_table_columns(label, props, pk, pk_map)
        columns = ",\n  ".join(cols) if len(cols) > 0 else ""
        stmt = f"CREATE TABLE {table_name} (\n  {columns}\n);"
        return stmt

    # TODO: Remove pk
    def _create_edge_table(self, label, constraints, props, pk, pk_map):
        lines = []
        src_table, dst_table = constraints
        table_prefix = f"{label}_{src_table}_{dst_table}"
        src_col = self._enquote_identifier(f"src_{src_table}_id")
        dst_col = self._enquote_identifier(f"dst_{dst_table}_id")
        lines.append(
            f"{self._enquote_identifier('id')} NUMBER(19) GENERATED ALWAYS AS IDENTITY PRIMARY KEY"
        )
        src_pk = pk_map.get(src_table, ["id", "NUMBER(19)"])
        src_pk_name = src_pk[0]
        src_pk_type = src_pk[1]
        dst_pk = pk_map.get(dst_table, ["id", "NUMBER(19)"])
        dst_pk_name = dst_pk[0]
        dst_pk_type = dst_pk[1]
        lines.append(f"{src_col} {src_pk_type} NOT NULL")
        lines.append(f"{dst_col} {dst_pk_type} NOT NULL")
        for col in self._add_table_columns(label, props, pk, pk_map):
            lines.append(col)
        src_tab = self._enquote_identifier(f"{src_table}_{VERTEX_TABLE_SUFFIX}")
        src_tab_col = self._enquote_identifier(src_pk_name)
        src_fk = self._enquote_identifier(f"FK_{table_prefix}_SRC")
        dst_tab = self._enquote_identifier(f"{dst_table}_{VERTEX_TABLE_SUFFIX}")
        dst_tab_col = self._enquote_identifier(dst_pk_name)
        dst_fk = self._enquote_identifier(f"FK_{table_prefix}_DST")
        lines.append(
            f"CONSTRAINT {src_fk} FOREIGN KEY ({src_col}) REFERENCES {src_tab}({src_tab_col})"
        )
        lines.append(
            f"CONSTRAINT {dst_fk} FOREIGN KEY ({dst_col}) REFERENCES {dst_tab}({dst_tab_col})"
        )
        sql = ",\n  ".join(lines)
        table_name = self._enquote_identifier(f"{table_prefix}_{EDGE_TABLE_SUFFIX}")
        return f"CREATE TABLE {table_name} (\n  {sql}\n);"

    def _create_label_and_props(self, label, props):
        lines = [self._enquote_identifier(f"{prop['name']}") for prop in props]
        properties = (
            "PROPERTIES (\n   " + ",\n   ".join(lines) + "\n)"
            if len(props) > 0
            else "NO PROPERTIES"
        )
        return f"LABEL {self._enquote_identifier(label)} {properties}"

    def _create_pg_vertex(self, label, pk, props):
        table_name = self._enquote_identifier(f"{label}_{VERTEX_TABLE_SUFFIX}")
        key = self._enquote_identifier(pk)
        label_and_props = self._create_label_and_props(label, props)
        return f"{table_name} KEY ({key}) {label_and_props}"

    def _create_pg_edge(self, label, constraint, props, pk_map):
        src_label, dst_label = constraint
        table_name = self._enquote_identifier(
            f"{label}_{src_label}_{dst_label}_{EDGE_TABLE_SUFFIX}"
        )
        src_col = self._enquote_identifier(f"src_{src_label}_id")
        src_tab = self._enquote_identifier(f"{src_label}_{VERTEX_TABLE_SUFFIX}")
        if pk_map.get(src_label):
            src_tab_col = self._enquote_identifier(pk_map.get(src_label)[0])
        else:
            src_tab_col = self._enquote_identifier(f"{src_label}_id")
        dst_col = self._enquote_identifier(f"dst_{dst_label}_id")
        dst_tab = self._enquote_identifier(f"{dst_label}_{VERTEX_TABLE_SUFFIX}")
        if pk_map.get(dst_label):
            dst_tab_col = self._enquote_identifier(pk_map.get(dst_label)[0])
        else:
            dst_tab_col = self._enquote_identifier(f"{dst_label}_id")
        return (
            f"{table_name} "
            f"KEY ({self._enquote_identifier('id')}) "
            f"SOURCE KEY ({src_col}) REFERENCES {src_tab} ({src_tab_col}) "
            f"DESTINATION KEY ({dst_col}) REFERENCES {dst_tab} ({dst_tab_col}) "
            f"{self._create_label_and_props(label, props)}"
        )

    # TODO: Add method to create indexes?

    def _generate_ddl(self, schema_graph):
        # To build vertex and edge tables
        vertices = []
        edges = []
        # To build property graph definition
        pg_vertices = []
        pg_edges = []

        # Using table name as label
        pk_map = {}

        for label, node in schema_graph.node_dict.items():
            pk = node.primary if getattr(node, "primary", None) else "id"
            props = node.properties
            sql_table = self._create_vertex_table(label, props, pk, pk_map)
            pg_vertex = self._create_pg_vertex(label, pk, props)
            vertices.append(sql_table)
            pg_vertices.append(pg_vertex)
        for label, edge in schema_graph.edge_dict.items():
            props = edge.properties
            constraints = edge.src_dst_list
            pk = "id"
            for c in constraints:
                sql_table = self._create_edge_table(label, c, props, pk, pk_map)
                pg_edge = self._create_pg_edge(label, c, props, pk_map)
                edges.append(sql_table)
                pg_edges.append(pg_edge)

        # Assemble CREATE PROPERTY GRAPH
        graph_name = self._enquote_identifier(schema_graph.db_id)
        vertex_tables = "VERTEX TABLES (\n  " + ",\n  ".join(pg_vertices) + "\n  )"
        edge_tables = ""
        if len(pg_edges) > 0:
            edge_tables = "EDGE TABLES (\n  " + ",\n  ".join(pg_edges) + "\n  )"
        pg_stmt = (
            "CREATE PROPERTY GRAPH "
            + graph_name
            + "\n  "
            + vertex_tables
            + "\n  "
            + edge_tables
            + ";"
        )

        return vertices + edges + [pg_stmt]

    def _get_file_name_from_domain(self, domain: str, subdomain: str, extension: str):
        filename = f"{domain.replace(' ', '_')}_{subdomain.replace(' ', '_')}.{extension}"
        return filename

    def save_schema_to_file(
        self, output_dir, schema_graph: SchemaGraph, domain: str, subdomain: str
    ):
        """save SchemaGraph to SQL file"""

        output_dir.mkdir(exist_ok=True)

        filename = self._get_file_name_from_domain(domain, subdomain, "sql")
        file_path = output_dir / filename

        # Transform schema graph to a series of SQL ddls
        ddls = self._generate_ddl(schema_graph)

        # Save to file
        with open(file_path, "w", encoding="utf-8") as f:
            for ddl in ddls:
                f.write(ddl)
                f.write("\n")

        return str(file_path)

    def _build_sqlldr_column(self, prop: Dict[str, str]) -> str:
        name = self._enquote_identifier(prop["name"])
        loader_type = SQLLDR_TYPE_MAP.get(prop.get("type", ""), "CHAR")
        nullif = f"NULLIF {name}=BLANKS" if prop.get("optional") else ""
        return f"{name} {loader_type} {nullif}"

    def _write_control_file(
        self, control_path: Path, table_identifier: str, csv_file: Path, columns: List[str]
    ):
        control_path.parent.mkdir(parents=True, exist_ok=True)
        content_lines = [
            "OPTIONS (SKIP=1)",
            "LOAD DATA",
            f'INFILE "{csv_file}"',
            "APPEND",
            f"INTO TABLE {table_identifier}",
            "FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '\"'",
            "TRAILING NULLCOLS",
            "(",
        ]
        for idx, column in enumerate(columns):
            suffix = "," if idx < len(columns) - 1 else ""
            content_lines.append(f"  {column}{suffix}")
        content_lines.append(")")

        control_path.write_text("\n".join(content_lines) + "\n", encoding="utf-8")

    def _format_sqlldr_command(
        self, credentials: str, control_file: Path, log_file: Path, bad_file: Path
    ) -> str:
        return f"sqlldr {credentials} control={control_file} log={log_file} bad={bad_file}"

    def _generate_table_sqlldr(
        self,
        label,
        properties,
        csv_dir,
        control_dir,
        log_directory,
        bad_directory,
        credentials,
        load_instructions,
        is_edge_table,
        src_label,
        dst_label,
    ):
        if is_edge_table:
            prefix = f"{label}_{src_label}_{dst_label}"
            suffix = EDGE_TABLE_SUFFIX
        else:
            prefix = label
            suffix = VERTEX_TABLE_SUFFIX
        table_identifier = self._enquote_identifier(f"{prefix}_{suffix}")
        csv_file = csv_dir / f"{prefix}.csv"
        control_path = control_dir / f"{prefix}.ctl"

        columns = []
        if is_edge_table:
            src_id = self._enquote_identifier(f"src_{src_label}_id")
            dst_id = self._enquote_identifier(f"dst_{dst_label}_id")
            columns = [
                f"{src_id} INTEGER EXTERNAL",
                f"{dst_id} INTEGER EXTERNAL",
            ]

        columns.extend(self._build_sqlldr_column(prop) for prop in properties)
        self._write_control_file(control_path, table_identifier, csv_file, columns)

        log_path = log_directory / f"{prefix}.log"
        bad_path = bad_directory / f"{prefix}.bad"
        command = self._format_sqlldr_command(credentials, control_path, log_path, bad_path)

        load_instructions.append(
            {
                "table": table_identifier,
                "csv_file": str(csv_file),
                "control_file": str(control_path),
                "log_file": str(log_path),
                "bad_file": str(bad_path),
                "command": command,
            }
        )

    # TODO Add variable type to all methods
    def generate_sqlldr_control_files(
        self,
        output_dir: Path,
        schema_graph: SchemaGraph,
        domain: str,
        subdomain: str,
        csv_dir: Path,
        control_dir: Path,
        credentials: str = "<user>/<password>@<connect_string>",
        log_dir: Path | None = None,
        bad_dir: Path | None = None,
    ) -> str:
        """generate SQLLDR scripts that allow to load data from csv files for given SchemaGraph"""

        csv_dir = Path(csv_dir)
        control_dir = Path(control_dir)
        control_dir.mkdir(parents=True, exist_ok=True)
        log_directory = Path(log_dir) if log_dir else control_dir / "logs"
        bad_directory = Path(bad_dir) if bad_dir else control_dir / "bad"
        log_directory.mkdir(parents=True, exist_ok=True)
        bad_directory.mkdir(parents=True, exist_ok=True)

        load_instructions: List[Dict[str, str]] = []

        for label, node in schema_graph.node_dict.items():
            self._generate_table_sqlldr(
                label,
                node.properties,
                csv_dir,
                control_dir,
                log_directory,
                bad_directory,
                credentials,
                load_instructions,
                False,
                None,
                None,
            )
        for label, edge in schema_graph.edge_dict.items():
            for src_label, dst_label in edge.src_dst_list:
                self._generate_table_sqlldr(
                    label,
                    edge.properties,
                    csv_dir,
                    control_dir,
                    log_directory,
                    bad_directory,
                    credentials,
                    load_instructions,
                    True,
                    src_label,
                    dst_label,
                )

        output_dir.mkdir(exist_ok=True)

        filename = self._get_file_name_from_domain(domain, subdomain, "sh")
        file_path = output_dir / filename

        with open(file_path, "w", encoding="utf-8") as f:
            for info in load_instructions:
                f.write(f"{info['command']}")
                f.write("\n")

        return file_path
