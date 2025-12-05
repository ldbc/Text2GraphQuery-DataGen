from app.core.schema.schema_graph import SchemaGraph
from app.core.schema.schema_parser import SchemaParser

# Type mappings: JSON schema -> Oracle SQL
# TODO: define all supported types and specify allowed formats
TYPE_MAP = {
    "INT64":    "NUMBER(19)",
    "INT32":    "NUMBER(10)",
    "FLOAT":    "FLOAT",
    "STRING":   "VARCHAR2(4000)",
    "DATETIME": "TIMESTAMP",
    "BOOL":     "BOOLEAN",
}

VERTEX_TABLE_SUFFIX = "VTX"
EDGE_TABLE_SUFFIX = "EDG"

class OracleSchemaParser(SchemaParser):
    def __init__(self, db_id, instance_path):
      self.db_id = db_id
      self.instance_path = instance_path

    def get_schema_graph(self):
      #Adding dummy implementation for now
      schema_graph = SchemaGraph(self.db_id)
      return schema_graph

    def enquote_identifier(self, identifier):
      #TODO throw error here for invalid identifier
      return "\"" + identifier + "\""

    def column_attrs(self, prop, pk):
      type = TYPE_MAP.get(prop['type'], 'VARCHAR2(4000)')
      nullable = ' NOT NULL' if not prop.get('optional') else ''
      unique = ' UNIQUE' if prop.get('unique') and (not pk or prop.get('name') != pk) else ''
      return type + nullable + unique

    def table_columns(self, props, pk):
      cols = []
      for prop in props:
        col_def = f"{self.enquote_identifier(prop['name'])} {self.column_attrs(prop, pk)}"
        if pk and prop['name'] == pk:
          col_def += " PRIMARY KEY"
        cols.append(col_def)
      return cols

    def create_vertex_table(self, label, props, pk):
      table_name = self.enquote_identifier(f"{label}_{VERTEX_TABLE_SUFFIX}")
      cols = self.table_columns(props, pk)
      columns = ',\n  '.join(cols) if len(cols) > 0 else ''
      stmt = f"CREATE TABLE {table_name} (\n  {columns}\n);"
      return stmt

    def create_edge_table(self, label, constraints, props):
      lines = []
      src_label, dst_label = constraints
      src_col = self.enquote_identifier(f"src_{src_label}_id")
      dst_col = self.enquote_identifier(f"dst_{dst_label}_id")
      lines.append(f"{self.enquote_identifier("id")} NUMBER(19) GENERATED ALWAYS AS IDENTITY PRIMARY KEY")
      lines.append(f"{src_col} NUMBER(19) NOT NULL")
      lines.append(f"{dst_col} NUMBER(19) NOT NULL")
      for col in self.table_columns(props, None):
        lines.append(col)
      src_tab = self.enquote_identifier(f"{src_label}_{VERTEX_TABLE_SUFFIX}")
      src_tab_col = self.enquote_identifier(f"{src_label}_id")
      src_fk = self.enquote_identifier(f"FK_{label}_{src_label}_SRC")
      dst_tab = self.enquote_identifier(f"{dst_label}_{VERTEX_TABLE_SUFFIX}")
      dst_tab_col = self.enquote_identifier(f"{dst_label}_id")
      dst_fk = self.enquote_identifier(f"FK_{label}_{dst_label}_DST")
      lines.append(f"CONSTRAINT {src_fk} FOREIGN KEY ({src_col}) REFERENCES {src_tab}({src_tab_col})")
      lines.append(f"CONSTRAINT {dst_fk} FOREIGN KEY ({dst_col}) REFERENCES {dst_tab}({dst_tab_col})")
      sql = ',\n  '.join(lines)
      table_name = self.enquote_identifier(f"{label}_{src_label}_{dst_label}_{EDGE_TABLE_SUFFIX}")
      return f"CREATE TABLE {table_name} (\n  {sql}\n);"

    def create_label_and_props(self, label, props):
      lines = [self.enquote_identifier(f"{prop['name']}") for prop in props]
      properties = "PROPERTIES (\n   " + ",\n   ".join(lines) + "\n)"  if len(props) > 0 else "NO PROPERTIES"
      return f"LABEL {self.enquote_identifier(label)} {properties}"

    def create_pg_vertex(self, label, pk, props):
      table_name = self.enquote_identifier(f"{label}_{VERTEX_TABLE_SUFFIX}")
      return f"{table_name} KEY ({self.enquote_identifier(pk)}) {self.create_label_and_props(label, props)}"

    def create_pg_edge(self, label, constraint, props):
      src_label, dst_label = constraint
      table_name = self.enquote_identifier(f"{label}_{src_label}_{dst_label}_{EDGE_TABLE_SUFFIX}")
      src_col = self.enquote_identifier(f"src_{src_label}_id")
      src_tab = self.enquote_identifier(f"{src_label}_{VERTEX_TABLE_SUFFIX}")
      src_tab_col = self.enquote_identifier(f"{src_label}_id")
      dst_col = self.enquote_identifier(f"dst_{dst_label}_id")
      dst_tab = self.enquote_identifier(f"{dst_label}_{VERTEX_TABLE_SUFFIX}")
      dst_tab_col = self.enquote_identifier(f"{dst_label}_id")
      return (f"{table_name} "
        f"KEY ({self.enquote_identifier("id")}) "
        f"SOURCE KEY ({src_col}) REFERENCES {src_tab} ({src_tab_col}) "
        f"DESTINATION KEY ({dst_col}) REFERENCES {dst_tab} ({dst_tab_col}) "
        f"{self.create_label_and_props(label, props)}")

    # TODO: Add method to create indexes?

    def generate_ddl(self, schema_graph):
      # To build vertex and edge tables
      vertices = []
      edges = []
      # To build property graph definition
      pg_vertices = []
      pg_edges = []

      for label, node in schema_graph.node_dict.items():
        pk = node.primary
        props = node.properties
        sql_table = self.create_vertex_table(label, props, pk)
        pg_vertex = self.create_pg_vertex(label, pk, props)
        vertices.append(sql_table)
        pg_vertices.append(pg_vertex)
      for label, edge in schema_graph.edge_dict.items():
        props = edge.properties
        constraints = edge.src_dst_list
        for c in constraints:
          sql_table = self.create_edge_table(label, c, props)
          pg_edge = self.create_pg_edge(label, c, props)
          edges.append(sql_table)
          pg_edges.append(pg_edge)

      # Assemble CREATE PROPERTY GRAPH
      graph_name = self.enquote_identifier(schema_graph.db_id)
      vertex_tables = "VERTEX TABLES (\n  " + ",\n  ".join(pg_vertices) + "\n  )"
      edge_tables = ""
      if len(pg_edges) > 0:
        edge_tables = "EDGE TABLES (\n  " + ",\n  ".join(pg_edges) + "\n  )"
      pg_stmt = ("CREATE PROPERTY GRAPH " + graph_name + 
        "\n  " + vertex_tables +
        "\n  " + edge_tables + ";")

      return vertices + edges + [pg_stmt]

    def save_schema_to_file(
        self, output_dir, schema_graph: SchemaGraph, domain: str, subdomain: str
    ):
        """save SchemaGraph to SQL file"""

        output_dir.mkdir(exist_ok=True)

        filename = f"{domain.replace(' ', '_')}_{subdomain.replace(' ', '_')}.sql"
        file_path = output_dir / filename

        # Transform schema graph to a series of SQL ddls
        ddls = self.generate_ddl(schema_graph)

        # save to file
        with open(file_path, "w", encoding="utf-8") as f:
          for ddl in ddls:
            f.write(ddl)
            f.write("\n")

        return str(file_path)
