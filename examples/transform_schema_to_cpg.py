import argparse
import json
from pathlib import Path
from typing import Dict, List

from app.core.schema.schema_graph import Edge, Node, SchemaGraph
from app.impl.oracle_sql.schema.schema_parser import OracleSchemaParser

# Path to directory containing input JSON files and output SQL files
INPUT_PATH = "examples/generated_schemas/"


def read_json_from_file(filename):
    with open(filename, encoding="utf-8") as f:
        return json.load(f)


def build_schema_graph(domain: str, schema_data: List[Dict]) -> SchemaGraph:
    """Convert LLM-generated JSON data into SchemaGraph instance"""
    schema_graph = SchemaGraph(db_id=domain)

    # Process all nodes
    node_map = {}
    for item in schema_data:
        if item["type"] == "VERTEX":
            node = Node(
                label=item["label"],
                properties=item["properties"],
                # Add Primary attribute
                primary=item["primary"],
            )
            schema_graph.add_node(node)
            node_map[item["label"]] = node

    # process all edges
    for item in schema_data:
        if item["type"] == "EDGE":
            # Extract source and target node labels
            src_dst_list = []
            for constraint in item.get("constraints", []):
                if len(constraint) == 2:
                    src_label, dst_label = constraint
                    src_dst_list.append([src_label, dst_label])

            edge = Edge(
                label=item["label"],
                src_dst_list=src_dst_list,
                properties=item.get("properties", []),
            )
            schema_graph.add_edge(edge)

    return schema_graph


if __name__ == "__main__":
    # Normally we would call SchemaGenerator, but that
    # requires calling LLM and, so for now we are
    # building schema graph from json file

    # Get json file from arguments
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--file", help="Graph schema in json format under examples/generated_schemas/"
    )
    parser.add_argument("--graph_name", help="Graph name")
    parser.add_argument("--domain")
    parser.add_argument("--subdomain")
    parser.add_argument(
        "--csv_dir", help="Directory containing CSV files for vertex and edge loads"
    )
    parser.add_argument(
        "--control_dir", help="Directory to write generated SQL*Loader control files"
    )
    parser.add_argument(
        "--credentials", help="<user>/<password>@<connect_string> for sqlldr commands"
    )
    args = parser.parse_args()
    json_file = read_json_from_file(INPUT_PATH + args.file + ".json")

    if isinstance(json_file, dict):
        definition = json_file.get("schema")
    else:
        definition = json_file

    db_id = args.graph_name
    schema_graph = build_schema_graph(db_id, definition)

    # Create schema parser
    oracle_schema_parser = OracleSchemaParser(db_id, "examples")
    output_dir = Path("examples/generated_schemas/")

    domain = args.domain
    subdomain = args.subdomain
    # serialize schema graph to Oracle format SQL file
    saved_path = oracle_schema_parser.save_schema_to_file(
        output_dir, schema_graph, domain, subdomain
    )

    # TODO: Use logger
    print(f"Schema SQL file saved to: {saved_path}")

    control_dir = Path(args.control_dir)
    csv_dir = Path(args.csv_dir)
    command_files = oracle_schema_parser.generate_sqlldr_control_files(
        output_dir,
        schema_graph=schema_graph,
        domain=domain,
        subdomain=subdomain,
        csv_dir=csv_dir,
        control_dir=control_dir,
        credentials=args.credentials,
    )
    print(f"SQLLDR commands saved to: {command_files}")
