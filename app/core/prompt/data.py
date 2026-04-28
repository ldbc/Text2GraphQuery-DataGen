"""
Prompt templates of DataGenerator
"""

PROMPT = """
You are a world-class Python engineer and an expert in graph database test data generation. 
Your task is to generate a single, self-contained, and executable Python script based on a given graph schema. 
The script must produce high-quality, realistic data that simulates complex real-world scenarios.
"""  # noqa: E501

INSTRUCTION_TEMPLATE = """
Graph Schema:
```json
{schema_json}
```
As a top-tier Python engineer, create a professional, high-quality Python script to generate realistic test data based on the provided graph schema.

Core Requirements:
0.  Strict Schema Adherence (TOP PRIORITY): This is the most important rule. The generated CSV headers and columns MUST STRICTLY and EXACTLY match the properties defined for the corresponding node or edge in the provided `schema_json`.
    - No Extra Columns: DO NOT add any columns that are not explicitly defined in the schema. This includes common default columns like `id`, `_id`, or `node_id`.
    - Exact Naming: If the schema defines a property `{{"name": "customer_id", "type": "string"}}`, the column header in the CSV MUST be `customer_id`.
1.  Single Script Generation: Generate a single, self-contained Python script. It must be directly executable (`python your_script.py`) without any modifications.
2.  Libraries: Use only the following standard libraries: `csv`, `faker`, `numpy`, `random`, `datetime`, and `os`.
3.  Reproducibility: Use `Faker('en_US')`, `np.random.seed(42)`, and `random.seed(42)` to ensure the generated data is reproducible.
4.  File Output:
    - Generate one CSV file for each node type and each edge type.
    - Crucially, all file paths must be relative to the location of the generated script. Use `os.path.dirname(os.path.abspath(__file__))` as the base directory.
    - Save node and edge CSV files into a `./csv_files/` subdirectory (relative to the script).
    - The script should automatically create this directory if it doesn't exist.
5.  OOP Script Generation: ...
6.  Libraries & Imports:
    - Use only `csv`, `faker`, `numpy`, `random`, `datetime`, and `os`.
    - CRITICAL IMPORT STYLE: You MUST use `from faker import Faker` to import the Faker library. Do not use `import faker`. The script should then instantiate it with `fake = Faker('en_US')`.

Data Realism & Quality Requirements:
8.  Data Volume Control: Use configurable parameters at the top of the script (e.g., `USER_COUNT`, `TRANSACTION_COUNT`) to easily control the amount of data generated.
9.  Realistic Data Distributions:
    - Implement realistic distributions for relevant properties.
    - For "hub" nodes or popular items (e.g., a few users with many transactions), use a power-law distribution. A good way to model this is with `numpy.random.zipf(a, size=...)`.
    - For values like transaction amounts, use a log-normal distribution (`numpy.random.lognormal(mean, sigma, size=...)`) or a skewed distribution to simulate a long tail (many small values, few large ones).
    - Use normal distribution (`numpy.random.normal`) for attributes like age or scores where applicable.
    - Add detailed comments in the code to explain which distribution is used for which attribute and why.
10. Data Consistency & Dependency Management:    - CRITICAL: Every function that generates nodes (e.g., `generate_customers`) MUST return a list of the unique IDs it generated.
    - The `main` function is responsible for orchestrating the calls. It must capture the returned ID lists from node-generation functions.
    - When a function needs IDs from another entity (e.g., `generate_accounts` needs customer IDs), these IDs MUST be passed as function arguments. Do not rely on global variables.
11.  Edge CSV File Structure (VERY IMPORTANT): This rule defines the specific format for all relationship (edge) CSV files.
    - Headers for Edges: The column headers for the source and destination nodes MUST be the `name` of the source node type and the `name` of the destination node type from the schema, respectively. They MUST NOT be `_from` or `_to`.
    - Data Values for Edges: The data values in these columns MUST be the raw node IDs ONLY (e.g., `LE0000`). They MUST NOT include the node type as a prefix (e.g., NOT `Lender/LE0000`).
    - Example: For an edge defined in the schema as `{{"name": "LENDS_TO", "source": "Lender", "destination": "Loan", "properties": [...]}}` the resulting CSV file header MUST be `Lender,Loan,...properties`.

12. Data Noise: For about 10% of records, simulate missing data by setting 1-2 non-critical, non-key fields to an empty string (`''`).
    - CRITICAL: Do NOT use Python's `None` object to represent missing values. The final representation in the CSV file for an empty field MUST be an empty string `''`, resulting in `,,` for an empty column.

CSV Formatting & Safety Rules:
13. Writing Files: Use `csv.writer` with `newline=''` and `encoding='utf-8'`.
14. Quoting Strategy (CRITICAL): You MUST set the quoting strategy to `quoting=csv.QUOTE_MINIMAL`. This is essential for compatibility with strict data importers. Do not use `QUOTE_ALL`.
15. Field Cleaning:
    - Before writing, clean all string fields: `str(field).strip().replace('\\r', '').replace('\\n', ' ')`.
    - Ensure every row has the exact same number of columns as the CSV header.
16. Sanitization Function: To ensure data integrity and prevent all common import errors, you MUST include and use the following helper function within the generated script's main class.
    ```python
    def _sanitize_for_csv(self, row_data: list) -> list:
        \"\"\"
        Cleans and formats a list of data just before it's written to CSV.
        - Formats datetime objects to 'YYYY-MM-DD HH:MM:SS'.
        - Converts None to an empty string ''.
        - Strips whitespace and removes newlines from all other data.
        \"\"\"
        cleaned_row = []
        for item in row_data:
            if isinstance(item, datetime):
                # Format datetime objects specifically
                cleaned_row.append(item.strftime('%Y-%m-%d %H:%M:%S'))
            elif item is None:
                # Convert None to empty string
                cleaned_row.append('')
            else:
                # Convert all other items to string, then clean
                s = str(item).strip()
                s = s.replace('\r\n', ' ').replace('\n', ' ').replace('\r', ' ')
                cleaned_row.append(s)
        return cleaned_row
    ```
17. Mandatory Usage: Every single `writer.writerow()` call MUST be wrapped with this sanitization function.
    - Correct Usage Example: `writer.writerow(self._sanitize_for_csv([field1, field2, field3]))`
    - Incorrect Usage Example: `writer.writerow([field1, field2, field3])`
18. CSV Writer Configuration: Configure the `csv.writer` with the following parameters for maximum compatibility: `newline=''` and `quoting=csv.QUOTE_MINIMAL`.

Final Output Instructions:
    - Python Code Only: Your entire response must be ONLY the Python code, enclosed in a single ` ```python ` block. Do not add any explanation, introduction, or concluding remarks.
    - Self-Contained: The script must include all necessary imports, parameter definitions, functions, and a main execution block (`if __name__ == "__main__":`).
    - Date Handling: When using `faker.date_...` functions, use `end_date='now'`.

Reference Example Snippet (for distribution and relationship logic):
```python
# ... (inside a generation function) ...
# Store generated IDs for later use in relationships
customer_ids = [f"C{{i:06d}}" for i in range(CUSTOMER_COUNT)]
# ... (in another function) ...
# For generating relationships, sample from the existing ID list
from_id = random.choice(customer_ids)
to_id = random.choice(account_ids)
writer.writerow([from_id, to_id, ...])

# Example for power-law distribution of activities per user
# 'a=2' is a common parameter for Zipf distributions
user_activity_counts = np.random.zipf(a=2, size=USER_COUNT)
# ... use these counts to generate a realistic number of events per user ...
```
"""  # noqa: E501

