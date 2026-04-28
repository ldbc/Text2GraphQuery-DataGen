import logging
from pathlib import Path

from app.core.generator.schema_generator import SchemaGenerator
from app.core.llm.llm_client import LlmClient
from app.impl.tugraph_cypher.schema.schema_parser import TuGraphSchemaParser

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


def main():
    try:
        """
        Initializes the domain, subdomain, and complexity level for schema generation.
        - domain (str): The main category for schema generation (e.g., "game").
        - subdomain (str): A more specific category within the domain (e.g., "card_games").
        - complexity_level (int): The desired complexity of the schema 
          (1-5, where 5 is most complex).
        - llm_client (LlmClient): The language model client used for schema generation 
          (e.g, "qwen3-coder-plus-2025-07-22").
        """
        domain = "moive"
        subdomain = "movielens"
        complexity_level = 3
        llm_client = LlmClient(model="qwen3-coder-plus-2025-07-22")

        schema_gen = SchemaGenerator(llm_client=llm_client)

        logger.info("Generating Schema...")
        schema_graph = schema_gen.generate_schema(domain, subdomain, complexity_level)

        # validate SchemaGraph
        if schema_graph.validate():
            logger.info("Schema generated successfully")

            tugraph_schema_parser = TuGraphSchemaParser("", "")
            output_dir = Path("examples/generated_schemas/")

            # serialize schema graph to tugraph format JSON file
            saved_path = tugraph_schema_parser.save_schema_to_file(
                output_dir, schema_graph, domain, subdomain
            )

            logger.info(f"Schema json file saved to: {saved_path}")

            # Print schema describe
            schema_desc = schema_graph.gen_desc()
            print("=== Schema describe ===")
            print(schema_desc)
        else:
            logger.info("Schema validation failed!")

    except Exception as e:
        logger.error(f"Failed: {str(e)}", exc_info=True)


if __name__ == "__main__":
    main()
