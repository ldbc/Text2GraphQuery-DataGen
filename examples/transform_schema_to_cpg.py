import json
import argparse

# Type mappings: JSON schema -> Oracle SQL
# TODO: define all supported types and specify allowed formats
TYPE_MAP = {
    "INT64":    "NUMBER(19)",
    "INT32":    "NUMBER(10)",
    "FLOAT":    "FLOAT",
    "STRING":   "VARCHAR2(4000)",
    "DATETIME": "TIMESTAMP",
    "BOOL":     "NUMBER(1)",  # 0/1 for False/True
}

# Path to directory containing input JSON files and output SQL files
INPUT_PATH = "examples/generated_schemas/"

def map_type(prop):
  sql_type = TYPE_MAP.get(prop['type'], 'VARCHAR2(4000)')
  nullable = '' if not prop.get('optional', True) else ''
  return sql_type + (' NOT NULL' if not prop.get('optional', True) else '')

def render_columns(props, with_pk=None):
  lines = []
  for prop in props:
    line = f"  {prop['name']} {map_type(prop)}"
    if with_pk and with_pk == prop['name']:
      line += " PRIMARY KEY"
    lines.append(line)
  return ',\n'.join(lines)

def table_columns(props, pk, uniques=None):
  cols = []
  for prop in props:
    ddl = f"{prop['name']} {map_type(prop)}"
    if pk and prop['name'] == pk:
      ddl += " PRIMARY KEY"
    cols.append(ddl)
  # Add additional unique constraints
  if uniques:
    for uq in uniques:
      if pk and uq == pk:
        continue
      cols.append(f"UNIQUE ({uq})")
  return ',\n  '.join(cols)

def create_vertex_table(label, props, pk):
  uniques = [p['name'] for p in props if p.get('unique')]
  stmt = f"CREATE TABLE {label}_VTX (\n  {table_columns(props, pk, uniques)}\n);"
  return stmt

def create_edge_table(label, constraints, props):
  lines = []
  src_label, dst_label = constraints
  src_col = f"src_{src_label}_id"
  dst_col = f"dst_{dst_label}_id"
  lines.append(f"id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY")
  lines.append(f"{src_col} NUMBER(19) NOT NULL")
  lines.append(f"{dst_col} NUMBER(19) NOT NULL")
  for prop in props:
    lines.append(f"{prop['name']} {map_type(prop)}")
  lines.append(f"CONSTRAINT FK_{label}_{src_label}_SRC FOREIGN KEY ({src_col}) REFERENCES {src_label}_VTX({src_label}_id)")
  lines.append(f"CONSTRAINT FK_{label}_{dst_label}_DST FOREIGN KEY ({dst_col}) REFERENCES {dst_label}_VTX({dst_label}_id)")
  sql = ',\n  '.join(lines)
  return f"CREATE TABLE {label}_{src_label}_{dst_label}_EDG (\n  {sql}\n);"

def create_pg_vertex(label, pk, props):
  lines = [f"{prop['name']}" for prop in props]
  return f"{label}_VTX KEY ({pk}) PROPERTIES (\n   " + ",\n   ".join(lines) + "\n)"

def create_pg_edge(label, constraint, props):
  src_label, dst_label = constraint
  lines = [f"{prop['name']}" for prop in props]
  return (f"{label}_{src_label}_{dst_label}_EDG "
      f"KEY (id) "
      f"SOURCE KEY (src_{src_label}_id) REFERENCES {src_label}_VTX ({src_label}_id) "
      f"DESTINATION KEY (dst_{dst_label}_id) REFERENCES {dst_label}_VTX ({dst_label}_id) "
      "PROPERTIES (\n   " + ",\n   ".join(lines) + "\n)")

def generate_ddl(defn):
  vertices = []
  edges = []
  # To build property graph definitions
  pg_vertices = []
  pg_edges = []

  for item in defn:
    if item['type'] == "VERTEX":
      label = item['label']
      pk = item.get('primary')
      props = item['properties']
      sql_table = create_vertex_table(label, props, pk)
      pg_vertex = create_pg_vertex(label, pk, props)
      vertices.append(sql_table)
      pg_vertices.append(pg_vertex)
    elif item['type'] == "EDGE":
      label = item['label']
      props = item['properties']
      constraints = item['constraints']
      for c in constraints:
        sql_table = create_edge_table(label, c, props)
        pg_edge = create_pg_edge(label, c, props)
        edges.append(sql_table)
        pg_edges.append(pg_edge)
  
  # Assemble CREATE PROPERTY GRAPH
  pg_stmt = ("CREATE PROPERTY GRAPH movie_graph\n"
         "  VERTEX TABLES (\n  " +
         ",\n  ".join(pg_vertices) +
         "\n  )\n  EDGE TABLES (\n  " +
         ",\n  ".join(pg_edges) +
         "\n  );")
  
  return vertices + edges + [pg_stmt]

def read_json_from_file(filename):
  with open(filename, 'r', encoding='utf-8') as f:
    return json.load(f)


if __name__ == "__main__":
  # Get json file from arguments
  parser = argparse.ArgumentParser()
  parser.add_argument('file', help='Graph schema in json format')
  args = parser.parse_args()
  definition = read_json_from_file(INPUT_PATH + args.file+ ".json" )
  #print(definition)

  # Transform to a series of SQL ddls
  ddls = generate_ddl(definition)

  # Write the ddls to a file
  output_file = f"{INPUT_PATH}{args.file}.sql"
  print(f"Output written to {output_file}")
  with open(output_file, "w") as file:
    for ddl in ddls:
      file.write(ddl)
      file.write("\n")
