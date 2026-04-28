import logging
from pathlib import Path

from app.core.generator.data_generator import DataGenerator
from app.core.llm.llm_client import LlmClient

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger("DataGenerator")


def main():
    try:
        """
        Initializes the DataGenerator, generate data base on given schema file.
        - schema_file (Path): The path of schema file 
          (e.g, "examples/generated_schemas/banking_financial.json")
        - llm_client (LlmClient): The language model client used for schema generation 
          (e.g, "qwen3-coder-plus-2025-07-22").
        """
        schema_file = Path("examples/generated_schemas/.json")
        schema_type = 'JSON'
        #schema_file = Path("examples/generated_schemas/nature_animals.sql")
        #schema_type = 'SQL'
        llm_client = LlmClient(model="qwen3-coder-plus-2025-07-22")

        logger.info("Creating DataGenerator...")
        data_gen = DataGenerator(llm_client)

        logger.info("Call LLM to generate high-quality data...")
        script_path, csv_files = data_gen.generate_data(
            schema_file, schema_type, output_base="examples/generated_data"
        )

        logger.info(f"Data generation script saved to: {script_path}")
        logger.info(f"Generated {len(csv_files)} CSV files")

        # Print file list
        logger.info("Generated Data Files:")
        for file in csv_files:
            print(f"- {file.name}")

        csv_file_info = ""
        # Display sample data
        for sample_file in csv_files:
            print(f"\nSample data of '{sample_file.name}':")
            csv_file_info += f"\nSample data of '{sample_file.name}':\n"
            with open(sample_file, encoding="utf-8") as f:
                for i, line in enumerate(f):
                    if i < 5:  # Display first 5 lines
                        print(line.strip())
                        csv_file_info = csv_file_info + line.strip() + "\n"
                    else:
                        break

        logger.info("Data generation completed!")

        if schema_type == 'JSON':
            # Generate import_config.json file
            logger.info("Generate import_config.json file...")
            success = data_gen.generate_import_config(
               schema_file, csv_file_info, output_path="examples/generated_data/scripts/csv_files"
            )
            if success:
               logger.info("import_config.json generation completed!")
            else:
               logger.error("import_config.json generation failed! Try again.")

    except Exception as e:
        logger.error(f"Program execution failed: {str(e)}", exc_info=True)


if __name__ == "__main__":
    main()