FIX_INSTRUCTION = """
The Python code you previously generated failed with an error. 
Please analyze the code and the error traceback, fix the bug, and provide the complete, corrected Python script.

Constraints:
    - Output ONLY the full, corrected Python code in a single ```python block.
    - Do not add any apologies or explanations outside the code.
    - Ensure all dependencies between functions are correctly handled (e.g., passing IDs as arguments or using class attributes).

    --- PREVIOUS CODE ---
    ```python
    {original_code}
    ```

    --- ERROR TRACEBACK ---
    ```
    {last_error}
    ``` 
"""  # noqa: E501


FIX_SYSTEM_PROMPT = """
You are a senior Python debugger. Your task is to fix the provided code based on the error message.
"""  # noqa: E501


IMPORT_SYSTEM_PROMPT = """
You are tasked with constructing an `import_config.json` file for use with the `lgraph_import` command to import test data into a TuGraph-DB graph database. This `import_config.json` file consists of two main sections:
1. The graph schema, which I have already prepared.
2. The `files` section, which specifies the paths to data files, header information, and column details. I will provide you with all CSV files, their headers, and an example of the `files` array. Your job is to help me generate a correct `import_config.json` file for these CSV files to facilitate data import.

Example of `import_config.json`:
{{
    "schema": [],
    "files": [
        {{
            "path": "Customer.csv",
            "label": "Customer",
            "format": "CSV",
            "header": 1,
            "columns": [
                "id",
                "name",
                "risk_level",
                "kyc_status",
                "last_updated",
                "noise_attr_1"
            ]
        }},
        {{
            "path": "Account.csv",
            "label": "Account",
            "format": "CSV",
            "header": 1,
            "columns": [
                "account_id",
                "balance",
                "currency",
                "open_date"
            ]
        }},
        {{
            "path": "Transaction.csv",
            "label": "Transaction",
            "format": "CSV",
            "header": 1,
            "columns": [
                "txn_id",
                "amount",
                "timestamp",
                "counterparty"
            ]
        }},
        {{
            "path": "Guarantor.csv",
            "label": "Guarantor",
            "format": "CSV",
            "header": 1,
            "columns": [
                "guarantor_id",
                "credit_rating",
                "relation_type"
            ]
        }},
        {{
            "path": "Ecommerce_Order.csv",
            "label": "Ecommerce_Order",
            "format": "CSV",
            "header": 1,
            "columns": [
                "order_id",
                "product",
                "amount"
            ]
        }},
        {{
            "path": "OWNS.csv",
            "label": "OWNS",
            "format": "CSV",
            "header": 1,
            "SRC_ID": "Customer",
            "DST_ID": "Account",
            "columns": [
                "SRC_ID",
                "DST_ID",
                "ownership_percent"
            ]
        }},
        {{
            "path": "HAS_TRANSACTION.csv",
            "label": "HAS_TRANSACTION",
            "format": "CSV",
            "header": 1,
            "SRC_ID": "Account",
            "DST_ID": "Transaction",
            "columns": [
                "SRC_ID",
                "DST_ID"
            ]
        }},
        {{
            "path": "GUARANTEES.csv",
            "label": "GUARANTEES",
            "format": "CSV",
            "header": 1,
            "SRC_ID": "Guarantor",
            "DST_ID": "Customer",
            "columns": [
                "SRC_ID",
                "DST_ID",
                "guarantee_amount",
                "expiry_date"
            ]
        }},
        {{
            "path": "CYCLIC_GUARANTEE_1.csv",
            "label": "CYCLIC_GUARANTEE_1",
            "format": "CSV",
            "header": 1,
            "SRC_ID": "Guarantor",
            "DST_ID": "Guarantor",
            "columns": [
                "SRC_ID",
                "DST_ID"
            ]
        }},
        {{
            "path": "CYCLIC_GUARANTEE_2.csv",
            "label": "CYCLIC_GUARANTEE_2",
            "format": "CSV",
            "header": 1,
            "SRC_ID": "Guarantor",
            "DST_ID": "Guarantor",
            "columns": [
                "SRC_ID",
                "DST_ID"
            ]
        }},
        {{
            "path": "CROSS_DOMAIN_ORDER.csv",
            "label": "CROSS_DOMAIN_ORDER",
            "format": "CSV",
            "header": 1,
            "SRC_ID": "Customer",
            "DST_ID": "Ecommerce_Order",
            "columns": [
                "SRC_ID",
                "DST_ID"
            ]
        }},
        {{
            "path": "NOISE_REL_1.csv",
            "label": "NOISE_REL_1",
            "format": "CSV",
            "header": 1,
            "SRC_ID": "Transaction",
            "DST_ID": "Guarantor",
            "columns": [
                "SRC_ID",
                "DST_ID"
            ]
        }}
    ]
}}

Important notes:
1. For edge files, always use "SRC_ID" and "DST_ID" as column names to indicate the source and destination nodes, rather than using the actual property names. For example:
{{"path": "TRIGGERED_ALERT.csv","label": "TRIGGERED_ALERT_BY_TRANSACTION", "format":"CSV","header": 3,"SRC_ID": "Transaction","DST_ID": "Alert","columns": [
        "transaction_id",
        "alert_id",
        "alert_reason"
     ]}}
Should be written as:
{{"path": "TRIGGERED_ALERT.csv","label": "TRIGGERED_ALERT_BY_TRANSACTION", "format":"CSV","header": 3,"SRC_ID": "Transaction","DST_ID": "Alert","columns": [
        "SRC_ID",
        "DST_ID",
        "alert_reason"
     ]}}
That is, use "SRC_ID" and "DST_ID" in the columns array to specify the edge endpoints.

2. For edge files, the "label" value must match the value defined in the schema exactly. Do not add suffixes or modify the label, otherwise the import will fail. For example:
{{
     "path": "TRIGGERED_ALERT.csv",
     "label": "TRIGGERED_ALERT_BY_TRANSACTION",
     "format": "CSV",
     ...
}},
{{
     "path": "TRIGGERED_ALERT.csv",
     "label": "TRIGGERED_ALERT_BY_RISKSCORE",
     "format": "CSV",
     ...
}}
Should be written as:
{{
     "path": "TRIGGERED_ALERT.csv",
     "label": "TRIGGERED_ALERT",
     "format": "CSV",
     ...
}},
{{
     "path": "TRIGGERED_ALERT.csv",
     "label": "TRIGGERED_ALERT",
     "format": "CSV",
     ...
}}
Always use the label value as defined in the schema.

3. In the files section, for each edge, the "SRC_ID" and "DST_ID" values must be strings, not arrays. For example:
{{
     "path": "SourceOf.csv",
     "label": "SourceOf",
     "format": "CSV",
     "header": 1,
     "SRC_ID": ["MOUNTAIN", "LAKE"],
     "DST_ID": "RIVER",
     "columns": ["SRC_ID", "DST_ID"]
}}
is incorrect. If a node needs to point to multiple nodes, create separate blocks for each source node:
{{
     "path": "SourceOf.csv",
     "label": "SourceOf",
     "format": "CSV",
     "header": 1,
     "SRC_ID": "MOUNTAIN",
     "DST_ID": "RIVER",
     "columns": ["SRC_ID", "DST_ID"]
}},
{{
     "path": "SourceOf.csv",
     "label": "SourceOf",
     "format": "CSV",
     "header": 1,
     "SRC_ID": "LAKE",
     "DST_ID": "RIVER",
     "columns": ["SRC_ID", "DST_ID"]
}}
The same applies for "DST_ID".
"""  # noqa: E501


IMPORT_INSTRUCTION = """
Based on the schema and file information below, generate the complete `import_config.json` file. Follow all the rules defined in the system prompt.

## Graph Schema
```json
{schema_json}
```

CSV Files Information
```
{csv_files_info}
```
"""  # noqa: E501
