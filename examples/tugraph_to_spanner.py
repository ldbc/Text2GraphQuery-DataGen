"""
Example: Convert TuGraph-DB Schema to Google Spanner DDL

This example demonstrates how to use the migration tool to convert a TuGraph-DB 
import_config.json to Google Spanner compatible DDL and import configuration.

The conversion includes:
- Converting TuGraph schema definitions to Spanner table schemas
- Handling vertex and edge table definitions
- Creating Spanner Property Graph definitions
- Generating data import configurations for Spanner

Input:
- A tugraph import_config.json file containing schema and file definitions

Output:
- Spanner_SchemaDDL_*.sql: SQL DDL statements for Google Spanner
  - Vertex table definitions
  - Edge table definitions with foreign keys
  - Property Graph definition
- spanner_import_config.json: Configuration for importing data into Spanner
"""

import os
import sys
from pathlib import Path
import json
import logging

# Add the parent directory to the path so we can import from app
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import from the schema translator
from app.core.translator.schema_translator import (
    ImportConfigGenerator,
    DDLGenerator,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def convert_tugraph_to_spanner(input_json_path: str, output_dir: str) -> None:
    """
    Convert a TuGraph import_config.json to Spanner DDL and import configuration.
    
    Args:
        input_json_path: Path to the TuGraph import_config.json file
        output_dir: Directory where output files will be generated
        
    Example:
        >>> convert_tugraph_to_spanner(
        ...     "examples/generated_schemas/example_schema.json",
        ...     "examples/Spanner_Instance"
        ... )
    """
    
    # Validate input file
    if not os.path.exists(input_json_path):
        logger.error(f"Input file not found: {input_json_path}")
        return
    
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    # Load input configuration
    logger.info(f"Loading TuGraph schema from: {input_json_path}")
    try:
        with open(input_json_path, 'r', encoding='utf-8') as f:
            config_data = json.load(f)
    except Exception as e:
        logger.error(f"Error loading JSON: {e}")
        return
    
    # Extract graph name from file path
    graph_name = Path(input_json_path).parent.name.lower()
    
    # Generate Spanner import configuration
    logger.info("Generating Spanner import configuration...")
    try:
        import_gen = ImportConfigGenerator()
        spanner_import_config = import_gen.generate(config_data)
        
        import_config_path = os.path.join(output_dir, "spanner_import_config.json")
        with open(import_config_path, 'w', encoding='utf-8') as f:
            f.write(spanner_import_config)
        logger.info(f"✓ Generated Spanner import config: {import_config_path}")
    except Exception as e:
        logger.error(f"Error generating import config: {e}")
        return
    
    # Generate Spanner DDL
    logger.info("Generating Spanner DDL...")
    try:
        ddl_gen = DDLGenerator()
        stages = ddl_gen.generate_stages(config_data, graph_name)
        
        # Combine all DDL stages
        final_ddl = "\n\n".join([
            stages.get('01_nodes', ''),
            stages.get('02_edges', ''),
            stages.get('03_graph', '')
        ]).strip()
        
        ddl_filename = f"Spanner_SchemaDDL_{graph_name}.sql"
        ddl_path = os.path.join(output_dir, ddl_filename)
        with open(ddl_path, 'w', encoding='utf-8') as f:
            f.write(final_ddl)
        logger.info(f"✓ Generated Spanner DDL: {ddl_path}")
        
        # Print DDL preview
        logger.info("\n--- Spanner DDL Preview (first 500 chars) ---")
        logger.info(final_ddl[:500] + "...\n")
        
    except Exception as e:
        logger.error(f"Error generating DDL: {e}")
        return
    
    logger.info(f"✓ Conversion completed successfully!")
    logger.info(f"Output directory: {output_dir}")


if __name__ == "__main__":
    # Example usage: Convert example_schema.json to Spanner format
    input_path = "examples/generated_schemas/example_schema.json"
    output_path = "examples/Spanner_Instance"
    
    # Change to project root directory
    os.chdir(Path(__file__).parent.parent)
    
    convert_tugraph_to_spanner(input_path, output_path)
